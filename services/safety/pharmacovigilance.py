"""
CareLoop Pharmacovigilance & Drug-Safety Bridge
Detects suspected adverse drug reactions (ADRs) reported in patient replies
and converts them into regulatory ICH-E2B (R3) XML/JSON-compatible Individual Case Safety Report (ICSR) drafts.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid

ADR_KEYWORDS = {
    "dizziness": {"meddra_term": "Dizziness", "meddra_code": "10013573", "severity": "MODERATE"},
    "dizzy": {"meddra_term": "Dizziness", "meddra_code": "10013573", "severity": "MODERATE"},
    "weakness": {"meddra_term": "Muscle Weakness", "meddra_code": "10028372", "severity": "MODERATE"},
    "muscle weakness": {"meddra_term": "Muscle Weakness", "meddra_code": "10028372", "severity": "MODERATE"},
    "palpitations": {"meddra_term": "Palpitations", "meddra_code": "10033557", "severity": "HIGH"},
    "irregular heartbeat": {"meddra_term": "Arrhythmia", "meddra_code": "10003119", "severity": "HIGH"},
    "shortness of breath": {"meddra_term": "Dyspnoea", "meddra_code": "10013968", "severity": "HIGH"},
    "rash": {"meddra_term": "Rash", "meddra_code": "10037844", "severity": "LOW"},
    "nausea": {"meddra_term": "Nausea", "meddra_code": "10028813", "severity": "LOW"}
}

class PharmacovigilanceBridge:
    def __init__(self):
        self.drafted_cases: List[Dict[str, Any]] = []

    def analyze_message_for_adr(self, patient_id: str, message_text: str, patient_medications: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Analyzes patient message text for suspected adverse drug events.
        If detected, drafts an ICH-E2B (R3) safety report.
        """
        lower_msg = message_text.lower()
        detected_reactions = []

        for keyword, info in ADR_KEYWORDS.items():
            if keyword in lower_msg:
                detected_reactions.append(info)

        if not detected_reactions:
            return None

        case_id = f"E2B-ICSR-{uuid.uuid4().hex[:8].upper()}"
        report_date = datetime.utcnow().strftime("%Y%m%d%H%M%S")

        # Suspect drugs (highlighting potassium-sparing or highest risk)
        suspect_drugs = []
        for med in patient_medications:
            is_suspect = med.get("highRiskWithHyperkalemia", False) or "spironolactone" in med.get("name", "").lower()
            suspect_drugs.append({
                "medicinalProduct": med.get("name"),
                "drugCharacterization": "1=Suspect" if is_suspect else "2=Concomitant",
                "dosage": med.get("dosage", "Unspecified"),
                "indication": "Congestive Heart Failure / Hypertension"
            })

        # Build E2B(R3) Structure
        icsr_case = {
            "caseSafetyReportId": case_id,
            "transmissionDate": report_date,
            "reportType": "1=Spontaneous",
            "patient": {
                "patientIdentifier": patient_id,
                "reactionDetails": detected_reactions,
                "patientNarrative": message_text
            },
            "suspectDrugs": suspect_drugs,
            "seriousnessCriteria": {
                "resultsInDeath": False,
                "lifeThreatening": any(r["severity"] == "HIGH" for r in detected_reactions),
                "requiresHospitalization": False,
                "disabling": False
            },
            "status": "DRAFT_PENDING_SAFETY_OFFICER_REVIEW",
            "createdAt": datetime.utcnow().isoformat() + "Z"
        }

        self.drafted_cases.append(icsr_case)

        # Audit trail recording
        from services.control_plane.ledger import action_ledger
        action_ledger.record_audit(
            actor="drug-safety-bridge",
            action_type="ADVERSE_EVENT_E2B_DRAFT_CREATED",
            details={
                "caseId": case_id,
                "patientId": patient_id,
                "reactionsCount": len(detected_reactions),
                "reactions": [r["meddra_term"] for r in detected_reactions]
            }
        )

        return icsr_case

    def get_all_cases(self) -> List[Dict[str, Any]]:
        return self.drafted_cases

pv_bridge = PharmacovigilanceBridge()
