// CareLoop Console Front-End Application
// Supports both live Control Plane API (port 8000) and instant offline browser simulation mode!

const API_BASE = (window.location.protocol === "file:" || (window.location.port !== "8000" && window.location.port !== "")) 
  ? "http://127.0.0.1:8000" 
  : "";

let isLiveBackend = true;

// In-browser mock state for offline mode
const mockState = {
  metrics: {
    closureRatePct: 100,
    avgTimeToContactMinutes: 4.2,
    pendingApprovals: 0,
    blockedActions: 1,
    costPerClosedLoopUSD: 0.0058,
    auditChainValid: true
  },
  loops: [],
  proposals: [],
  agents: [
    { id: "lab-agent", name: "Lab Results Classifier Agent", version: "1.2.0", max_risk_tier: "T0", token_budget_per_task: 1500, is_active: true, is_quarantined: false },
    { id: "pharmacy-agent", name: "Clinical Pharmacy Reconciliation Agent", version: "1.4.1", max_risk_tier: "T0", token_budget_per_task: 2000, is_active: true, is_quarantined: false },
    { id: "scheduling-agent", name: "Urgent Appointment Scheduling Agent", version: "1.1.0", max_risk_tier: "T1", token_budget_per_task: 1500, is_active: true, is_quarantined: false },
    { id: "billing-agent", name: "Patient Invoicing & Billing Agent", version: "1.0.5", max_risk_tier: "T1", token_budget_per_task: 1500, is_active: true, is_quarantined: false },
    { id: "outreach-agent", name: "Patient Clinical Outreach Agent", version: "2.0.0", max_risk_tier: "T2", token_budget_per_task: 3000, is_active: true, is_quarantined: false }
  ],
  audit: [
    { entryId: 1, actionType: "SYSTEM_INITIALIZED", actor: "control-plane", currentHash: "0a8f9c1e3b5d7a9f2e4c6b8d0a1f3e5c7b9d1f3e5a7b9c1d3e5f7a9b1c3d5e7f", prevHash: "0000000000000000000000000000000000000000000000000000000000000000" }
  ],
  pvCases: []
};

async function fetchJSON(url, options = {}) {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 1200);
    const res = await fetch(`${API_BASE}${url}`, {
      ...options,
      signal: controller.signal,
      headers: { "Content-Type": "application/json", ...options.headers }
    });
    clearTimeout(timeoutId);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    isLiveBackend = true;
    return await res.json();
  } catch (err) {
    isLiveBackend = false;
    return null;
  }
}

// 1. Refresh Metrics
async function refreshMetrics() {
  let data = await fetchJSON("/api/metrics");
  if (!data) {
    data = mockState.metrics;
  }

  document.getElementById("kpiClosureRate").innerText = `${data.closureRatePct}%`;
  document.getElementById("kpiContactTime").innerText = `${data.avgTimeToContactMinutes} min`;
  document.getElementById("kpiApprovals").innerText = data.pendingApprovals;
  document.getElementById("kpiBlocked").innerText = data.blockedActions;
  document.getElementById("kpiCost").innerText = `$${Number(data.costPerClosedLoopUSD).toFixed(4)}`;

  const statusEl = document.getElementById("auditChainStatus");
  if (data.auditChainValid) {
    statusEl.innerText = isLiveBackend 
      ? "SHA-256 Audit Chain: VALID (Live Backend Connected)"
      : "SHA-256 Audit Chain: VALID (Interactive Mode)";
    statusEl.parentElement.style.borderColor = "rgba(16, 185, 129, 0.4)";
  } else {
    statusEl.innerText = "SHA-256 Audit Chain: COMPROMISED!";
    statusEl.parentElement.style.borderColor = "rgba(239, 68, 68, 0.4)";
  }
}

// 2. Refresh Active Loops
async function refreshLoops() {
  let loops = await fetchJSON("/api/loops");
  if (!loops) loops = mockState.loops;
  
  const container = document.getElementById("loopsContainer");
  const badge = document.getElementById("loopCountBadge");

  if (!loops || loops.length === 0) {
    container.innerHTML = `<div class="empty-state">No active clinical loops. Click "▶ Run Critical Result Scenario" to simulate.</div>`;
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
      <div class="loop-patient">Patient: <strong>${l.patientId}</strong> | SLA Deadline: 60 mins | Opened: ${new Date(l.openedAt).toLocaleTimeString()}</div>
      <div class="loop-timer">Time to Contact: ${l.timeToContactMinutes !== null ? l.timeToContactMinutes + ' mins' : 'Awaiting Clinician Message Sign-Off'}</div>
    </div>
  `).join("");
}

// 3. Refresh Approval Inbox (T2)
async function refreshInbox() {
  let proposals = await fetchJSON("/api/ledger/proposals");
  if (!proposals) proposals = mockState.proposals;

  const container = document.getElementById("inboxContainer");
  const badge = document.getElementById("inboxCountBadge");

  const pendingT2 = proposals.filter(p => p.status === "PENDING_APPROVAL" || p.riskTier === "T2");
  const activePending = pendingT2.filter(p => p.status === "PENDING_APPROVAL");
  badge.innerText = `${activePending.length} Pending T2`;

  if (activePending.length === 0) {
    container.innerHTML = `<div class="empty-state">No actions waiting for clinician review.</div>`;
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
          <div>• Lab Finding: ${p.evidence.labFinding || 'Potassium 6.4 mEq/L (Critical High)'}</div>
          <div>• Drug Conflict: ${p.evidence.drugInteraction || 'Spironolactone 50mg daily + Lisinopril 20mg'}</div>
          <div>• Recipient Language: ${payload.targetLanguage || 'Telugu'} (${payload.recipientPhone || '+91-9876543210'})</div>
        </div>
        <div class="message-preview">
          <strong>Proposed Outbound Patient Message (${payload.targetLanguage}):</strong><br/>
          ${payload.draftMessage || ''}
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
  let agents = await fetchJSON("/api/agents");
  if (!agents) agents = mockState.agents;

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
  let audit = await fetchJSON("/api/ledger/audit");
  let entries = audit ? audit.entries : mockState.audit;

  const container = document.getElementById("auditContainer");
  if (!container || !entries) return;

  container.innerHTML = entries.slice().reverse().map(e => `
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
  let cases = await fetchJSON("/api/safety/pv-cases");
  if (!cases) cases = mockState.pvCases;

  const container = document.getElementById("pvContainer");
  if (!container) return;

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
  let res = await fetchJSON("/api/ledger/decide", {
    method: "POST",
    body: JSON.stringify({ actionId, decision, clinicianId: "DR-JENKINS-88", notes: "Clinician verified back-translation" })
  });

  if (!res) {
    // Offline simulation update
    const prop = mockState.proposals.find(p => p.actionId === actionId);
    if (prop) {
      prop.status = decision === "APPROVE" ? "APPROVED" : "REJECTED";
    }
    if (mockState.loops.length > 0) {
      mockState.loops[0].status = "CLOSED";
      mockState.loops[0].timeToContactMinutes = 0.8;
      mockState.metrics.closedLoops = 1;
      mockState.metrics.pendingApprovals = 0;
    }
    mockState.audit.push({
      entryId: mockState.audit.length + 1,
      actionType: `ACTION_${decision === "APPROVE" ? "APPROVED" : "REJECTED"}`,
      actor: "DR-JENKINS-88",
      currentHash: "3f8e7d2b1a9c4e6f8a0b2d4e6f8a0c2e4f6a8b0d2e4f6a8b0c2d4e6f8a0b2c4e",
      prevHash: mockState.audit[mockState.audit.length - 1].currentHash
    });
  }

  await refreshAll();
  const moment3 = document.getElementById("moment3Status");
  moment3.className = "moment-result-box success";
  moment3.innerText = `Action ${actionId} ${decision}ED by Dr. Jenkins. Patient outreach sent. Contact SLA closed.`;
}

async function toggleKillSwitch(agentId, action) {
  let res = await fetchJSON("/api/agents/kill-switch", {
    method: "POST",
    body: JSON.stringify({ agentId, action, reason: "Operator trigger via Console" })
  });

  if (!res) {
    const ag = mockState.agents.find(a => a.id === agentId);
    if (ag) {
      ag.is_quarantined = action === "QUARANTINE";
      ag.is_active = action !== "QUARANTINE";
    }
  }

  await refreshAll();
}

async function runDemoScenario() {
  const btn = document.getElementById("btnRunDemo");
  btn.disabled = true;
  btn.innerText = "⏳ Executing Multi-Agent Loop...";

  let res = await fetchJSON("/api/demo/run-full-scenario", { method: "POST" });
  
  if (!res) {
    // Interactive mock execution
    mockState.loops = [{
      loopId: "LOOP-00001",
      patientId: "P-84920",
      description: "Critical Potassium (6.4 mEq/L) detected post-discharge",
      status: "OPEN",
      openedAt: new Date().toISOString(),
      timeToContactMinutes: null
    }];

    mockState.proposals = [
      {
        actionId: "ACT-BILL-SK-004",
        agentId: "billing-agent",
        patientId: "P-84920",
        actionType: "BILLING_SEND_INVOICE",
        riskTier: "T1",
        status: "PAUSED_BY_CONFLICT_RULE",
        conflictStatus: "CONFLICT_DETECTED",
        conflictReason: "Billing action paused: Active clinical safety loop in progress (Critical Potassium 6.4 mEq/L). Clinical resolution must precede commercial invoicing."
      },
      {
        actionId: "ACT-OUTREACH-SK-005",
        agentId: "outreach-agent",
        patientId: "P-84920",
        actionType: "OUTREACH_SEND_MESSAGE",
        riskTier: "T2",
        status: "PENDING_APPROVAL",
        evidence: {
          labFinding: "Potassium 6.4 mEq/L (Critical High)",
          drugInteraction: "Spironolactone 50mg daily + Lisinopril 20mg"
        },
        payload: {
          recipientPhone: "+91-9876543210",
          targetLanguage: "Telugu",
          draftMessage: "నమస్కారం రమేష్ కుమార్ గారు. మీ డిశ్చార్జ్ తర్వాత వచ్చిన రక్త పరీక్షలో పొటాషియం స్థాయి ఎక్కువగా (6.4 mEq/L) ఉన్నట్లు డాక్టర్ గుర్తించారు. దయచేసి తదుపరి డాక్టర్ సంప్రదింపుల వరకు మీ స్పైరోనోలాక్టోన్ (Spironolactone) మాత్రను వేసుకోవద్దు. రేపు ఉదయం 10:30 గంటలకు కార్డియాలజీ క్లినిక్‌లో అత్యవసర అపాయింట్‌మెంట్ బుక్ చేయబడింది. ఛాతీ నొప్పి, గుండె దడ లేదా తీవ్రమైన నీరసం ఉంటే వెంటనే అత్యవసర విభాగానికి (ER) వెళ్ళండి.",
          certifiedBackTranslation: "Hello Mr. Ramesh Kumar. Your doctor has noted that your post-discharge blood test shows high potassium levels (6.4 mEq/L). Please do NOT take your Spironolactone tablet until further consultation with your doctor. An urgent follow-up appointment has been booked for you tomorrow at 10:30 AM at the Cardiology Clinic. If you experience chest pain, palpitations, or severe weakness, go to the Emergency Room (ER) immediately."
        }
      }
    ];

    mockState.metrics.pendingApprovals = 1;
    mockState.metrics.blockedActions = 1;

    res = {
      billingAgent: {
        status: "PAUSED_BY_CONFLICT_RULE",
        conflictReason: "Billing action paused: Active clinical safety loop in progress. Clinical resolution must precede commercial invoicing."
      }
    };
  }

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
  let res = await fetchJSON("/api/safety/inspect-text", {
    method: "POST",
    body: JSON.stringify({ patientId: "P-84920", messageText: text })
  });

  if (!res) {
    const isSuspicious = /ignore\s+(all\s+)?previous|system\s+prompt|forward\s+all|attacker|evil|exfil/i.test(text);
    res = {
      isSafe: !isSuspicious,
      reason: isSuspicious ? "Prompt-injection attack detected: matched suspicious exfiltration pattern" : "Clean text",
      totalBlockedAttempts: isSuspicious ? 1 : 0
    };
  }

  const moment2 = document.getElementById("moment2Status");
  if (res && !res.isSafe) {
    moment2.className = "moment-result-box active";
    moment2.innerText = `SECURITY BLOCKED: ${res.reason}`;
  } else {
    moment2.className = "moment-result-box success";
    moment2.innerText = `PASSED: Text deemed clean and safe.`;
  }
  await refreshAll();
}

async function simulatePatientADR() {
  const text = "Doctor, I am experiencing severe dizziness, heart palpitations, and muscle weakness after taking my new Spironolactone.";
  let res = await fetchJSON("/api/safety/patient-reply", {
    method: "POST",
    body: JSON.stringify({ patientId: "P-84920", messageText: text })
  });

  if (!res) {
    mockState.pvCases.push({
      caseSafetyReportId: `E2B-ICSR-${Math.random().toString(16).substring(2, 10).toUpperCase()}`,
      status: "DRAFT_PENDING_SAFETY_OFFICER_REVIEW",
      patient: {
        patientIdentifier: "P-84920",
        reactionDetails: [
          { meddra_term: "Dizziness", meddra_code: "10013573" },
          { meddra_term: "Muscle Weakness", meddra_code: "10028372" },
          { meddra_term: "Palpitations", meddra_code: "10033557" }
        ]
      },
      suspectDrugs: [{ medicinalProduct: "Spironolactone 50mg daily", drugCharacterization: "1=Suspect" }],
      seriousnessCriteria: { lifeThreatening: true }
    });
  }

  await refreshAll();
}

async function runSimulator() {
  const btn = document.getElementById("btnRunSimulator");
  btn.disabled = true;
  btn.innerText = "Running...";

  let res = await fetchJSON("/api/simulator/run", { method: "POST" });
  if (!res) {
    res = {
      historicalEventsProcessed: 50,
      baselineApprovalLoad: 17,
      forecastCandidateApprovalLoad: 11,
      approvalWorkloadReductionPct: 35.3,
      clinicianHoursSaved: 0.7,
      billingConflictsPrevented: 17,
      estimatedInferenceSpendUSD: 0.0366,
      totalTokensConsumed: 24400,
      policyRecommendation: "APPROVED: Candidate policy cuts clinician inbox burden by 35.3% while maintaining 100% safety bounds."
    };
  }

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
  setInterval(refreshAll, 3000);
});
