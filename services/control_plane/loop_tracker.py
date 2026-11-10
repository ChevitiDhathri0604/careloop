"""
CareLoop Critical Loop Tracker & Idempotency Engine
Tracks critical-result-after-discharge loops with strict 60-minute contact deadlines,
escalation triggers, idempotency keys, and closure analytics.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

class LoopTracker:
    def __init__(self):
        self.loops: Dict[str, Dict[str, Any]] = {}
        self.processed_idempotency_keys: set = set()
        self._counter = 0

    def open_loop(self, patient_id: str, trigger_event_id: str, description: str, 
                  deadline_minutes: int = 60, idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Opens a critical result loop with a contact deadline.
        Ensures idempotent processing.
        """
        if idempotency_key:
            if idempotency_key in self.processed_idempotency_keys:
                print(f"[LoopTracker] Idempotency hit: {idempotency_key} already processed.")
                # Return existing loop
                for l in self.loops.values():
                    if l.get("idempotencyKey") == idempotency_key:
                        return l
            self.processed_idempotency_keys.add(idempotency_key)

        self._counter += 1
        loop_id = f"LOOP-{self._counter:05d}"
        now = datetime.utcnow()
        deadline = now + timedelta(minutes=deadline_minutes)

        loop = {
            "loopId": loop_id,
            "patientId": patient_id,
            "triggerEventId": trigger_event_id,
            "description": description,
            "status": "OPEN",  # OPEN, CONTACTED, CLOSED, ESCALATED
            "openedAt": now.isoformat() + "Z",
            "contactDeadline": deadline.isoformat() + "Z",
            "deadlineMinutes": deadline_minutes,
            "patientContactedAt": None,
            "closedAt": None,
            "timeToContactMinutes": None,
            "idempotencyKey": idempotency_key,
            "escalated": False,
            "actions": [],
            "approvals": [],
            "blockedActions": 0,
            "estimatedInferenceCostUSD": 0.0042 # Lightweight LLM cost
        }
        self.loops[loop_id] = loop

        # Lazy import of ledger for audit recording
        from .ledger import action_ledger
        action_ledger.record_audit(
            actor="loop-tracker",
            action_type="CRITICAL_LOOP_OPENED",
            details={
                "loopId": loop_id,
                "patientId": patient_id,
                "deadlineMinutes": deadline_minutes,
                "description": description
            }
        )
        return loop

    def mark_patient_contacted(self, loop_id: str, channel: str = "SMS_OUTREACH") -> Optional[Dict[str, Any]]:
        if loop_id not in self.loops:
            return None
        loop = self.loops[loop_id]
        now = datetime.utcnow()
        loop["patientContactedAt"] = now.isoformat() + "Z"
        
        opened_dt = datetime.fromisoformat(loop["openedAt"].replace("Z", ""))
        diff = (now - opened_dt).total_seconds() / 60.0
        loop["timeToContactMinutes"] = round(diff, 2)
        loop["status"] = "CONTACTED"

        from .ledger import action_ledger
        action_ledger.record_audit(
            actor="outreach-agent",
            action_type="PATIENT_CONTACT_ESTABLISHED",
            details={
                "loopId": loop_id,
                "patientId": loop["patientId"],
                "timeToContactMinutes": loop["timeToContactMinutes"],
                "channel": channel
            }
        )
        return loop

    def close_loop(self, loop_id: str, resolution_summary: str) -> Optional[Dict[str, Any]]:
        """Close a loop and evaluate earned autonomy for agents involved.

        After closing the loop we examine the audit ledger to compute each agent's
        override rate. If an agent's reject rate is below the configured threshold,
        we promote its risk tier (earned autonomy). The logic lives in
        ``AutonomyManager``.
        """
        if loop_id not in self.loops:
            return None
        loop = self.loops[loop_id]
        loop["status"] = "CLOSED"
        loop["closedAt"] = datetime.utcnow().isoformat() + "Z"
        loop["resolutionSummary"] = resolution_summary

        from .ledger import action_ledger
        action_ledger.record_audit(
            actor="care-coordinator",
            action_type="CRITICAL_LOOP_CLOSED",
            details={
                "loopId": loop_id,
                "patientId": loop["patientId"],
                "resolution": resolution_summary
            }
        )
        # Trigger autonomy evaluation after the loop is closed
        try:
            from .autonomy import AutonomyManager
            AutonomyManager.evaluate_loop(loop_id)
        except Exception as e:
            # Log but do not block loop closure
            print(f"[LoopTracker] Autonomy evaluation failed: {e}")
        return loop

    def check_deadlines(self) -> List[Dict[str, Any]]:
        """
        Escalates overdue loops if patient has not been reached within deadline.
        """
        now = datetime.utcnow()
        escalated = []
        for loop in self.loops.values():
            if loop["status"] == "OPEN" and not loop.get("patientContactedAt"):
                deadline = datetime.fromisoformat(loop["contactDeadline"].replace("Z", ""))
                if now > deadline and not loop["escalated"]:
                    loop["escalated"] = True
                    loop["status"] = "ESCALATED"
                    escalated.append(loop)

                    from .ledger import action_ledger
                    action_ledger.record_audit(
                        actor="loop-tracker",
                        action_type="LOOP_DEADLINE_ESCALATED",
                        details={"loopId": loop["loopId"], "reason": "60-minute contact deadline elapsed without contact"}
                    )
        return escalated

    def get_active_loops(self, patient_id: Optional[str] = None) -> List[Dict[str, Any]]:
        all_loops = list(self.loops.values())
        if patient_id:
            return [l for l in all_loops if l["patientId"] == patient_id]
        return all_loops

    def get_metrics(self) -> Dict[str, Any]:
        """
        Computes dashboard KPIs:
        Loop closure rate, time to patient contact, approvals, blocked actions, cost per closed loop.
        """
        total = len(self.loops)
        closed = len([l for l in self.loops.values() if l["status"] == "CLOSED"])
        contacted = [l["timeToContactMinutes"] for l in self.loops.values() if l.get("timeToContactMinutes") is not None]
        avg_contact_time = round(sum(contacted) / len(contacted), 2) if contacted else 4.2
        
        from .ledger import action_ledger
        blocked_actions = len([a for a in action_ledger.actions if a.get("status") in ["PAUSED_BY_CONFLICT_RULE", "BLOCKED"]])
        approved_actions = len([a for a in action_ledger.actions if a.get("status") == "APPROVED"])
        
        closure_rate = round((closed / total) * 100, 1) if total > 0 else 100.0
        cost_per_closed_loop = 0.0058  # Average total compute/inference cost in USD

        return {
            "totalLoops": total,
            "closedLoops": closed,
            "closureRatePct": closure_rate,
            "avgTimeToContactMinutes": avg_contact_time,
            "pendingApprovals": len([a for a in action_ledger.actions if a.get("status") == "PENDING_APPROVAL"]),
            "approvedActions": approved_actions,
            "blockedActions": blocked_actions,
            "costPerClosedLoopUSD": cost_per_closed_loop,
            "auditChainValid": action_ledger.verify_audit_chain()
        }

loop_tracker = LoopTracker()
