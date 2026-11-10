import threading
from typing import Dict, List

# Simple in‑memory store for webhook URL (could be persisted later)
_webhook_url_lock = threading.Lock()
_webhook_url: str = ""

def set_webhook(url: str) -> None:
    """Register a webhook URL that will receive JSON POSTs for safety‑moment events.
    Overwrites any previously stored URL.
    """
    global _webhook_url
    with _webhook_url_lock:
        _webhook_url = url.strip()

def get_webhook() -> str:
    with _webhook_url_lock:
        return _webhook_url

class AutonomyManager:
    """Evaluates earned autonomy after a loop is closed.

    The policy is simple: for each agent that participated in the loop we compute
    the *override rate* = rejected approvals / total approvals. If the rate is below
    ``AUTONOMY_THRESHOLD`` the agent is promoted to the next risk tier (up to T3).
    The agent registry is updated in‑place.
    """

    AUTONOMY_THRESHOLD = 0.10  # 10% reject rate qualifies for promotion
    MAX_TIER = 3

    @staticmethod
    def evaluate_loop(loop_id: str) -> None:
        from .ledger import action_ledger
        from .registry import agent_registry

        # Find all actions linked to this loop (by loopId in action metadata)
        loop_actions = [a for a in action_ledger.actions if a.get("metadata", {}).get("loopId") == loop_id]
        # Group actions by agent_id
        actions_by_agent: Dict[str, List[Dict]] = {}
        for act in loop_actions:
            agent_id = act.get("metadata", {}).get("agentId")
            if not agent_id:
                continue
            actions_by_agent.setdefault(agent_id, []).append(act)

        for agent_id, acts in actions_by_agent.items():
            total = len(acts)
            rejects = sum(1 for a in acts if a.get("status") == "REJECTED")
            if total == 0:
                continue
            reject_rate = rejects / total
            # Fetch current tier
            agent_info = agent_registry.get_agent(agent_id)
            if not agent_info:
                continue
            current_tier = agent_info.get("riskTier", 0)
            # Promote if reject_rate below threshold and not already max tier
            if reject_rate <= AutonomyManager.AUTONOMY_THRESHOLD and current_tier < AutonomyManager.MAX_TIER:
                new_tier = current_tier + 1
                agent_registry.update_agent(agent_id, {"riskTier": new_tier})
                # Record promotion in audit ledger
                action_ledger.record_audit(
                    actor="autonomy-manager",
                    action_type="AGENT_TIER_PROMOTION",
                    details={
                        "agentId": agent_id,
                        "oldTier": current_tier,
                        "newTier": new_tier,
                        "loopId": loop_id,
                        "rejectRate": reject_rate,
                    }
                )
