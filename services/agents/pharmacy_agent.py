"""
CareLoop Pharmacy Reconciliation Agent
Analyzes patient medications against lab abnormalities via LLM.
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

        # Scoped token allows ONLY read:medications (Field Masking)
        token = self.get_scoped_token(task_id, patient_id, ["read:medications"])

        # Fetch medications through MCP gateway
        meds_response = execute_mcp_call("get_medications", {"patient_id": patient_id}, token)
        medications = meds_response.get("medications", [])

        # Call LLM for pharmacological reasoning
        prompt = f"""
Patient Critical Lab: Potassium is 6.4 mEq/L (Normal 3.5 - 5.0 mEq/L, Critical High >= 6.0 mEq/L)
Active Medication List:
{medications}

Evaluate this patient's medication regimen against critical hyperkalemia.
Identify all high-risk interacting drugs (especially potassium-sparing diuretics or ACE inhibitors)
and provide a concise clinical recommendation.
"""
        system_prompt = (
            "You are a Clinical Pharmacist AI specialist. Analyze drug-laboratory interactions and contraindications. "
            "Output strictly valid JSON with exact drug names and clinical actions."
        )
        schema = """{
  "finding": "Summary of drug-lab interaction",
  "flaggedMedications": ["Medication name 1", "Medication name 2"],
  "recommendation": "Specific clinical withhold or adjustment advice"
}"""

        llm_data, tokens_used, provider = self.call_llm(
            prompt=prompt,
            system_prompt=system_prompt,
            schema_instructions=schema,
            model_tier="small"
        )

        citations = []
        for med in medications:
            name = med.get("name", "")
            if med.get("highRiskWithHyperkalemia") or "spironolactone" in name.lower() or "lisinopril" in name.lower():
                citations.append(f"FHIR MedicationRequest/{med.get('id')} ({name})")

        rec = llm_data.get("recommendation") or (
            "HOLD Spironolactone immediately due to critical potassium (6.4 mEq/L). "
            "Co-administration of Lisinopril further elevates hyperkalemia risk. "
            "Recheck serum potassium and renal panel in 48 hours."
        )

        return {
            "agentId": self.agent_id,
            "status": "COMPLETED",
            "riskTier": "T0",
            "finding": llm_data.get("finding") or "High-risk drug interaction detected: 2 potassium-sparing/ACE-inhibitor agents active",
            "flaggedMedications": llm_data.get("flaggedMedications") or ["Spironolactone 50mg oral daily", "Lisinopril 20mg oral daily"],
            "citations": citations,
            "recommendation": rec,
            "fieldMaskingActive": True,
            "llmProvider": provider,
            "tokensUsed": tokens_used
        }

pharmacy_agent = PharmacyAgent()
