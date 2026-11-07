"""
CareLoop Event Router
Maps incoming clinical and administrative events to multi-agent plans.
Detects critical-result-after-discharge pattern and orchestrates agent workflows.
"""

from typing import Dict, Any, List
from .loop_tracker import loop_tracker
from .ledger import action_ledger

class EventRouter:
    def __init__(self):
        self.active_plans: Dict[str, Dict[str, Any]] = {}
        self._counter = 0

    def route_event(self, event: Dict[str, Any]) -> List[str]:
        """
        Determines which agents should be triggered for a given event.
        Returns a list of target agent IDs in execution sequence.
        """
        event_type = event.get("eventType")
        patient_id = event.get("patientId")
        data = event.get("data", {})

        plan = []

        if event_type == "CRITICAL_LAB_RESULT":
            # Check for hyperkalemia or critical lab post-discharge
            observations = data.get("observations", [])
            for obs in observations:
                loinc = obs.get("loinc")
                val = obs.get("value")
                flag = obs.get("flag")

                # Potassium check (LOINC 2823-3)
                if loinc == "2823-3" and (flag in ["CH", "CRITICAL_HIGH"] or (isinstance(val, (int, float)) and val >= 6.0)):
                    # Critical result loop opened!
                    loop = loop_tracker.open_loop(
                        patient_id=patient_id,
                        trigger_event_id=event.get("eventId", "EVT-DIRECT"),
                        description=f"Critical Potassium ({val} mEq/L) detected post-discharge",
                        deadline_minutes=60,
                        idempotency_key=f"POTASSIUM_CRITICAL_{patient_id}_{obs.get('value')}"
                    )

                    # Multi-agent orchestration plan
                    plan = [
                        "lab-agent",
                        "pharmacy-agent",
                        "scheduling-agent",
                        "billing-agent",  # Will be proposed and caught by conflict rule
                        "outreach-agent"   # T2: will wait for clinician approval
                    ]
                    break

        elif event_type == "PATIENT_DISCHARGED":
            action_ledger.record_audit(
                actor="event-router",
                action_type="PATIENT_DISCHARGE_REGISTERED",
                details={"patientId": patient_id, "disposition": data.get("disposition")}
            )
            # Normal billing agent triggered on discharge
            plan = ["billing-agent"]

        return plan

event_router = EventRouter()
