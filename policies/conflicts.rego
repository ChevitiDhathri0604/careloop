package careloop.conflicts

default has_conflict = false
default conflict_reason = ""

# Safety Rule 1: Billing paused if active clinical issue / critical loop is open
has_conflict {
    input.action_domain == "BILLING"
    input.has_open_critical_loop == true
}

conflict_reason = "Billing action paused: Active clinical loop is in progress. Commercial invoice dispatch withheld." {
    input.action_domain == "BILLING"
    input.has_open_critical_loop == true
}
