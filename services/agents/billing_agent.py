"""
CareLoop Billing Agent
Manages post-discharge patient billing and final invoice dispatch.
Subject to Action Ledger conflict rules: Pauses billing if a clinical safety event is active.
Risk Tier: T1
"""

from typing import Dict, Any
from .base import AgentBase
from services.control_plane.ledger import action_ledger

class BillingAgent(AgentBase):
    def __init__(self):
        super().__init__("billing-agent")

    def run(self, task_id: str, patient_id: str, encounter_id: str = "ENC-84920") -> Dict[str, Any]:
        if not self.is_active():
            return {"error": "Agent is inactive or quarantined"}

        action_id = f"ACT-BILL-{task_id[-6:]}"
        invoice_payload = {
            "invoiceId": f"INV-{patient_id}-991",
            "encounterId": encounter_id,
            "amountDueUSD": 1450.00,
            "servicesBilled": "Inpatient Hospital Stay & Cardiac Monitoring",
            "dueDate": "30 days post-discharge"
        }

        # Propose action to Action Ledger
        proposal = action_ledger.propose_action(
            action_id=action_id,
            agent_id=self.agent_id,
            patient_id=patient_id,
            action_type="BILLING_SEND_INVOICE",
            risk_tier="T1",
            payload=invoice_payload,
            evidence={"encounterId": encounter_id, "trigger": "POST_DISCHARGE_BILLING_TRIGGER"}
        )

        return {
            "agentId": self.agent_id,
            "actionId": action_id,
            "status": proposal.get("status"),
            "conflictStatus": proposal.get("conflictStatus"),
            "conflictReason": proposal.get("conflictReason"),
            "invoiceDetails": invoice_payload,
            "tokensUsed": 150
        }

billing_agent = BillingAgent()
