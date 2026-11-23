"""
CareLoop Control Plane API
Exposes endpoints for the entire CareLoop ecosystem:
- Agent registry & Emergency Kill-Switch
- Event Ingestion & Routing
- Action Ledger & Cryptographic Audit Chain
- Clinician Approval Inbox
- Loop Tracker & Deadline Escalations
- Safety moments (Conflict detection, Injection guard, PV bridge)
- Replay Simulator
"""

from typing import Dict, Any, List, Optional
from pathlib import Path
from fastapi import FastAPI, HTTPException, Body, UploadFile, File, Query, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .registry import agent_registry
from .ledger import action_ledger
from .loop_tracker import loop_tracker
from .risk_gate import risk_gate
from .router import event_router

from services.ingestion.event_publisher import event_bus
from services.safety.injection_guard import injection_guard
from services.safety.pharmacovigilance import pv_bridge
from services.safety.behaviour_monitor import behaviour_monitor
from services.simulator.replay_engine import replay_engine
from services.agents import lab_agent, pharmacy_agent, scheduling_agent, billing_agent, outreach_agent
from services.agents.llm_gateway import llm_gateway

app = FastAPI(
    title="CareLoop Control Plane & Safety Gate",
    version="2.0.0",
    description="Autonomous Clinical Safety Control Plane with Cryptographic Audit Trail"
)

# Optional OpenTelemetry instrumentation
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    trace.set_tracer_provider(TracerProvider())
    tracer = trace.get_tracer(__name__)
    span_processor = BatchSpanProcessor(ConsoleSpanExporter())
    trace.get_tracer_provider().add_span_processor(span_processor)
    FastAPIInstrumentor().instrument_app(app)
except Exception:
    pass


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request Models
class EventRequest(BaseModel):
    eventType: str
    patientId: str
    patientName: Optional[str] = "Synthetic Patient"
    data: Dict[str, Any]

class ApprovalDecisionRequest(BaseModel):
    actionId: str
    decision: str  # "APPROVE" or "REJECT"
    clinicianId: str = "DR-JENKINS-88"
    notes: Optional[str] = None

class FreeTextInput(BaseModel):
    patientId: str
    messageText: str

class KillSwitchRequest(BaseModel):
    agentId: str
    action: str # "QUARANTINE" or "RESTORE"
    reason: Optional[str] = "Manual operator override"

class LLMConfigRequest(BaseModel):
    provider: str
    apiKey: Optional[str] = None
    baseUrl: Optional[str] = None
    smallModel: Optional[str] = None
    largeModel: Optional[str] = None

class LLMTestRequest(BaseModel):
    prompt: str = "Draft a 1-sentence urgent patient alert for hyperkalemia (Potassium 6.4 mEq/L)."

# Endpoints
@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "careloop-control-plane",
        "auditChainIntegrity": action_ledger.verify_audit_chain()
    }

@app.get("/api/metrics")
def get_metrics():
    return loop_tracker.get_metrics()

@app.get("/api/agents")
def list_agents():
    return [a.dict() for a in agent_registry.list_agents()]

@app.post("/api/agents/kill-switch")
def toggle_kill_switch(req: KillSwitchRequest):
    if req.action == "QUARANTINE":
        behaviour_monitor.manual_kill_switch(req.agentId, req.reason)
        return {"status": "QUARANTINED", "agentId": req.agentId}
    else:
        behaviour_monitor.reset_agent(req.agentId)
        return {"status": "RESTORED", "agentId": req.agentId}

@app.get("/api/ledger/proposals")
def get_proposals():
    return action_ledger.get_proposals()

@app.post("/api/ledger/decide")
def decide_proposal(req: ApprovalDecisionRequest):
    action = action_ledger.proposals.get(req.actionId)
    if not action:
        raise HTTPException(status_code=404, detail="Action proposal not found")

    if req.decision == "APPROVE":
        new_status = "APPROVED"
        agent_registry.record_feedback(action["agentId"], approved=True)
        updated = action_ledger.update_proposal_status(req.actionId, new_status, actor=req.clinicianId, notes=req.notes)
        
        # If this was an outreach message or clinical action, mark patient contacted and close loop
        active_loops = loop_tracker.get_active_loops(action["patientId"])
        if active_loops:
            loop_id = active_loops[0]["loopId"]
            loop_tracker.mark_patient_contacted(loop_id)
            loop_tracker.close_loop(
                loop_id,
                resolution_summary=f"Clinical safety loop resolved: Clinician ({req.clinicianId}) approved {action.get('actionType', 'outreach')}. Patient contact verified."
            )

        return {"status": "APPROVED", "action": updated}
    else:
        new_status = "REJECTED_BY_CLINICIAN"
        agent_registry.record_feedback(action["agentId"], approved=False)
        updated = action_ledger.update_proposal_status(req.actionId, new_status, actor=req.clinicianId, notes=req.notes)
        return {"status": "REJECTED", "action": updated}

@app.get("/api/ledger/audit")
def get_audit_trail():
    return {
        "integrityValid": action_ledger.verify_audit_chain(),
        "entriesCount": len(action_ledger.audit_log),
        "entries": action_ledger.get_audit_trail()[-50:]
    }


# ----- Webhook management endpoints -----
from fastapi import Body, HTTPException
from typing import Literal
from fastapi.responses import StreamingResponse
import csv
import io
from services.control_plane.webhook import set_webhook, get_webhook

@app.post("/api/webhook/register")
def register_webhook(payload: dict = Body(...)):
    """Register a webhook URL that will receive JSON notifications for safety events.
    Payload example: {"url": "https://my.endpoint/webhook"}
    """
    url = payload.get("url", "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="Webhook URL required")
    set_webhook(url)
    return {"status": "registered", "url": get_webhook()}

@app.get("/api/webhook/status")
def webhook_status():
    """Return the currently registered webhook URL (empty string if none)."""
    return {"url": get_webhook()}

# ----- Audit ledger export -----

# ----- Debug / Negative scenario endpoints -----
from services.control_plane.negative_scenarios import (
    run_autonomy_negative_scenario,
    test_webhook_failure,
    test_llm_failure,
)

@app.get("/api/debug/negative_autonomy")
def debug_negative_autonomy():
    """Run a loop where every proposal is rejected to demonstrate no autonomy earned."""
    return run_autonomy_negative_scenario()

@app.get("/api/debug/webhook_failure")
def debug_webhook_failure():
    """Trigger a webhook delivery failure and return the error info."""
    return test_webhook_failure()

@app.get("/api/debug/llm_fallback")
def debug_llm_fallback():
    """Force the LLM gateway into deterministic fallback and show the response."""
    return test_llm_failure()


@app.get("/api/loops")
def get_loops():
    # Evaluate deadline checks on poll
    loop_tracker.check_deadlines()
    return loop_tracker.get_active_loops()

@app.post("/api/loops/{loop_id}/close")
def close_loop(loop_id: str, summary: str = Body(..., embed=True)):
    closed = loop_tracker.close_loop(loop_id, summary)
    if not closed:
        raise HTTPException(status_code=404, detail="Loop not found")
    return {"status": "CLOSED", "loop": closed}

@app.post("/api/events")
async def ingest_event(event_req: EventRequest):
    event = await event_bus.publish(event_req.dict())
    plan = event_router.route_event(event)
    return {"status": "PUBLISHED", "eventId": event["eventId"], "orchestrationPlan": plan}

@app.post("/api/safety/inspect-text")
def inspect_text(req: FreeTextInput):
    """Safety Moment 2: Prompt-injection inspection"""
    is_safe, reason, meta = injection_guard.inspect_text(req.messageText, source_identifier=f"patient_{req.patientId}")
    return {
        "isSafe": is_safe,
        "reason": reason,
        "metadata": meta,
        "totalBlockedAttempts": injection_guard.blocked_attempts_count
    }

@app.post("/api/safety/patient-reply")
def handle_patient_reply(req: FreeTextInput):
    """
    Handles inbound patient text with:
    1. Prompt-injection guard
    2. Pharmacovigilance ADR analysis (E2B ICSR generator)
    """
    # 1. Injection check
    is_safe, reason, meta = injection_guard.inspect_text(req.messageText, source_identifier=f"patient_{req.patientId}")
    if not is_safe:
        return {
            "status": "BLOCKED",
            "securityEvent": "PROMPT_INJECTION_PREVENTED",
            "reason": reason,
            "details": meta
        }

    # 2. Pharmacovigilance check
    from data.fhir_store import fhir_store
    meds = fhir_store.get_medications(req.patientId)
    adr_case = pv_bridge.analyze_message_for_adr(req.patientId, req.messageText, meds)

    return {
        "status": "PROCESSED",
        "adrDetected": adr_case is not None,
        "adrCase": adr_case
    }

@app.get("/api/safety/pv-cases")
def get_pv_cases():
    return pv_bridge.get_all_cases()

@app.get("/api/llm/status")
def get_llm_status():
    return llm_gateway.get_status()

@app.post("/api/llm/config")
def update_llm_config(req: LLMConfigRequest):
    llm_gateway.set_config(
        provider=req.provider,
        api_key=req.apiKey,
        base_url=req.baseUrl,
        small_model=req.smallModel,
        large_model=req.largeModel
    )
    # Save to local .env for persistence if key provided
    if req.apiKey:
        try:
            with open(Path(__file__).parent.parent.parent / ".env", "a", encoding="utf-8") as f:
                if "gemini" in req.provider.lower():
                    f.write(f"\nGEMINI_API_KEY={req.apiKey}\n")
                elif "groq" in req.provider.lower():
                    f.write(f"\nGROQ_API_KEY={req.apiKey}\n")
                else:
                    f.write(f"\nOPENAI_API_KEY={req.apiKey}\n")
        except Exception:
            pass

    return {"status": "UPDATED", "config": llm_gateway.get_status()}

@app.post("/api/llm/test")
def test_llm_call(req: LLMTestRequest):
    data, tokens, provider = llm_gateway.complete(
        prompt=req.prompt,
        system_prompt="You are a clinical AI specialist. Provide a brief, professional response.",
        model_tier="small",
        agent_id="test-harness"
    )
    return {
        "status": "SUCCESS",
        "output": data,
        "tokensUsed": tokens,
        "provider": provider,
        "totalTokensConsumed": llm_gateway.total_tokens_consumed,
        "totalSpendUSD": round(llm_gateway.total_inference_cost_usd, 5)
    }

@app.post("/api/simulator/run")
def run_simulation(policy: Optional[Dict[str, Any]] = None):
    return replay_engine.run_simulation(policy)

@app.post("/api/demo/run-full-scenario")
async def run_full_demo():
    """
    Executes the complete critical-result-after-discharge end-to-end scenario:
    1. Patient P-84920 discharged (ADT^A03)
    2. Critical lab results arrives: K+ = 6.4 mEq/L (ORU^R01)
    3. Loop opened with 60-min deadline
    4. Lab agent analyzes and cites FHIR observation
    5. Pharmacy agent analyzes medications and flags Spironolactone (field masking active)
    6. Scheduling agent auto-books urgent slot (T1)
    7. Billing agent attempts invoice dispatch -> PAUSED by conflict rule (Safety Moment 1)
    8. Outreach agent drafts multilingual message -> Enters Approval Inbox (Safety Moment 3)
    """
    patient_id = "P-84920"

    # Step 1: Discharge Event
    discharge_evt = await event_bus.publish({
        "eventType": "PATIENT_DISCHARGED",
        "patientId": patient_id,
        "patientName": "Ramesh Kumar",
        "data": {"dischargeTime": "2026-10-31T09:30:00Z", "disposition": "HOME"}
    })

    # Step 2: Critical Lab Event (Potassium 6.4 mEq/L)
    lab_evt = await event_bus.publish({
        "eventType": "CRITICAL_LAB_RESULT",
        "patientId": patient_id,
        "patientName": "Ramesh Kumar",
        "data": {
            "isCritical": True,
            "observations": [{
                "loinc": "2823-3",
                "testName": "Potassium [Moles/volume] in Serum or Plasma",
                "value": 6.4,
                "unit": "mEq/L",
                "flag": "CRITICAL_HIGH"
            }]
        }
    })

    # Route event and trigger agents
    event_router.route_event(lab_evt)

    # Step 3: Run Agents
    lab_res = lab_agent.run("TASK-LAB-01", patient_id, {"value": 6.4})
    pharm_res = pharmacy_agent.run("TASK-PHARM-01", patient_id, lab_res)
    sched_res = scheduling_agent.run("TASK-SCHED-01", patient_id, "Critical Hyperkalemia post-discharge")
    billing_res = billing_agent.run("TASK-BILL-01", patient_id) # Paused by conflict rule!
    outreach_res = outreach_agent.run("TASK-OUTREACH-01", patient_id, {"lab": lab_res, "pharmacy": pharm_res})

    active_loops = loop_tracker.get_active_loops(patient_id)
    loop = active_loops[0] if active_loops else {}

    return {
        "status": "DEMO_SCENARIO_EXECUTED",
        "patientId": patient_id,
        "loop": loop,
        "labAgent": lab_res,
        "pharmacyAgent": pharm_res,
        "schedulingAgent": sched_res,
        "billingAgent": billing_res,
        "outreachAgent": outreach_res,
        "metrics": loop_tracker.get_metrics(),
        "auditChainValid": action_ledger.verify_audit_chain()
    }


# ---------------------------------------------------------------------------
# PATIENT MANAGEMENT & CLINICAL LOOP PIPELINE ENDPOINTS
# ---------------------------------------------------------------------------
from services.db.database import db
from services.control_plane.pipeline import process_patient_clinical_loop
from services.control_plane.bulk_processor import bulk_processor

class PatientCreateRequest(BaseModel):
    id: Optional[str] = None
    name: str
    birth_date: Optional[str] = None
    gender: Optional[str] = "unknown"
    phone: Optional[str] = None
    preferred_language: Optional[str] = "en"
    discharge_date: Optional[str] = None
    discharge_unit: Optional[str] = "Ambulatory Stepdown"
    attending_physician: Optional[str] = "Dr. Jenkins, MD"
    diagnosis: Optional[str] = "Post-discharge follow-up"
    potassium: Optional[float] = 4.5
    medications: Optional[Any] = []
    billing_amount: Optional[float] = 1250.0

@app.get("/api/patients")
def list_patients(q: Optional[str] = Query(None), limit: int = 200, offset: int = 0):
    patients = db.list_patients(query=q, limit=limit, offset=offset)
    return {"total": len(patients), "patients": patients}

@app.get("/api/patients/{patient_id}")
def get_patient_detail(patient_id: str):
    p = db.get_patient(patient_id)
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    loops = db.get_loops_for_patient(patient_id)
    props = action_ledger.get_proposals(patient_id)
    return {
        "patient": p,
        "loops": loops,
        "proposals": props
    }

@app.post("/api/patients")
def create_or_update_patient(req: PatientCreateRequest, auto_run: bool = Query(True)):
    data = req.dict()
    if auto_run:
        result = process_patient_clinical_loop(data)
        saved = db.get_patient(result["patientId"])
        return {"status": "SUCCESS", "patient": saved, "analysis": result}
    else:
        saved = db.save_patient(data)
        return {"status": "SAVED", "patient": saved}

@app.put("/api/patients/{patient_id}")
def update_patient(patient_id: str, req: Dict[str, Any] = Body(...)):
    existing = db.get_patient(patient_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Patient not found")
    req["id"] = patient_id
    updated = db.save_patient(req)
    return {"status": "UPDATED", "patient": updated}

@app.delete("/api/patients/{patient_id}")
def delete_patient(patient_id: str):
    success = db.delete_patient(patient_id)
    if not success:
        raise HTTPException(status_code=404, detail="Patient not found")
    return {"status": "DELETED", "patientId": patient_id}

@app.post("/api/patients/{patient_id}/analyze")
def analyze_patient(patient_id: str):
    p = db.get_patient(patient_id)
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    result = process_patient_clinical_loop(p)
    return {"status": "ANALYZED", "result": result}

# ---------------------------------------------------------------------------
# BULK INGESTION & REPORT EXPORT ENDPOINTS
# ---------------------------------------------------------------------------
@app.post("/api/bulk/upload")
async def bulk_upload(file: UploadFile = File(...)):
    content_bytes = await file.read()
    if not content_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    try:
        report = bulk_processor.process_batch(file.filename, content_bytes)
        return report
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Processing failed: {str(e)}")

@app.get("/api/bulk/export")
def export_bulk_results(format: str = Query("csv")):
    if format.lower() == "xlsx":
        excel_bytes = bulk_processor.export_results_excel()
        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="careloop_batch_results.xlsx"'}
        )
    else:
        csv_text = bulk_processor.export_results_csv()
        return Response(
            content=csv_text,
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="careloop_batch_results.csv"'}
        )

@app.get("/api/bulk/template/{file_format}")
def download_sample_template(file_format: str):
    fmt = file_format.lower()
    tmpl_dir = Path(__file__).parent.parent.parent / "data" / "templates"
    if fmt == "csv":
        path = tmpl_dir / "careloop_sample_dataset.csv"
        media = "text/csv"
    elif fmt in ["xlsx", "excel"]:
        path = tmpl_dir / "careloop_sample_dataset.xlsx"
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif fmt == "json":
        path = tmpl_dir / "careloop_sample_dataset.json"
        media = "application/json"
    else:
        raise HTTPException(status_code=400, detail="Invalid format. Choose csv, xlsx, or json.")

    if not path.exists():
        raise HTTPException(status_code=404, detail="Template file not found.")

    return FileResponse(
        str(path),
        media_type=media,
        filename=path.name,
        headers={"Content-Disposition": f'attachment; filename="{path.name}"'}
    )

@app.get("/api/bulk/analytics")
def get_bulk_analytics():
    return db.get_analytics()

