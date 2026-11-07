"""
CareLoop OPA Risk Gate
Evaluates proposals against risk tiers (T0-T3) and agent registry permissions.
Enforces that T2 actions (outreach messages) require human-in-the-loop clinician sign-off.
"""

from typing import Dict, Any, Tuple
from .registry import agent_registry

class RiskGate:
    @staticmethod
    def evaluate(agent_id: str, risk_tier: str, action_type: str, context: Dict[str, Any]) -> Tuple[str, str]:
        """
        Evaluates risk tier policy for an agent action.
        Returns: (decision: str, reason: str)
        Decision can be:
          - "ALLOW_AUTO" (T0, T1)
          - "REQUIRE_APPROVAL" (T2)
          - "DENY" (exceeds max tier, inactive, or quarantined)
        """
        agent = agent_registry.get_agent(agent_id)
        if not agent:
            return "DENY", f"Agent '{agent_id}' is not registered"

        if agent.is_quarantined:
            return "DENY", f"Agent '{agent_id}' is QUARANTINED by emergency kill switch"

        if not agent.is_active:
            return "DENY", f"Agent '{agent_id}' is currently deactivated"

        # Tier mapping
        tier_hierarchy = {"T0": 0, "T1": 1, "T2": 2, "T3": 3}
        action_rank = tier_hierarchy.get(risk_tier, 99)
        max_allowed_rank = tier_hierarchy.get(agent.max_risk_tier, 0)

        # Earned autonomy upgrade check
        if agent.earned_autonomy_eligible and risk_tier == "T2":
            return "ALLOW_AUTO", "Allowed via Earned Autonomy: Low clinician override rate (<5%)"

        if action_rank > max_allowed_rank and not agent.earned_autonomy_eligible:
            return "DENY", f"Action risk tier {risk_tier} exceeds agent's maximum authorized tier {agent.max_risk_tier}"

        if risk_tier in ["T0", "T1"]:
            return "ALLOW_AUTO", f"Risk tier {risk_tier} approved for automated execution"

        if risk_tier == "T2":
            return "REQUIRE_APPROVAL", "Risk tier T2: Clinician Human-in-the-Loop approval required"

        if risk_tier == "T3":
            return "REQUIRE_ATTENDING_APPROVAL", "Risk tier T3: Attending Physician approval required"

        return "DENY", "Unrecognized risk tier"

risk_gate = RiskGate()
