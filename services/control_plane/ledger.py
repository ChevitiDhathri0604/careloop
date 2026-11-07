"""
CareLoop Action Ledger & Hash-Chained Audit Trail
Implements:
1. Append-only, cryptographically hash-chained audit ledger (SHA-256)
2. Conflict detection engine (e.g., pausing billing when clinical loop is open)
3. Action proposals, decisions, and execution tracking
"""

import hashlib
import json
import time
from typing import Dict, Any, List, Optional
from datetime import datetime

class AuditEntry:
    def __init__(self, entry_id: int, timestamp: str, actor: str, action_type: str, details: Dict[str, Any], prev_hash: str):
        self.entry_id = entry_id
        self.timestamp = timestamp
        self.actor = actor
        self.action_type = action_type
        self.details = details
        self.prev_hash = prev_hash
        self.current_hash = self.compute_hash()

    def compute_hash(self) -> str:
        data = {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp,
            "actor": self.actor,
            "action_type": self.action_type,
            "details": self.details,
            "prev_hash": self.prev_hash
        }
        serialized = json.dumps(data, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entryId": self.entry_id,
            "timestamp": self.timestamp,
            "actor": self.actor,
            "actionType": self.action_type,
            "details": self.details,
            "prevHash": self.prev_hash,
            "currentHash": self.current_hash
        }

class ActionLedger:
    def __init__(self):
        self.audit_log: List[AuditEntry] = []
        self.genesis_hash = "0" * 64
        self.proposals: Dict[str, Dict[str, Any]] = {}
        self.actions: List[Dict[str, Any]] = []
        self._counter = 0

    def record_audit(self, actor: str, action_type: str, details: Dict[str, Any]) -> Dict[str, Any]:
        """
        Appends an immutable entry to the SHA-256 hash-chained audit ledger.
        """
        self._counter += 1
        prev_hash = self.audit_log[-1].current_hash if self.audit_log else self.genesis_hash
        timestamp = datetime.utcnow().isoformat() + "Z"
        
        entry = AuditEntry(
            entry_id=self._counter,
            timestamp=timestamp,
            actor=actor,
            action_type=action_type,
            details=details,
            prev_hash=prev_hash
        )
        self.audit_log.append(entry)
        return entry.to_dict()

    def verify_audit_chain(self) -> bool:
        """
        Verifies cryptographic integrity of the entire audit trail.
        """
        for i, entry in enumerate(self.audit_log):
            expected_prev = self.audit_log[i-1].current_hash if i > 0 else self.genesis_hash
            if entry.prev_hash != expected_prev:
                return False
            if entry.current_hash != entry.compute_hash():
                return False
        return True

    def propose_action(self, action_id: str, agent_id: str, patient_id: str, action_type: str, 
                       risk_tier: str, payload: Dict[str, Any], evidence: Dict[str, Any]) -> Dict[str, Any]:
        """
        Registers an action proposal and evaluates conflict rules against active patient states.
        """
        proposal = {
            "actionId": action_id,
            "agentId": agent_id,
            "patientId": patient_id,
            "actionType": action_type,
            "riskTier": risk_tier,
            "payload": payload,
            "evidence": evidence,
            "status": "PROPOSED",
            "conflictStatus": "NONE",
            "conflictReason": None,
            "createdAt": datetime.utcnow().isoformat() + "Z"
        }

        # Check Conflict Rules
        conflict_detected, reason = self.check_conflicts(patient_id, action_type)
        if conflict_detected:
            proposal["status"] = "PAUSED_BY_CONFLICT_RULE"
            proposal["conflictStatus"] = "CONFLICT_DETECTED"
            proposal["conflictReason"] = reason

            self.record_audit(
                actor="conflict-engine",
                action_type="ACTION_PAUSED_BY_CONFLICT_RULE",
                details={
                    "actionId": action_id,
                    "agentId": agent_id,
                    "patientId": patient_id,
                    "actionType": action_type,
                    "reason": reason
                }
            )
        else:
            self.record_audit(
                actor=agent_id,
                action_type="ACTION_PROPOSED",
                details={"actionId": action_id, "actionType": action_type, "riskTier": risk_tier}
            )

        self.proposals[action_id] = proposal
        self.actions.append(proposal)
        return proposal

    def check_conflicts(self, patient_id: str, action_type: str) -> tuple[bool, Optional[str]]:
        """
        Safety Moment 1: A conflict rule pauses a billing action while a clinical issue is open.
        """
        # Import loop tracker lazily to avoid circular imports
        from .loop_tracker import loop_tracker
        
        active_loops = [loop for loop in loop_tracker.get_active_loops(patient_id) if loop["status"] == "OPEN"]
        
        if action_type.startswith("BILLING_") and len(active_loops) > 0:
            loop_desc = active_loops[0].get("description", "Critical clinical lab event")
            return True, f"Billing action paused: Active clinical safety loop in progress ({loop_desc}). Clinical resolution must precede commercial invoicing."

        return False, None

    def update_proposal_status(self, action_id: str, new_status: str, actor: str, notes: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if action_id not in self.proposals:
            return None
        proposal = self.proposals[action_id]
        proposal["status"] = new_status
        proposal["updatedAt"] = datetime.utcnow().isoformat() + "Z"
        if notes:
            proposal["notes"] = notes

        self.record_audit(
            actor=actor,
            action_type=f"ACTION_{new_status}",
            details={"actionId": action_id, "newStatus": new_status, "notes": notes}
        )
        return proposal

    def get_proposals(self, patient_id: Optional[str] = None) -> List[Dict[str, Any]]:
        all_props = list(self.proposals.values())
        if patient_id:
            return [p for p in all_props if p["patientId"] == patient_id]
        return all_props

    def get_audit_trail(self) -> List[Dict[str, Any]]:
        return [entry.to_dict() for entry in self.audit_log]

action_ledger = ActionLedger()
