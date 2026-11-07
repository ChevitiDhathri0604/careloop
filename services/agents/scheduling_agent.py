"""
CareLoop Scheduling Agent
Books urgent post-discharge follow-up slots.
Risk Tier: T1 (Reversible automated administrative action)
"""

from typing import Dict, Any
from .base import AgentBase
from services.control_plane.ledger import action_ledger

class SchedulingAgent(AgentBase):
    def __init__(self):
        super().__init__("scheduling-agent")

    def run(self, task_id: str, patient_id: str, urgency_reason: str) -> Dict[str, Any]:
        if not self.is_active():
            return {"error": "Agent is inactive or quarantined"}

        action_id = f"ACT-SCHED-{task_id[-6:]}"
        slot_details = {
            "slotId": "SLOT-9942",
            "department": "Cardiology / Nephrology Post-Discharge Urgent Care",
            "physician": "Dr. Sarah Jenkins, MD",
            "appointmentTime": "Tomorrow, 10:30 AM",
            "appointmentType": "Urgent Hyperkalemia Follow-up & Repeat Chem-7",
            "location": "Cardiology Clinic Suite 4B / In-Person or Telehealth"
        }

        # Propose and register action in ledger (T1 auto-action)
        action_ledger.propose_action(
            action_id=action_id,
            agent_id=self.agent_id,
            patient_id=patient_id,
            action_type="SCHEDULING_URGENT_BOOKING",
            risk_tier="T1",
            payload=slot_details,
            evidence={"reason": urgency_reason, "source": "CRITICAL_LAB_TRIGGER"}
        )

        # Mark confirmed since T1 is auto-approved
        action_ledger.update_proposal_status(action_id, "EXECUTED", actor="scheduling-agent", notes="Auto-booked urgent slot")

        return {
            "agentId": self.agent_id,
            "status": "COMPLETED",
            "actionId": action_id,
            "riskTier": "T1",
            "bookingDetails": slot_details,
            "execution": "AUTOMATICALLY_EXECUTED",
            "tokensUsed": 190
        }

scheduling_agent = SchedulingAgent()
