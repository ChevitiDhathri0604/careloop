// CareLoop Console Front-End Application
// Connects to Control Plane API (port 8000 or relative /)

const API_BASE = window.location.port === "8080" ? "http://127.0.0.1:8000" : "";

async function fetchJSON(url, options = {}) {
  try {
    const res = await fetch(`${API_BASE}${url}`, {
      ...options,
      headers: { "Content-Type": "application/json", ...options.headers }
    });
    return await res.json();
  } catch (err) {
    console.error(`API Error on ${url}:`, err);
    return null;
  }
}

// 1. Refresh Metrics
async function refreshMetrics() {
  const data = await fetchJSON("/api/metrics");
  if (!data) return;

  document.getElementById("kpiClosureRate").innerText = `${data.closureRatePct}%`;
  document.getElementById("kpiContactTime").innerText = `${data.avgTimeToContactMinutes} min`;
  document.getElementById("kpiApprovals").innerText = data.pendingApprovals;
  document.getElementById("kpiBlocked").innerText = data.blockedActions;
  document.getElementById("kpiCost").innerText = `$${data.costPerClosedLoopUSD.toFixed(4)}`;

  const statusEl = document.getElementById("auditChainStatus");
  if (data.auditChainValid) {
    statusEl.innerText = "SHA-256 Audit Chain: VALID (Tamper-Proof)";
    statusEl.parentElement.style.borderColor = "rgba(16, 185, 129, 0.4)";
  } else {
    statusEl.innerText = "SHA-256 Audit Chain: COMPROMISED!";
    statusEl.parentElement.style.borderColor = "rgba(239, 68, 68, 0.4)";
  }
}

// 2. Refresh Active Loops
async function refreshLoops() {
  const loops = await fetchJSON("/api/loops");
  const container = document.getElementById("loopsContainer");
  const badge = document.getElementById("loopCountBadge");

  if (!loops || loops.length === 0) {
    container.innerHTML = `<div class="empty-state">No active clinical loops. Click "Run Critical Result Scenario" to simulate.</div>`;
    badge.innerText = "0 Active";
    return;
  }

  badge.innerText = `${loops.length} Active`;
  container.innerHTML = loops.map(l => `
    <div class="loop-item">
      <div class="loop-header">
        <span class="loop-title">${l.loopId}: ${l.description}</span>
        <span class="badge ${l.status === 'CLOSED' ? 'badge-green' : 'badge-amber'}">${l.status}</span>
      </div>
      <div class="loop-patient">Patient: <strong>${l.patientId}</strong> | Deadline: 60 mins | Opened: ${new Date(l.openedAt).toLocaleTimeString()}</div>
      <div class="loop-timer">Time to Contact: ${l.timeToContactMinutes !== null ? l.timeToContactMinutes + ' mins' : 'Awaiting Clinician Message Approval'}</div>
    </div>
  `).join("");
}

// 3. Refresh Approval Inbox (T2)
async function refreshInbox() {
  const proposals = await fetchJSON("/api/ledger/proposals");
  const container = document.getElementById("inboxContainer");
  const badge = document.getElementById("inboxCountBadge");

  if (!proposals) return;

  const pendingT2 = proposals.filter(p => p.status === "PENDING_APPROVAL" || p.riskTier === "T2");
  badge.innerText = `${pendingT2.filter(p => p.status === "PENDING_APPROVAL").length} Pending T2`;

  const activePending = pendingT2.filter(p => p.status === "PENDING_APPROVAL");

  if (activePending.length === 0) {
    container.innerHTML = `<div class="empty-state">No pending actions waiting for clinician review.</div>`;
    return;
  }

  container.innerHTML = activePending.map(p => {
    const payload = p.payload || {};
    return `
      <div class="approval-card">
        <div class="approval-meta">
          <strong>Action: ${p.actionId}</strong>
          <span class="badge badge-amber">Risk Tier: ${p.riskTier} (Human Sign-off Required)</span>
        </div>
        <div class="evidence-box">
          <div class="evidence-title">Clinical Trigger & Safety Evidence:</div>
          <div>• Lab Finding: ${p.evidence.labFinding || 'Potassium 6.4 mEq/L'}</div>
          <div>• Drug Conflict: ${p.evidence.drugInteraction || 'Spironolactone 50mg daily'}</div>
          <div>• Recipient Language: ${payload.targetLanguage || 'Telugu'} (${payload.recipientPhone || ''})</div>
        </div>
        <div class="message-preview">
          <strong>Proposed Outbound Patient Message (${payload.targetLanguage}):</strong><br/>
          ${payload.draftMessage || 'Drafting message...'}
        </div>
        <div class="back-translation">
          <strong>Certified Back-Translation for Clinician Verification:</strong><br/>
          "${payload.certifiedBackTranslation || ''}"
        </div>
        <div class="action-buttons">
          <button class="btn btn-approve btn-xs" onclick="decideAction('${p.actionId}', 'APPROVE')">✔ Approve & Send Immediately</button>
          <button class="btn btn-reject btn-xs" onclick="decideAction('${p.actionId}', 'REJECT')">✖ Override / Reject</button>
        </div>
      </div>
    `;
  }).join("");
}

// 4. Refresh Agent Registry & Kill Switches
async function refreshAgents() {
  const agents = await fetchJSON("/api/agents");
  const container = document.getElementById("agentsContainer");
  if (!agents || !container) return;

  container.innerHTML = agents.map(a => {
    const isQuarantined = a.is_quarantined;
    return `
      <div class="agent-row">
        <div class="agent-info">
          <span class="agent-name">${a.name} (v${a.version})</span>
          <span class="agent-sub">Max Risk: <strong>${a.max_risk_tier}</strong> | Budget: ${a.token_budget_per_task} tokens</span>
        </div>
        <div class="agent-actions">
          <span class="badge ${isQuarantined ? 'badge-red' : 'badge-green'}">${isQuarantined ? 'QUARANTINED' : 'ACTIVE'}</span>
          <button class="btn btn-xs ${isQuarantined ? 'btn-primary' : 'btn-outline'}" onclick="toggleKillSwitch('${a.id}', '${isQuarantined ? 'RESTORE' : 'QUARANTINE'}')">
            ${isQuarantined ? 'Restore' : 'Kill Switch'}
          </button>
        </div>
      </div>
    `;
  }).join("");
}

// 5. Refresh Audit Trail
async function refreshAudit() {
  const audit = await fetchJSON("/api/ledger/audit");
  const container = document.getElementById("auditContainer");
  if (!audit || !container) return;

  container.innerHTML = audit.entries.slice().reverse().map(e => `
    <div class="audit-entry-row">
      <div class="audit-entry-top">
        <span>#${e.entryId} <strong>${e.actionType}</strong></span>
        <span>${e.actor}</span>
      </div>
      <div class="audit-hash">Hash: ${e.currentHash.substring(0, 32)}... (prev: ${e.prevHash.substring(0, 16)}...)</div>
    </div>
  `).join("");
}

// 6. Refresh Pharmacovigilance Cases
async function refreshPVCases() {
  const cases = await fetchJSON("/api/safety/pv-cases");
  const container = document.getElementById("pvContainer");
  if (!cases || !container) return;

  if (cases.length === 0) {
    container.innerHTML = `<div class="empty-state">No adverse drug events drafted. Click "Simulate Patient ADR Reply" above.</div>`;
    return;
  }

  container.innerHTML = cases.map(c => `
    <div class="evidence-box" style="margin-bottom: 8px;">
      <div class="evidence-title">ICH-E2B(R3) Draft: ${c.caseSafetyReportId}</div>
      <div>• Patient: ${c.patient.patientIdentifier} | Seriousness: Life-Threatening=${c.seriousnessCriteria.lifeThreatening}</div>
      <div>• Reactions: ${c.patient.reactionDetails.map(r => r.meddra_term).join(", ")}</div>
      <div>• Suspect Drug: ${c.suspectDrugs.map(d => d.medicinalProduct + ' (' + d.drugCharacterization + ')').join(", ")}</div>
      <div style="font-size:10px; color:#94a3b8; margin-top:4px;">Status: ${c.status}</div>
    </div>
  `).join("");
}

// Handlers
async function decideAction(actionId, decision) {
  await fetchJSON("/api/ledger/decide", {
    method: "POST",
    body: JSON.stringify({ actionId, decision, clinicianId: "DR-JENKINS-88", notes: "Clinician verified back-translation" })
  });
  await refreshAll();
  document.getElementById("moment3Status").className = "moment-result-box success";
  document.getElementById("moment3Status").innerText = `Action ${actionId} ${decision}ED by Dr. Jenkins. Patient outreach sent. Contact SLA closed.`;
}

async function toggleKillSwitch(agentId, action) {
  await fetchJSON("/api/agents/kill-switch", {
    method: "POST",
    body: JSON.stringify({ agentId, action, reason: "Operator trigger via Console" })
  });
  await refreshAll();
}

async function runDemoScenario() {
  const btn = document.getElementById("btnRunDemo");
  btn.disabled = true;
  btn.innerText = "⏳ Executing Multi-Agent Loop...";

  const res = await fetchJSON("/api/demo/run-full-scenario", { method: "POST" });
  
  btn.disabled = false;
  btn.innerText = "▶ Run Critical Result Scenario";

  // Update Safety Moment 1 Box
  const moment1 = document.getElementById("moment1Status");
  if (res && res.billingAgent && res.billingAgent.status === "PAUSED_BY_CONFLICT_RULE") {
    moment1.className = "moment-result-box active";
    moment1.innerText = `BLOCKED LIVE: ${res.billingAgent.conflictReason}`;
  }

  // Update Safety Moment 3 Box
  const moment3 = document.getElementById("moment3Status");
  moment3.className = "moment-result-box active";
  moment3.innerText = "WAITING: Outreach Agent (T2) message queued in Clinician Inbox with back-translation.";

  await refreshAll();
}

async function testPromptInjection() {
  const text = document.getElementById("injectionInput").value;
  const res = await fetchJSON("/api/safety/inspect-text", {
    method: "POST",
    body: JSON.stringify({ patientId: "P-84920", messageText: text })
  });

  const moment2 = document.getElementById("moment2Status");
  if (res && !res.isSafe) {
    moment2.className = "moment-result-box active";
    moment2.innerText = `SECURITY BLOCKED: ${res.reason} (Total blocked: ${res.totalBlockedAttempts})`;
  } else {
    moment2.className = "moment-result-box success";
    moment2.innerText = `PASSED: Text deemed clean and safe.`;
  }
  await refreshAll();
}

async function simulatePatientADR() {
  const text = "Doctor, I am experiencing severe dizziness, heart palpitations, and muscle weakness after taking my new Spironolactone.";
  await fetchJSON("/api/safety/patient-reply", {
    method: "POST",
    body: JSON.stringify({ patientId: "P-84920", messageText: text })
  });
  await refreshAll();
}

async function runSimulator() {
  const btn = document.getElementById("btnRunSimulator");
  btn.disabled = true;
  btn.innerText = "Running...";

  const res = await fetchJSON("/api/simulator/run", { method: "POST" });
  btn.disabled = false;
  btn.innerText = "Run Policy Forecast";

  const container = document.getElementById("simulatorContainer");
  if (res && container) {
    container.innerHTML = `
      <div class="evidence-box">
        <div class="evidence-title">Forecast Report (${res.historicalEventsProcessed} Recorded Events Replayed)</div>
        <div>• Baseline Approvals: <strong>${res.baselineApprovalLoad}</strong> ➔ Candidate: <strong>${res.candidateApprovalLoad || res.forecastCandidateApprovalLoad}</strong></div>
        <div>• Clinician Workload Reduction: <strong style="color:#34d399;">${res.approvalWorkloadReductionPct}%</strong> (${res.clinicianHoursSaved} hrs saved)</div>
        <div>• Commercial Invoicing Conflicts Prevented: <strong>${res.billingConflictsPrevented}</strong></div>
        <div>• Inference Cost: <strong>$${res.estimatedInferenceSpendUSD}</strong> (${res.totalTokensConsumed} tokens)</div>
        <div style="font-size:11px; color:#38bdf8; margin-top:4px;">${res.policyRecommendation}</div>
      </div>
    `;
  }
}

async function refreshAll() {
  await Promise.all([
    refreshMetrics(),
    refreshLoops(),
    refreshInbox(),
    refreshAgents(),
    refreshAudit(),
    refreshPVCases()
  ]);
}

// Event Listeners
document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("btnRunDemo").addEventListener("click", runDemoScenario);
  document.getElementById("btnTestInjection").addEventListener("click", testPromptInjection);
  document.getElementById("btnSimulateSideEffect").addEventListener("click", simulatePatientADR);
  document.getElementById("btnRunSimulator").addEventListener("click", runSimulator);

  refreshAll();
  // Poll every 3 seconds for live dashboard updates
  setInterval(refreshAll, 3000);
});
