package careloop.authz

default allow = false
default decision = "DENY"
default requires_approval = false

# Risk Tier T0: Pure read-only and analytical actions
allow {
    input.risk_tier == "T0"
    input.agent_active == true
    not input.agent_quarantined
}

decision = "ALLOW_AUTO" {
    input.risk_tier == "T0"
    input.agent_active == true
    not input.agent_quarantined
}

# Risk Tier T1: Low risk, reversible actions (e.g. appointment reservation)
allow {
    input.risk_tier == "T1"
    input.agent_active == true
    not input.agent_quarantined
}

decision = "ALLOW_AUTO" {
    input.risk_tier == "T1"
    input.agent_active == true
    not input.agent_quarantined
}

# Risk Tier T2: Moderate/High clinical risk (e.g. direct patient medical outreach)
requires_approval {
    input.risk_tier == "T2"
    input.agent_active == true
    not input.agent_quarantined
}

decision = "REQUIRE_APPROVAL" {
    input.risk_tier == "T2"
    input.agent_active == true
    not input.agent_quarantined
}

# Quarantined / Inactive Agent Kill-Switch
decision = "DENY_AGENT_QUARANTINED" {
    input.agent_quarantined == true
}

decision = "DENY_AGENT_INACTIVE" {
    input.agent_active == false
}
