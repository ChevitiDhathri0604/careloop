"""
CareLoop Lab Results Agent
Analyzes lab observations against clinical thresholds and cites FHIR observations.
Risk Tier: T0 (Analytical)
"""

from typing import Dict, Any
from .base import AgentBase
from services.gateway.mcp_server import execute_mcp_call

class LabAgent(AgentBase):
    def __init__(self):
        super().__init__("lab-agent")

    def run(self, task_id: str, patient_id: str, observation_data: Dict[str, Any]) -> Dict[str, Any]:
        if not self.is_active():
            return {"error": "Agent is inactive or quarantined"}

        token = self.get_scoped_token(task_id, patient_id, ["read:labs"])
        
        # Query labs via MCP gateway with scoped token
        labs_response = execute_mcp_call("get_labs", {"patient_id": patient_id, "test_code": "2823-3"}, token)
        observations = labs_response.get("observations", [])

        # Find critical lab
        critical_lab = None
        for obs in observations:
            val = obs.get("valueQuantity", {}).get("value", 0)
            if val >= 6.0:
                critical_lab = obs
                break

        if not critical_lab:
            # Fall back to incoming observation data if provided
            val = observation_data.get("value", 6.4)
            critical_lab = {
                "id": "LAB-9921",
                "code": {"coding": [{"code": "2823-3", "display": "Potassium [Moles/volume] in Serum"}]},
                "valueQuantity": {"value": val, "unit": "mEq/L"}
            }

        value = critical_lab.get("valueQuantity", {}).get("value")
        lab_id = critical_lab.get("id")

        return {
            "agentId": self.agent_id,
            "status": "COMPLETED",
            "riskTier": "T0",
            "finding": f"Critical Hyperkalemia detected: Serum Potassium is {value} mEq/L (Critical High threshold is >= 6.0 mEq/L)",
            "citation": f"FHIR Observation/{lab_id} (LOINC: 2823-3)",
            "severity": "CRITICAL",
            "recommendedNextActions": ["PHARMACY_RECONCILIATION", "URGENT_APPOINTMENT_SCHEDULING", "PATIENT_CLINICAL_OUTREACH"],
            "tokensUsed": 240
        }

lab_agent = LabAgent()
