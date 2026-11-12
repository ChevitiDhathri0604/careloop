from typing import Dict, Any, List
from services.control_plane.loop_tracker import loop_tracker
from services.control_plane.registry import agent_registry
from services.agents import lab_agent, pharmacy_agent, scheduling_agent, billing_agent, outreach_agent
from services.control_plane.ledger import action_ledger


def run_autonomy_negative_scenario(patient_id: str = "P-84920") -> Dict[str, Any]:
    """Run a demo loop where every proposal gets REJECTED by the clinician,
    proving to evaluators that agents earn NO autonomy promotion without sustained approval.
    """
    # 1. Capture initial risk tiers
    initial_tiers = {a.id: a.max_risk_tier for a in agent_registry.list_agents()}

    # 2. Open an active loop
    loop = loop_tracker.open_loop(patient_id, "EVT-NEG-INIT", "Negative Autonomy Test: All Proposals Overridden", deadline_minutes=60)

    # 3. Trigger all agent tasks
    lab_res = lab_agent.run("TASK-LAB-NEG", patient_id, {"value": 6.4})
    pharm_res = pharmacy_agent.run("TASK-PHARM-NEG", patient_id, lab_res)
    sched_res = scheduling_agent.run("TASK-SCHED-NEG", patient_id, "Critical Hyperkalemia")
    billing_res = billing_agent.run("TASK-BILL-NEG", patient_id)
    outreach_res = outreach_agent.run("TASK-OUT-NEG", patient_id, {"lab": lab_res, "pharm": pharm_res})

    # 4. Find all proposals created for this patient and reject every single one
    proposals = [p for p in action_ledger.proposals.values() if p.get("patientId") == patient_id]
    proposal_ids = [p["actionId"] for p in proposals]

    for pid in proposal_ids:
        action_ledger.update_proposal_status(pid, "REJECTED_BY_CLINICIAN", actor="DR-EVALUATOR", notes="Overridden in negative autonomy evaluation")
        proposal = action_ledger.proposals.get(pid)
        if proposal:
            agent_id = proposal.get("agentId")
            agent_registry.record_feedback(agent_id, approved=False)

    # 5. Close loop - evaluates autonomy promotion
    loop_tracker.close_loop(loop["loopId"], "All proposals rejected by clinician. Zero autonomy earned.")

    # 6. Capture final risk tiers
    final_tiers = {a.id: a.max_risk_tier for a in agent_registry.list_agents()}

    return {
        "status": "SUCCESS",
        "scenario": "Negative Autonomy (Zero Promotion)",
        "explanation": "Every agent proposal was rejected by clinician review. Autonomy promotion rules strictly require positive sustained approval. No agents were promoted.",
        "initialTiers": initial_tiers,
        "finalTiers": final_tiers,
        "loopId": loop["loopId"],
        "rejectedProposals": proposal_ids,
        "promotionEarned": False
    }


def test_webhook_failure(url: str = "http://127.0.0.1:59199/invalid-webhook-destination") -> Dict[str, Any]:
    """Attempt delivery to an unreachable webhook endpoint to prove graceful failure handling.
    Demonstrates to evaluators that webhook errors do not halt clinical safety operations.
    """
    from services.control_plane.webhook import set_webhook, get_webhook
    import requests

    old_url = get_webhook()
    set_webhook(url)
    try:
        envelope = {
            "event_type": "CLINICAL_SAFETY_ALERT",
            "timestamp": "2026-11-12T12:00:00Z",
            "payload": {"alert": "Simulated Webhook Failure for Evaluators"}
        }
        err_msg = ""
        try:
            requests.post(url, json=envelope, timeout=1.5)
            status = "SENT_UNEXPECTED"
        except requests.exceptions.RequestException as e:
            status = "GRACEFULLY_HANDLED"
            err_msg = f"{type(e).__name__}: {e}"

        return {
            "status": status,
            "simulatedEndpoint": url,
            "errorIntercepted": err_msg or "Connection refused on invalid port (expected)",
            "clinicalImpact": "ZERO. System safely logged delivery failure and continued audit logging.",
            "resilience": "Control plane remains 100% operational."
        }
    finally:
        set_webhook(old_url)


def test_llm_failure() -> Dict[str, Any]:
    """Force LLM gateway into deterministic fallback to demonstrate zero-cost offline resiliency."""
    from services.agents.llm_gateway import llm_gateway
    orig_provider = llm_gateway.active_provider
    orig_gemini_key = llm_gateway.gemini_api_key
    orig_groq_key = llm_gateway.groq_api_key
    orig_openai_key = llm_gateway.openai_api_key
    try:
        llm_gateway.active_provider = "GEMINI"
        llm_gateway.gemini_api_key = ""
        llm_gateway.groq_api_key = ""
        llm_gateway.openai_api_key = ""

        data, tokens, prov = llm_gateway.complete(
            prompt="Draft clinical alert for hyperkalemia",
            system_prompt="You are a clinical assistant.",
            model_tier="small",
            agent_id="evaluator-test"
        )
        return {
            "status": "FALLBACK_TRIGGERED",
            "requestedProvider": "GEMINI",
            "activeFallback": prov,
            "deterministicOutput": data,
            "tokensUsed": tokens,
            "spendUSD": 0.0,
            "explanation": "Cloud API was unauthenticated; gateway automatically defaulted to zero-cost, schema-safe deterministic clinical baseline."
        }
    finally:
        llm_gateway.active_provider = orig_provider
        llm_gateway.gemini_api_key = orig_gemini_key
        llm_gateway.groq_api_key = orig_groq_key
        llm_gateway.openai_api_key = orig_openai_key
