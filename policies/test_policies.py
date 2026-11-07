"""
CareLoop Policy Unit Tests
Tests OPA risk tiers (T0-T3), agent activation status, emergency kill-switch quarantine,
and conflict detection rules.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from services.control_plane.risk_gate import risk_gate
from services.control_plane.registry import agent_registry
from services.control_plane.ledger import action_ledger
from services.control_plane.loop_tracker import loop_tracker

def test_risk_tier_t0():
    decision, reason = risk_gate.evaluate("lab-agent", "T0", "LAB_ANALYSIS", {})
    assert decision == "ALLOW_AUTO", f"Expected ALLOW_AUTO for T0, got {decision}"

def test_risk_tier_t1():
    decision, reason = risk_gate.evaluate("scheduling-agent", "T1", "SCHEDULING_BOOKING", {})
    assert decision == "ALLOW_AUTO", f"Expected ALLOW_AUTO for T1, got {decision}"

def test_risk_tier_t2_requires_approval():
    decision, reason = risk_gate.evaluate("outreach-agent", "T2", "OUTREACH_MESSAGE", {})
    assert decision == "REQUIRE_APPROVAL", f"Expected REQUIRE_APPROVAL for T2, got {decision}"

def test_agent_quarantine_kill_switch():
    agent_registry.quarantine_agent("lab-agent", "Security drill")
    decision, reason = risk_gate.evaluate("lab-agent", "T0", "LAB_ANALYSIS", {})
    assert decision == "DENY", f"Expected DENY for quarantined agent, got {decision}"
    # Restore
    agent_registry.get_agent("lab-agent").is_quarantined = False

def test_billing_conflict_rule():
    # Open a critical loop
    loop_tracker.open_loop("P-TEST-CONFLICT", "EVT-TEST", "Critical Potassium 6.5 mEq/L")
    has_conflict, reason = action_ledger.check_conflicts("P-TEST-CONFLICT", "BILLING_SEND_INVOICE")
    assert has_conflict is True, "Expected billing conflict to be detected while loop is open"
    assert "Billing action paused" in reason

def run_all_tests():
    test_risk_tier_t0()
    test_risk_tier_t1()
    test_risk_tier_t2_requires_approval()
    test_agent_quarantine_kill_switch()
    test_billing_conflict_rule()
    print("ALL POLICY UNIT TESTS PASSED (5/5)!")

if __name__ == "__main__":
    run_all_tests()
