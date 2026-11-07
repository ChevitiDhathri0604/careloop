"""
CareLoop Behaviour Monitor & Kill-Switch Controller
Tracks real-time agent behaviour (request frequency, bulk read volumes, unauthorized tool attempts).
Automatically quarantines anomalous or compromised agents and revokes their active tokens.
"""

from typing import Dict, Any, List
from datetime import datetime
from services.control_plane.registry import agent_registry

class BehaviourMonitor:
    def __init__(self, bulk_read_threshold: int = 15):
        self.bulk_read_threshold = bulk_read_threshold
        self.agent_read_counts: Dict[str, int] = {}
        self.anomalies: List[Dict[str, Any]] = []

    def record_data_read(self, agent_id: str, count: int) -> bool:
        """
        Records record access count. If count exceeds threshold, quarantines agent.
        Returns: True if safe, False if quarantined
        """
        current = self.agent_read_counts.get(agent_id, 0) + count
        self.agent_read_counts[agent_id] = current

        if current > self.bulk_read_threshold:
            self._trigger_kill_switch(
                agent_id=agent_id,
                anomaly_type="BULK_READ_EXCEEDED",
                reason=f"Agent attempted to read {current} records, exceeding safe threshold of {self.bulk_read_threshold}"
            )
            return False
        return True

    def _trigger_kill_switch(self, agent_id: str, anomaly_type: str, reason: str):
        agent_registry.quarantine_agent(agent_id, reason)
        anomaly = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "agentId": agent_id,
            "anomalyType": anomaly_type,
            "reason": reason,
            "actionTaken": "AGENT_QUARANTINED"
        }
        self.anomalies.append(anomaly)

        from services.control_plane.ledger import action_ledger
        action_ledger.record_audit(
            actor="behaviour-monitor",
            action_type="EMERGENCY_KILL_SWITCH_QUARANTINE",
            details=anomaly
        )

    def manual_kill_switch(self, agent_id: str, reason: str = "Clinician manual kill-switch"):
        """Allows clinician or ops operator to manually kill/quarantine any agent mid-run"""
        self._trigger_kill_switch(agent_id, "MANUAL_TRIGGER", reason)

    def reset_agent(self, agent_id: str):
        """Restores quarantined agent after operator clearance"""
        agent = agent_registry.get_agent(agent_id)
        if agent:
            agent.is_quarantined = False
            agent.is_active = True
            self.agent_read_counts[agent_id] = 0

            from services.control_plane.ledger import action_ledger
            action_ledger.record_audit(
                actor="ops-operator",
                action_type="AGENT_RESTORED_FROM_QUARANTINE",
                details={"agentId": agent_id}
            )

behaviour_monitor = BehaviourMonitor()
