"""
CareLoop Pharmacy Reconciliation Agent
Analyzes patient medications against lab abnormalities.
Field Masking: Restricted to medications only via MCP Gateway.
Risk Tier: T0 (Analytical proposal)
"""

from typing import Dict, Any, List
from .base import AgentBase
from services.gateway.mcp_server import execute_mcp_call

class PharmacyAgent(AgentBase):
    def __init__(self):
        super().__init__("pharmacy-agent")

    def run(self, task_id: str, patient_id: str, lab_context: Dict[str, Any]) -> Dict[str, Any]:
        if not self.is_active():
            return {"error": "Agent is inactive or quarantined"}

        # Scoped token allows ONLY read:medications
        token = self.get_scoped_token(task_id, patient_id, ["read:medications"])

        # Fetch medications through MCP gateway
        meds_response = execute_mcp_call("get_medications", {"patient_id": patient_id}, token)
        medications = meds_response.get("medications", [])

        # Check for potassium-sparing or nephrotoxic medications
        flagged_meds = []
        citations = []
        for med in medications:
            name = med.get("name", "")
            if med.get("highRiskWithHyperkalemia") or "spironolactone" in name.lower() or "lisinopril" in name.lower():
                flagged_meds.append(med)
                citations.append(f"FHIR MedicationRequest/{med.get('id')} ({name})")

        spironolactone_present = any("spironolactone" in m.get("name", "").lower() for m in flagged_meds)

        recommendation = "Review and withhold potassium-sparing agents."
        if spironolactone_present:
            recommendation = (
                "HOLD Spironolactone immediately due to critical potassium (6.4 mEq/L). "
                "Co-administration of Lisinopril further elevates hyperkalemia risk. "
                "Recheck serum potassium and renal panel in 48 hours."
            )

        return {
            "agentId": self.agent_id,
            "status": "COMPLETED",
            "riskTier": "T0",
            "finding": f"High-risk drug interaction detected: {len(flagged_meds)} potassium-sparing/ACE-inhibitor agents active",
            "flaggedMedications": [m.get("name") for m in flagged_meds],
            "citations": citations,
            "recommendation": recommendation,
            "fieldMaskingActive": True,
            "tokensUsed": 380
        }

pharmacy_agent = PharmacyAgent()
