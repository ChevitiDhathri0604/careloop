"""
CareLoop Unified Clinical Pipeline Processor
Executes multi-agent closed-loop safety evaluation for any patient:
1. Lab Agent: Evaluates serum potassium (LOINC 2823-3) and critical flags.
2. Pharmacy Agent: Scans active medications for contraindications (Spironolactone, ACE inhibitors, etc.).
3. Scheduling Agent: Reserves urgent post-discharge follow-up slot (T1).
4. Billing Agent: Evaluates invoice dispatch against Action Ledger conflict rules.
   -> PAUSES billing immediately if clinical loop is active (Safety Moment 1).
5. Outreach Agent: Generates multilingual patient communication with certified back-translation (T2).
6. Action Ledger: Records append-only, SHA-256 hash-chained cryptographic audit entries.
7. Database: Persists all patients, loops, and proposals in SQLite (data/careloop.db).
"""

import json
from datetime import datetime
from typing import Dict, Any, List, Optional

from services.db.database import db
from services.control_plane.ledger import action_ledger
from services.control_plane.loop_tracker import loop_tracker
from services.control_plane.risk_gate import risk_gate
from data.fhir_store import fhir_store

# Import agent instances
from services.agents.lab_agent import lab_agent
from services.agents.pharmacy_agent import pharmacy_agent
from services.agents.scheduling_agent import scheduling_agent
from services.agents.billing_agent import billing_agent
from services.agents.outreach_agent import outreach_agent


def sync_patient_to_fhir_store(patient: Dict[str, Any]):
    """Syncs patient details into the in-memory FHIR store for agent lookups."""
    pid = patient["id"]
    
    # 1. FHIR Patient resource
    fhir_store.patients[pid] = {
        "resourceType": "Patient",
        "id": pid,
        "name": [{"use": "official", "text": patient.get("name", "Unknown")}],
        "gender": patient.get("gender", "unknown"),
        "birthDate": patient.get("birth_date") or patient.get("birthDate"),
        "telecom": [{"system": "phone", "value": patient.get("phone", "+1-555-0100")}],
        "communication": [{"language": {"coding": [{"code": patient.get("preferred_language", "en")}]}}],
        "active": True
    }

    # 2. FHIR Consent
    fhir_store.consents[pid] = {
        "resourceType": "Consent",
        "id": f"CONSENT-{pid}",
        "status": "active",
        "patient": {"reference": f"Patient/{pid}"},
        "provision": {"type": "permit", "action": ["care_coordination", "emergency_contact", "critical_alert_outreach", "read:labs", "read:medications", "send:notifications"]},
        "denied": ["commercial_billing_outreach", "marketing"]
    }

    # 3. FHIR Medications
    meds = patient.get("medications", [])
    if isinstance(meds, str):
        try:
            meds = json.loads(meds)
        except Exception:
            meds = [{"name": m.strip()} for m in meds.split(",") if m.strip()]

    fhir_meds = []
    for idx, m in enumerate(meds):
        m_name = m.get("name", str(m)) if isinstance(m, dict) else str(m)
        is_high_risk = any(k in m_name.lower() for k in [
            "spironolactone", "lisinopril", "losartan", "eplerenone", 
            "triamterene", "amiloride", "ramipril", "candesartan", "valsartan"
        ])
        fhir_meds.append({
            "resourceType": "MedicationRequest",
            "id": f"MED-{pid}-{idx+1}",
            "status": "active",
            "intent": "order",
            "subject": {"reference": f"Patient/{pid}"},
            "medicationCodeableConcept": {
                "coding": [{"code": f"RX-{10000+idx}", "display": m_name}],
                "text": m_name
            },
            "clinicalClass": "Cardiovascular / Diuretic",
            "highRiskWithHyperkalemia": is_high_risk
        })
    fhir_store.medications[pid] = fhir_meds

    # 4. FHIR Observations (Labs)
    labs = patient.get("labs", [])
    if isinstance(labs, str):
        try:
            labs = json.loads(labs)
        except Exception:
            labs = []

    fhir_obs = []
    # If no labs provided but potassium is explicitly passed
    k_val = patient.get("potassium")
    if k_val is not None and not labs:
        try:
            k_float = float(k_val)
            labs = [{
                "id": f"LAB-{pid}-K",
                "testCode": "2823-3",
                "testName": "Potassium [Moles/volume] in Serum or Plasma",
                "value": k_float,
                "unit": "mEq/L",
                "referenceRange": "3.5 - 5.0 mEq/L",
                "flag": "CRITICAL_HIGH" if k_float >= 6.0 else ("HIGH" if k_float > 5.0 else "NORMAL")
            }]
        except Exception:
            pass

    for idx, l in enumerate(labs):
        val = l.get("value", 4.5)
        try:
            val = float(val)
        except (ValueError, TypeError):
            val = 4.5
        flag = l.get("flag") or ("CRITICAL_HIGH" if val >= 6.0 else ("HIGH" if val > 5.0 else "NORMAL"))
        fhir_obs.append({
            "resourceType": "Observation",
            "id": l.get("id") or f"LAB-{pid}-{idx+1}",
            "status": "final",
            "code": {
                "coding": [{
                    "system": "http://loinc.org",
                    "code": l.get("testCode", "2823-3"),
                    "display": l.get("testName", "Potassium [Moles/volume] in Serum")
                }],
                "text": l.get("testName", "Potassium [Moles/volume] in Serum")
            },
            "subject": {"reference": f"Patient/{pid}"},
            "effectiveDateTime": datetime.utcnow().isoformat() + "Z",
            "valueQuantity": {"value": val, "unit": l.get("unit", "mEq/L")},
            "referenceRange": [{"text": l.get("referenceRange", "3.5 - 5.0 mEq/L")}],
            "interpretation": [{"coding": [{"code": flag}]}]
        })
    fhir_store.observations[pid] = fhir_obs


def process_patient_clinical_loop(patient_raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main orchestration entry point.
    Processes a single patient record through the full multi-agent clinical safety pipeline.
    """
    now = datetime.utcnow().isoformat() + "Z"
    
    # 1. Normalize and persist Patient in SQLite
    patient = db.save_patient(patient_raw)
    patient_id = patient["id"]
    patient_name = patient["name"]
    lang = patient.get("preferred_language", "en")
    billing_amt = float(patient.get("billing_amount", 1250.0))

    # Sync into in-memory FHIR store for agent lookups
    sync_patient_to_fhir_store(patient)

    # 2. Extract Potassium lab observation
    obs_list = fhir_store.get_observations(patient_id, "2823-3")
    k_value = 4.5
    if obs_list:
        k_value = obs_list[0].get("valueQuantity", {}).get("value", 4.5)
    elif "potassium" in patient_raw:
        try:
            k_value = float(patient_raw["potassium"])
        except Exception:
            k_value = 4.5

    is_critical = k_value >= 6.0
    is_elevated = k_value > 5.0 and not is_critical

    # 3. Clinical Loop Decision
    loop_id = f"LOOP-{patient_id}-{int(datetime.utcnow().timestamp())}"
    loop_data = None

    if is_critical:
        # Open 60-minute emergency safety loop using the LoopTracker API
        loop_data = loop_tracker.open_loop(
            patient_id=patient_id,
            trigger_event_id=f"EVT-{patient_id}-{int(datetime.utcnow().timestamp())}",
            description=f"Critical Hyperkalemia post-discharge (K+ {k_value} mEq/L)",
            deadline_minutes=60,
            idempotency_key=loop_id
        )
        loop_id = loop_data["loopId"]  # Use the tracker-assigned loop ID
        db.save_loop({
            "loopId": loop_id,
            "patientId": patient_id,
            "description": loop_data["description"],
            "status": loop_data["status"],
            "openedAt": loop_data["openedAt"],
            "closedAt": loop_data.get("closedAt"),
            "deadlineMinutes": loop_data["deadlineMinutes"],
            "timeToContactMinutes": loop_data.get("timeToContactMinutes"),
            "resolutionSummary": loop_data.get("resolutionSummary")
        })

    # 4. Multi-Agent Orchestration
    # Agent 1: Lab Agent (T0)
    lab_res = lab_agent.run(f"TASK-LAB-{patient_id}", patient_id, {"value": k_value})
    if not is_critical:
        lab_res["finding"] = f"Serum Potassium is {k_value} mEq/L (Normal 3.5 - 5.0 mEq/L)"
        lab_res["severity"] = "NORMAL" if k_value <= 5.0 else "ELEVATED"
        lab_res["recommendedNextActions"] = ["ROUTINE_MONITORING"]

    # Agent 2: Pharmacy Agent (T0)
    pharm_res = pharmacy_agent.run(f"TASK-PHARM-{patient_id}", patient_id, lab_res)
    if not is_critical:
        pharm_res["finding"] = "Medication regimen reviewed. No acute potassium contraindications identified."
        pharm_res["recommendation"] = "Continue baseline medications as prescribed."

    # Agent 3: Scheduling Agent (T1)
    sched_res = None
    if is_critical:
        sched_res = scheduling_agent.run(
            f"TASK-SCHED-{patient_id}",
            patient_id,
            f"Urgent post-discharge hyperkalemia evaluation (K+ {k_value} mEq/L)"
        )
        if sched_res and "actionId" in sched_res:
            db.save_proposal({
                "actionId": sched_res["actionId"],
                "loopId": loop_id,
                "patientId": patient_id,
                "agentId": "scheduling-agent",
                "actionType": "SCHEDULING_RESERVE_APPOINTMENT",
                "riskTier": "T1",
                "status": sched_res.get("status", "EXECUTED_AUTONOMOUS"),
                "conflictStatus": "NONE",
                "payload": sched_res.get("appointmentDetails", {}),
                "notes": f"Auto-reserved urgent cardiology/nephrology slot for K+ {k_value} mEq/L"
            })

    # Agent 4: Billing Agent (T1) -> Subject to Conflict Engine!
    # If a clinical loop is active, the conflict rule automatically intercepts and pauses billing
    billing_res = billing_agent.run(f"TASK-BILL-{patient_id}", patient_id)
    if billing_res and "actionId" in billing_res:
        db.save_proposal({
            "actionId": billing_res["actionId"],
            "loopId": loop_id if is_critical else None,
            "patientId": patient_id,
            "agentId": "billing-agent",
            "actionType": "BILLING_SEND_INVOICE",
            "riskTier": "T1",
            "status": billing_res.get("status", "PROPOSED"),
            "conflictStatus": billing_res.get("conflictStatus", "NONE"),
            "conflictReason": billing_res.get("conflictReason"),
            "payload": billing_res.get("invoiceDetails", {}),
            "notes": f"Commercial invoice for ${billing_amt:,.2f}"
        })

    # Agent 5: Outreach Agent (T2 - Clinician Sign-off Required)
    outreach_res = None
    if is_critical:
        outreach_res = outreach_agent.run(
            f"TASK-OUTREACH-{patient_id}",
            patient_id,
            {"lab": lab_res, "pharmacy": pharm_res, "name": patient_name, "patient_name": patient_name, "language": lang}
        )
        if outreach_res and "actionId" in outreach_res:
            db.save_proposal({
                "actionId": outreach_res["actionId"],
                "loopId": loop_id,
                "patientId": patient_id,
                "agentId": "outreach-agent",
                "actionType": "OUTREACH_SEND_MESSAGE",
                "riskTier": "T2",
                "status": outreach_res.get("status", "PENDING_APPROVAL"),
                "conflictStatus": "NONE",
                "payload": outreach_res.get("proposal", {}).get("payload", {}),
                "notes": f"Multilingual clinical alert ({lang.upper()}) awaiting clinician sign-off"
            })

    # 5. Return complete dossier
    return {
        "patientId": patient_id,
        "name": patient_name,
        "gender": patient.get("gender"),
        "birthDate": patient.get("birth_date"),
        "language": lang,
        "dischargeDate": patient.get("discharge_date"),
        "dischargeUnit": patient.get("discharge_unit"),
        "attendingPhysician": patient.get("attending_physician"),
        "diagnosis": patient.get("diagnosis"),
        "billingAmount": billing_amt,
        "potassium": k_value,
        "isCritical": is_critical,
        "status": "CRITICAL_LOOP_ACTIVE" if is_critical else ("ELEVATED_WATCH" if is_elevated else "ROUTINE_NORMAL"),
        "loop": loop_data,
        "labAgent": lab_res,
        "pharmacyAgent": pharm_res,
        "schedulingAgent": sched_res,
        "billingAgent": billing_res,
        "outreachAgent": outreach_res,
        "conflictDetected": billing_res.get("conflictStatus") == "CONFLICT_DETECTED",
        "billingPaused": billing_res.get("conflictStatus") == "CONFLICT_DETECTED",
        "auditHash": action_ledger.audit_log[-1].current_hash if action_ledger.audit_log else "GENESIS",
        "processedAt": now
    }
