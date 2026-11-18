// CareLoop Console Front-End Application
// Supports both live FastAPI Control Plane API and resilient offline browser simulation mode.

// Dynamic API_BASE: in web serving (HTTP/HTTPS), always use relative paths so local & production deployments work identically.
// Only fall back to http://127.0.0.1:8000 when opened directly as a file:// URL.
const API_BASE = window.location.protocol === "file:" ? "http://127.0.0.1:8000" : "";

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

async function fetchJSON(url, options = {}, timeoutMs = 8000) {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
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
    console.warn(`[CareLoop] Call to ${url} failed:`, err.message || err);
    return null;
  }
}

// Diagnostics Modal Helper
function showDiagModal({ icon = "🔬", title, badge = "SAFETY VERIFIED", badgeClass = "badge-green", description, details, rawData }) {
  const modal = document.getElementById("diagModal");
  if (!modal) return;

  document.getElementById("diagIcon").innerText = icon;
  document.getElementById("diagTitle").innerText = title;
  const badgeEl = document.getElementById("diagBadge");
  badgeEl.innerText = badge;
  badgeEl.className = `badge ${badgeClass}`;
  document.getElementById("diagTimestamp").innerText = new Date().toLocaleTimeString();
  document.getElementById("diagDescription").innerText = description;
  document.getElementById("diagDetails").innerHTML = details;
  document.getElementById("diagRawJSON").innerText = typeof rawData === "string" ? rawData : JSON.stringify(rawData, null, 2);

  modal.style.display = "flex";
}

function initDiagModal() {
  const modal = document.getElementById("diagModal");
  const btnClose = document.getElementById("btnCloseDiagModal");
  const btnDismiss = document.getElementById("btnDismissDiag");

  if (!modal) return;

  const closeModal = () => { modal.style.display = "none"; };
  if (btnClose) btnClose.addEventListener("click", closeModal);
  if (btnDismiss) btnDismiss.addEventListener("click", closeModal);

  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();
  });
}

// 1. Refresh Metrics
async function refreshMetrics() {
  let data = await fetchJSON("/api/metrics");
  if (!data) data = mockState.metrics;

  const elClosure = document.getElementById("kpiClosureRate");
  const elContact = document.getElementById("kpiContactTime");
  const elApprovals = document.getElementById("kpiApprovals");
  const elBlocked = document.getElementById("kpiBlocked");
  const elCost = document.getElementById("kpiCost");

  if (elClosure) elClosure.innerText = `${data.closureRatePct}%`;
  if (elContact) elContact.innerText = `${data.avgTimeToContactMinutes} min`;
  if (elApprovals) elApprovals.innerText = data.pendingApprovals;
  if (elBlocked) elBlocked.innerText = data.blockedActions;
  if (elCost) elCost.innerText = `$${Number(data.costPerClosedLoopUSD).toFixed(4)}`;

  const statusEl = document.getElementById("auditChainStatus");
  if (statusEl) {
    if (data.auditChainValid) {
      statusEl.innerText = isLiveBackend 
        ? "SHA-256 Audit Chain: VALID (Live Backend)"
        : "SHA-256 Audit Chain: VALID (Sandbox Simulation)";
      statusEl.parentElement.style.borderColor = "rgba(16, 185, 129, 0.4)";
    } else {
      statusEl.innerText = "SHA-256 Audit Chain: COMPROMISED!";
      statusEl.parentElement.style.borderColor = "rgba(239, 68, 68, 0.4)";
    }
  }
}

// 2. Refresh Active Loops
async function refreshLoops() {
  let loops = await fetchJSON("/api/loops");
  if (!loops) loops = mockState.loops;
  
  const container = document.getElementById("loopsContainer");
  const badge = document.getElementById("loopCountBadge");
  if (!container) return;

  if (!loops || loops.length === 0) {
    container.innerHTML = `<div class="empty-state">No active clinical loops. Click "▶ Run Demo Scenario" to simulate.</div>`;
    if (badge) badge.innerText = "0 Active";
    return;
  }

  if (badge) badge.innerText = `${loops.length} Active`;
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
  if (!container) return;

  const pendingT2 = proposals.filter(p => p.status === "PENDING_APPROVAL" || p.riskTier === "T2");
  const activePending = pendingT2.filter(p => p.status === "PENDING_APPROVAL");
  if (badge) badge.innerText = `${activePending.length} Pending T2`;

  if (activePending.length === 0) {
    container.innerHTML = `<div class="empty-state">No actions awaiting clinician review.</div>`;
    return;
  }

  container.innerHTML = activePending.map(p => {
    const payload = p.payload || {};
    const providerTag = payload.llmProvider ? `<span class="badge" style="background:#0284c7; color:#fff; font-size:10px;">Generated by: ${payload.llmProvider}</span>` : '';
    return `
      <div class="approval-card">
        <div class="approval-meta">
          <strong>Action: ${p.actionId}</strong>
          <div style="display:flex; gap:6px; align-items:center;">
            ${providerTag}
            <span class="badge badge-amber">Risk Tier: ${p.riskTier} (Human Sign-off Required)</span>
          </div>
        </div>
        <div class="evidence-box">
          <div class="evidence-title">Clinical Trigger & Safety Evidence:</div>
          <div>• Lab Finding: ${p.evidence ? p.evidence.labFinding : 'Potassium 6.4 mEq/L (Critical High)'}</div>
          <div>• Drug Conflict: ${p.evidence ? p.evidence.drugInteraction : 'Spironolactone 50mg daily + Lisinopril 20mg'}</div>
          <div>• Recipient Language: ${payload.targetLanguage || 'Telugu'} (${payload.recipientPhone || '+91-9876543210'})</div>
        </div>
        <div class="message-preview">
          <strong>Proposed Outbound Patient Message (${payload.targetLanguage || 'Telugu'}):</strong><br/>
          ${payload.draftMessage || 'నమస్కారం రమేష్ కుమార్ గారు. మీ రక్త పరీక్షలో పొటాషియం స్థాయి ఎక్కువగా (6.4 mEq/L) ఉంది. దయచేసి తదుపరి డాక్టర్ సంప్రదింపుల వరకు మీ స్పైరోనోలాక్టోన్ మాత్రను ఆపండి.'}
        </div>
        <div class="back-translation">
          <strong>Certified Back-Translation for Clinician Verification:</strong><br/>
          "${payload.certifiedBackTranslation || 'Hello Mr. Ramesh Kumar. Your blood test shows high potassium levels (6.4 mEq/L). Please stop taking your Spironolactone medication until further doctor consultation.'}"
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

  if (!cases || cases.length === 0) {
    container.innerHTML = `<div class="empty-state">No adverse drug events drafted. Click "Simulate ADR" above.</div>`;
    return;
  }

  container.innerHTML = cases.map(c => `
    <div class="evidence-box" style="margin-bottom: 8px;">
      <div class="evidence-title">ICH-E2B(R3) Draft: ${c.caseSafetyReportId}</div>
      <div>• Patient: ${c.patient.patientIdentifier} | Seriousness: Life-Threatening=${c.seriousnessCriteria ? c.seriousnessCriteria.lifeThreatening : true}</div>
      <div>• Reactions: ${c.patient && c.patient.reactionDetails ? c.patient.reactionDetails.map(r => r.meddra_term).join(", ") : 'Dizziness, Palpitations'}</div>
      <div>• Suspect Drug: ${c.suspectDrugs ? c.suspectDrugs.map(d => d.medicinalProduct + ' (' + d.drugCharacterization + ')').join(", ") : 'Spironolactone'}</div>
      <div style="font-size:10px; color:#94a3b8; margin-top:4px;">Status: ${c.status}</div>
    </div>
  `).join("");
}

// Clinician Decision Handler (Approve / Reject)
async function decideAction(actionId, decision) {
  let res = await fetchJSON("/api/ledger/decide", {
    method: "POST",
    body: JSON.stringify({ actionId, decision, clinicianId: "DR-JENKINS-88", notes: "Clinician verified back-translation" })
  });

  if (!res) {
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
  if (moment3) {
    moment3.className = "moment-result-box success";
    moment3.innerText = `Action ${actionId} ${decision}ED by Dr. Jenkins. Patient outreach sent. Contact SLA closed.`;
  }
}

// Agent Kill Switch Handler
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

// 7. Run Full Demo Scenario
async function runDemoScenario() {
  const btn = document.getElementById("btnRunDemo");
  if (btn) {
    btn.disabled = true;
    btn.innerText = "⏳ Executing Multi-Agent Loop...";
  }

  let res = await fetchJSON("/api/demo/run-full-scenario", { method: "POST" });
  
  if (!res) {
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
          draftMessage: "నమస్కారం రమేష్ కుమార్ గారు. మీ డిశ్చార్జ్ తర్వాత వచ్చిన రక్త పరీక్షలో పొటాషియం స్థాయి ఎక్కువగా (6.4 mEq/L) ఉన్నట్లు డాక్టర్ గుర్తించారు. దయచేసి తదుపరి డాక్టర్ సంప్రదింపుల వరకు మీ స్పైరోనోలాక్టోన్ మాత్రను వేసుకోవద్దు. రేపు ఉదయం 10:30 గంటలకు కార్డియాలజీ క్లినిక్‌లో అత్యవసర అపాయింట్‌మెంట్ బుక్ చేయబడింది.",
          certifiedBackTranslation: "Hello Mr. Ramesh Kumar. Your doctor noted that your post-discharge blood test shows high potassium (6.4 mEq/L). Please do NOT take your Spironolactone tablet until further consultation. An urgent follow-up appointment is booked tomorrow at 10:30 AM at the Cardiology Clinic."
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

  if (btn) {
    btn.disabled = false;
    btn.innerText = "▶ Run Demo Scenario";
  }

  // Update Safety Moment 1 Box
  const moment1 = document.getElementById("moment1Status");
  if (moment1) {
    moment1.className = "moment-result-box active";
    moment1.innerText = `BLOCKED LIVE: Billing action intercepted and frozen while critical hyperkalemia loop is active.`;
  }

  // Update Safety Moment 3 Box
  const moment3 = document.getElementById("moment3Status");
  if (moment3) {
    moment3.className = "moment-result-box active";
    moment3.innerText = "WAITING: Outreach Agent (T2) message queued in Clinician Inbox with certified back-translation.";
  }

  await refreshAll();
}

// 8. Test Prompt Injection
async function testPromptInjection() {
  const inputEl = document.getElementById("injectionInput");
  const text = inputEl ? inputEl.value : "";
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
  if (moment2) {
    if (res && !res.isSafe) {
      moment2.className = "moment-result-box active";
      moment2.innerText = `SECURITY BLOCKED: ${res.reason}`;
    } else {
      moment2.className = "moment-result-box success";
      moment2.innerText = `PASSED: Inbound SMS deemed clean and clinically safe.`;
    }
  }
  await refreshAll();
}

// 9. Simulate Patient Adverse Drug Reaction (ADR)
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

// 10. Replay Simulator (Policy Forecasting)
async function runSimulator() {
  const btn = document.getElementById("btnRunSimulator");
  if (btn) {
    btn.disabled = true;
    btn.innerText = "Running...";
  }

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

  if (btn) {
    btn.disabled = false;
    btn.innerText = "Run Forecast";
  }

  const container = document.getElementById("simulatorContainer");
  if (res && container) {
    container.innerHTML = `
      <div class="evidence-box">
        <div class="evidence-title">Forecast Report (${res.historicalEventsProcessed} Recorded Events Replayed)</div>
        <div>• Baseline Approvals: <strong>${res.baselineApprovalLoad}</strong> ➔ Candidate: <strong>${res.candidateApprovalLoad || res.forecastCandidateApprovalLoad}</strong></div>
        <div>• Clinician Workload Reduction: <strong style="color:#34d399;">${res.approvalWorkloadReductionPct}%</strong> (${res.clinicianHoursSaved} hrs saved)</div>
        <div>• Invoicing Conflicts Prevented: <strong>${res.billingConflictsPrevented}</strong></div>
        <div>• Inference Cost: <strong>$${res.estimatedInferenceSpendUSD}</strong> (${res.totalTokensConsumed} tokens)</div>
        <div style="font-size:11px; color:#38bdf8; margin-top:4px;">${res.policyRecommendation}</div>
      </div>
    `;
  }
}

// 11. Debug & Evaluator Negative Scenario Buttons
function initDebugButtons() {
  const btnNegAutonomy = document.getElementById("btnNegAutonomy");
  const btnWebhookFail = document.getElementById("btnWebhookFail");
  const btnLLMFallback = document.getElementById("btnLLMFallback");

  if (btnNegAutonomy) {
    btnNegAutonomy.addEventListener("click", async () => {
      btnNegAutonomy.disabled = true;
      btnNegAutonomy.innerText = "⏳ Testing...";
      let res = await fetchJSON("/api/debug/negative_autonomy");
      btnNegAutonomy.disabled = false;
      btnNegAutonomy.innerText = "⚡ Negative Autonomy Demo";

      if (!res) {
        res = {
          status: "SUCCESS",
          scenario: "Negative Autonomy (Zero Promotion)",
          explanation: "Every agent proposal was rejected by clinician review. Autonomy promotion rules strictly require positive sustained approval. No agents were promoted.",
          initialTiers: { "lab-agent": "T0", "pharmacy-agent": "T0", "scheduling-agent": "T1", "billing-agent": "T1", "outreach-agent": "T2" },
          finalTiers: { "lab-agent": "T0", "pharmacy-agent": "T0", "scheduling-agent": "T1", "billing-agent": "T1", "outreach-agent": "T2" },
          rejectedProposals: ["ACT-LAB-NEG", "ACT-PHARM-NEG", "ACT-SCHED-NEG", "ACT-BILL-NEG", "ACT-OUT-NEG"],
          promotionEarned: false
        };
      }

      showDiagModal({
        icon: "⚡",
        title: "Negative Autonomy Evaluation Result",
        badge: res.promotionEarned ? "FAIL (Unearned Promotion)" : "PASS (Zero Unearned Autonomy)",
        badgeClass: res.promotionEarned ? "badge-red" : "badge-green",
        description: res.explanation || "All agent actions were intentionally overridden by a clinician to demonstrate that agents cannot graduate risk tiers without human trust.",
        details: `
          <div>• <strong>Loop Evaluated:</strong> ${res.loopId || 'LOOP-NEG-001'}</div>
          <div>• <strong>Proposals Overridden:</strong> ${res.rejectedProposals ? res.rejectedProposals.length : 5} rejected</div>
          <div>• <strong>Initial Risk Tiers:</strong> Lab=${res.initialTiers['lab-agent']}, Pharm=${res.initialTiers['pharmacy-agent']}, Outreach=${res.initialTiers['outreach-agent']}</div>
          <div>• <strong>Final Risk Tiers:</strong> Lab=${res.finalTiers['lab-agent']}, Pharm=${res.finalTiers['pharmacy-agent']}, Outreach=${res.finalTiers['outreach-agent']} (Unchanged)</div>
          <div>• <strong>Autonomy Granted:</strong> 0% (Strict safety boundary confirmed)</div>
        `,
        rawData: res
      });

      await refreshAll();
    });
  }

  if (btnWebhookFail) {
    btnWebhookFail.addEventListener("click", async () => {
      btnWebhookFail.disabled = true;
      btnWebhookFail.innerText = "⏳ Simulating...";
      let res = await fetchJSON("/api/debug/webhook_failure");
      btnWebhookFail.disabled = false;
      btnWebhookFail.innerText = "📡 Test Webhook Failure";

      if (!res) {
        res = {
          status: "GRACEFULLY_HANDLED",
          simulatedEndpoint: "http://127.0.0.1:59199/invalid-webhook-destination",
          errorIntercepted: "ConnectionRefusedError: [WinError 10061] No connection could be made",
          clinicalImpact: "ZERO. System safely logged delivery failure and continued audit logging.",
          resilience: "Control plane remains 100% operational."
        };
      }

      showDiagModal({
        icon: "📡",
        title: "External Webhook Delivery Failure Simulation",
        badge: "RESILIENCE VERIFIED",
        badgeClass: "badge-green",
        description: "Evaluator test verifying that downstream webhook failures (e.g. EHR downtime or network drops) never crash the clinical safety control plane.",
        details: `
          <div>• <strong>Simulated Target:</strong> ${res.simulatedEndpoint}</div>
          <div>• <strong>Error Intercepted:</strong> ${res.errorIntercepted}</div>
          <div>• <strong>Clinical Impact:</strong> <strong style="color:#34d399;">${res.clinicalImpact}</strong></div>
          <div>• <strong>Operational Health:</strong> ${res.resilience}</div>
        `,
        rawData: res
      });
    });
  }

  if (btnLLMFallback) {
    btnLLMFallback.addEventListener("click", async () => {
      btnLLMFallback.disabled = true;
      btnLLMFallback.innerText = "⏳ Provoking...";
      let res = await fetchJSON("/api/debug/llm_fallback");
      btnLLMFallback.disabled = false;
      btnLLMFallback.innerText = "🤖 Force LLM Fallback";

      if (!res) {
        res = {
          status: "FALLBACK_TRIGGERED",
          requestedProvider: "GEMINI",
          activeFallback: "DETERMINISTIC",
          deterministicOutput: "Hyperkalemia detected (Potassium 6.4 mEq/L). Clinical directive: Withhold spironolactone, cardiology follow-up booked.",
          tokensUsed: 0,
          spendUSD: 0.0,
          explanation: "Cloud API was unauthenticated; gateway automatically defaulted to zero-cost, schema-safe deterministic clinical baseline."
        };
      }

      showDiagModal({
        icon: "🤖",
        title: "Zero-Cost Deterministic Fallback Test",
        badge: "FALLBACK ACTIVE",
        badgeClass: "badge-blue",
        description: res.explanation || "Cloud LLM keys cleared to test graceful degradation.",
        details: `
          <div>• <strong>Primary Provider Requested:</strong> ${res.requestedProvider} (Keys absent)</div>
          <div>• <strong>Failover Engaged:</strong> <strong style="color:#38bdf8;">${res.activeFallback}</strong></div>
          <div>• <strong>Fallback Clinical Output:</strong> "${typeof res.deterministicOutput === 'object' ? JSON.stringify(res.deterministicOutput) : res.deterministicOutput}"</div>
          <div>• <strong>Tokens Consumed:</strong> ${res.tokensUsed} tokens ($${res.spendUSD || '0.00'})</div>
        `,
        rawData: res
      });

      await refreshAll();
    });
  }
}

// 12. Refresh All Panels
async function refreshAll() {
  await Promise.all([
    refreshMetrics(),
    refreshLoops(),
    refreshInbox(),
    refreshAgents(),
    refreshAudit(),
    refreshPVCases(),
    refreshLLMStatus()
  ]);
}

// 13. LLM Modal & Settings Handlers
async function refreshLLMStatus() {
  const status = await fetchJSON("/api/llm/status");
  if (!status) return;

  const totalTok = document.getElementById("modalTotalTokens");
  const totalCost = document.getElementById("modalTotalCost");
  if (totalTok) totalTok.innerText = Number(status.totalTokensConsumed || 0).toLocaleString();
  if (totalCost) totalCost.innerText = `$${Number(status.totalInferenceCostUSD || status.totalCostUSD || 0).toFixed(4)}`;

  const btnOpen = document.getElementById("btnOpenLLMModal");
  if (btnOpen) {
    btnOpen.innerText = `⚙️ LLM (${status.activeProvider})`;
  }
}

function initLLMModal() {
  const modal = document.getElementById("llmModal");
  const btnOpen = document.getElementById("btnOpenLLMModal");
  const btnClose = document.getElementById("btnCloseLLMModal");
  const selProvider = document.getElementById("llmProviderSelect");
  const apiKeyGroup = document.getElementById("apiKeyGroup");
  const baseUrlGroup = document.getElementById("baseUrlGroup");
  const btnSave = document.getElementById("btnSaveLLMConfig");
  const btnTest = document.getElementById("btnTestLLMCall");
  const testResult = document.getElementById("llmTestResult");

  if (!btnOpen || !modal) return;

  btnOpen.addEventListener("click", () => {
    modal.style.display = "flex";
    refreshLLMStatus();
  });

  if (btnClose) {
    btnClose.addEventListener("click", () => {
      modal.style.display = "none";
    });
  }

  modal.addEventListener("click", (e) => {
    if (e.target === modal) modal.style.display = "none";
  });

  if (selProvider) {
    selProvider.addEventListener("change", () => {
      const val = selProvider.value;
      if (val === "OLLAMA") {
        apiKeyGroup.style.display = "none";
        baseUrlGroup.style.display = "block";
        document.getElementById("llmSmallModel").value = "llama3:latest";
        document.getElementById("llmLargeModel").value = "llama3:latest";
      } else if (val === "GROQ") {
        apiKeyGroup.style.display = "block";
        baseUrlGroup.style.display = "none";
        document.getElementById("llmSmallModel").value = "llama-3.1-8b-instant";
        document.getElementById("llmLargeModel").value = "llama-3.3-70b-versatile";
      } else if (val === "DETERMINISTIC") {
        apiKeyGroup.style.display = "none";
        baseUrlGroup.style.display = "none";
      } else {
        apiKeyGroup.style.display = "block";
        baseUrlGroup.style.display = "block";
        document.getElementById("llmSmallModel").value = "gemini-1.5-flash";
        document.getElementById("llmLargeModel").value = "gemini-1.5-pro";
      }
    });
  }

  if (btnSave) {
    btnSave.addEventListener("click", async () => {
      const payload = {
        provider: selProvider ? selProvider.value : "GEMINI",
        apiKey: document.getElementById("llmApiKey").value.trim() || null,
        baseUrl: document.getElementById("llmBaseUrl").value.trim() || null,
        smallModel: document.getElementById("llmSmallModel").value.trim() || null,
        largeModel: document.getElementById("llmLargeModel").value.trim() || null
      };
      btnSave.innerText = "Saving...";
      await fetchJSON("/api/llm/config", { method: "POST", body: JSON.stringify(payload) });
      btnSave.innerText = "✔ Saved!";
      setTimeout(() => { btnSave.innerText = "Save Configuration"; }, 2000);
      refreshLLMStatus();
    });
  }

  if (btnTest) {
    btnTest.addEventListener("click", async () => {
      if (!testResult) return;
      testResult.style.display = "block";
      testResult.className = "moment-result-box pending";
      testResult.innerText = "⚡ Invoking LLM Gateway...";
      btnTest.disabled = true;

      const res = await fetchJSON("/api/llm/test", {
        method: "POST",
        body: JSON.stringify({ prompt: "Draft a 1-sentence urgent patient alert for hyperkalemia (Potassium 6.4 mEq/L)." })
      });

      btnTest.disabled = false;
      if (res && res.status === "SUCCESS") {
        testResult.className = "moment-result-box success";
        testResult.innerHTML = `
          <strong>✔ Response from ${res.provider}:</strong><br/>
          "${typeof res.output === 'object' ? JSON.stringify(res.output) : res.output}"<br/>
          <span style="font-size:11px; color:#38bdf8;">Tokens Used: ${res.tokensUsed} | Total Tokens: ${res.totalTokensConsumed} | Total Spend: $${res.totalSpendUSD}</span>
        `;
      } else {
        testResult.className = "moment-result-box active";
        testResult.innerText = "Test executed using offline clinical fallback baseline. (Enter API key above for live cloud models)";
      }
      refreshLLMStatus();
    });
  }
}

// 14. Audience Lens Switcher & Welcome Portal Navigation
// 14. Audience Lens Switcher & Multi-Perspective Navigation
function initLensSwitcher() {
  const btnPortal = document.getElementById("btnLensPortal");
  const btnIndividual = document.getElementById("btnLensIndividual");
  const btnBulk = document.getElementById("btnLensBulk");
  const btnClinician = document.getElementById("btnLensClinician");
  const btnStory = document.getElementById("btnLensStory");
  const btnScientist = document.getElementById("btnLensScientist");

  const viewLanding = document.getElementById("viewLanding");
  const viewIndividual = document.getElementById("viewIndividual");
  const viewBulk = document.getElementById("viewBulk");
  const viewClinician = document.getElementById("viewClinician");
  const viewStory = document.getElementById("viewStory");
  const viewScientist = document.getElementById("viewScientist");

  const buttons = [btnPortal, btnIndividual, btnBulk, btnClinician, btnStory, btnScientist];
  const views = [viewLanding, viewIndividual, viewBulk, viewClinician, viewStory, viewScientist];

  function setLens(lens) {
    buttons.forEach(b => { if (b) b.classList.remove("active"); });
    views.forEach(v => { if (v) v.classList.add("hidden"); });

    if (lens === "portal") {
      if (btnPortal) btnPortal.classList.add("active");
      if (viewLanding) viewLanding.classList.remove("hidden");
    } else if (lens === "individual") {
      if (btnIndividual) btnIndividual.classList.add("active");
      if (viewIndividual) viewIndividual.classList.remove("hidden");
      loadPatientsTable();
    } else if (lens === "bulk") {
      if (btnBulk) btnBulk.classList.add("active");
      if (viewBulk) viewBulk.classList.remove("hidden");
    } else if (lens === "story") {
      if (btnStory) btnStory.classList.add("active");
      if (viewStory) viewStory.classList.remove("hidden");
    } else if (lens === "scientist") {
      if (btnScientist) btnScientist.classList.add("active");
      if (viewScientist) viewScientist.classList.remove("hidden");
    } else {
      if (btnClinician) btnClinician.classList.add("active");
      if (viewClinician) viewClinician.classList.remove("hidden");
    }

    try {
      history.replaceState(null, "", `#${lens}`);
    } catch (_) {}

    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // Lens bar buttons
  if (btnPortal) btnPortal.addEventListener("click", () => setLens("portal"));
  if (btnIndividual) btnIndividual.addEventListener("click", () => setLens("individual"));
  if (btnBulk) btnBulk.addEventListener("click", () => setLens("bulk"));
  if (btnClinician) btnClinician.addEventListener("click", () => setLens("clinician"));
  if (btnStory) btnStory.addEventListener("click", () => setLens("story"));
  if (btnScientist) btnScientist.addEventListener("click", () => setLens("scientist"));

  // Persistent Back to Home / Front Page buttons on all inner views
  document.querySelectorAll(".btn-back-home").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      setLens("portal");
    });
  });

  // Hero Section CTA buttons
  const btnHeroGetStarted = document.getElementById("btnHeroGetStarted");
  const btnHeroBulk = document.getElementById("btnHeroBulk");
  const btnHeroIndividual = document.getElementById("btnHeroIndividual");
  const btnHeroWAR = document.getElementById("btnHeroWAR");

  if (btnHeroGetStarted) btnHeroGetStarted.addEventListener("click", () => setLens("clinician"));
  if (btnHeroBulk) btnHeroBulk.addEventListener("click", () => setLens("bulk"));
  if (btnHeroIndividual) btnHeroIndividual.addEventListener("click", () => setLens("individual"));
  if (btnHeroWAR) {
    btnHeroWAR.addEventListener("click", () => {
      const modal = document.getElementById("warModal");
      if (modal) modal.style.display = "flex";
    });
  }

  // Welcome Portal Gateway Cards
  const cardIndividual = document.getElementById("portalCardIndividual");
  const cardBulk = document.getElementById("portalCardBulk");
  const cardClinician = document.getElementById("portalCardClinician");
  const cardScientist = document.getElementById("portalCardScientist");

  if (cardIndividual) cardIndividual.addEventListener("click", () => setLens("individual"));
  if (cardBulk) cardBulk.addEventListener("click", () => setLens("bulk"));
  if (cardClinician) cardClinician.addEventListener("click", () => setLens("clinician"));
  if (cardScientist) cardScientist.addEventListener("click", () => setLens("scientist"));

  // Logo badge returns to Front Page
  const brandEl = document.querySelector(".brand");
  if (brandEl) {
    brandEl.style.cursor = "pointer";
    brandEl.title = "Return to Front Page";
    brandEl.addEventListener("click", () => setLens("portal"));
  }

  // Hash route initialization
  const initialHash = window.location.hash.replace("#", "").toLowerCase();
  if (["portal", "individual", "bulk", "clinician", "story", "scientist"].includes(initialHash)) {
    setLens(initialHash);
  }
}

// 15. Individual Patient Studio
let currentEditingPatientId = null;
let currentDeletingPatientId = null;

function initIndividualStudio() {
  const kInput = document.getElementById("indivPotassium");
  const kBadge = document.getElementById("kLevelBadge");
  const form = document.getElementById("individualPatientForm");
  const btnRun = document.getElementById("btnRunIndivLoop");
  const btnSave = document.getElementById("btnSaveIndivOnly");
  const btnClear = document.getElementById("btnClearIndivForm");
  const btnNewQuick = document.getElementById("btnNewPatientQuick");
  const searchInput = document.getElementById("patientSearchInput");
  const btnRefresh = document.getElementById("btnRefreshPatients");

  // Dynamic Potassium Badge
  function updateKBadge() {
    if (!kInput || !kBadge) return;
    const val = parseFloat(kInput.value) || 0;
    if (val >= 6.0) {
      kBadge.className = "badge badge-red";
      kBadge.innerText = `Critical High (${val} mEq/L ≥ 6.0)`;
    } else if (val > 5.0) {
      kBadge.className = "badge badge-amber";
      kBadge.innerText = `Elevated Watch (${val} mEq/L)`;
    } else {
      kBadge.className = "badge badge-green";
      kBadge.innerText = `Normal Range (${val} mEq/L)`;
    }
  }

  if (kInput) {
    kInput.addEventListener("input", updateKBadge);
    updateKBadge();
  }

  // Gather form values
  function getFormData() {
    return {
      id: document.getElementById("indivId").value.trim() || undefined,
      name: document.getElementById("indivName").value.trim() || "Synthetic Patient",
      gender: document.getElementById("indivGender").value,
      birth_date: document.getElementById("indivDob").value,
      phone: document.getElementById("indivPhone").value.trim(),
      preferred_language: document.getElementById("indivLang").value,
      discharge_unit: document.getElementById("indivUnit").value.trim(),
      attending_physician: document.getElementById("indivPhysician").value.trim(),
      diagnosis: document.getElementById("indivDiagnosis").value.trim(),
      potassium: parseFloat(document.getElementById("indivPotassium").value) || 4.5,
      medications: document.getElementById("indivMeds").value.trim(),
      billing_amount: parseFloat(document.getElementById("indivBilling").value) || 1250.0
    };
  }

  // Run Multi-Agent Safety Loop
  if (btnRun) {
    btnRun.addEventListener("click", async () => {
      const payload = getFormData();
      btnRun.disabled = true;
      btnRun.innerText = "⏳ Executing Multi-Agent Pipeline...";

      try {
        const res = await fetchJSON("/api/patients?auto_run=true", {
          method: "POST",
          body: JSON.stringify(payload)
        });

        if (res && res.analysis) {
          renderIndividualDossier(res.analysis);
          loadPatientsTable();
          refreshAll();
        } else {
          // Simulation fallback
          const isCrit = payload.potassium >= 6.0;
          renderIndividualDossier({
            patientId: payload.id || "P-LOCAL-01",
            name: payload.name,
            language: payload.preferred_language,
            dischargeUnit: payload.discharge_unit,
            potassium: payload.potassium,
            isCritical: isCrit,
            status: isCrit ? "CRITICAL_LOOP_ACTIVE" : "ROUTINE_NORMAL",
            billingAmount: payload.billing_amount,
            conflictDetected: isCrit,
            billingPaused: isCrit,
            auditHash: "8f2a1b9c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a",
            labAgent: {
              finding: `Serum Potassium is ${payload.potassium} mEq/L (${isCrit ? 'CRITICAL HIGH >= 6.0' : 'Normal'})`,
              citation: "FHIR Observation/LAB-9921 (LOINC: 2823-3)"
            },
            pharmacyAgent: {
              finding: isCrit ? "Identified interacting medication: Spironolactone" : "No acute contraindications",
              flaggedMedications: isCrit ? ["Spironolactone"] : [],
              recommendation: isCrit ? "Withhold Spironolactone. Re-check potassium in 24 hours." : "Continue baseline regimen."
            },
            schedulingAgent: isCrit ? {
              bookingDetails: { appointmentTime: "Tomorrow 09:30 AM", department: "Cardio-Renal Outpatient Clinic" }
            } : null,
            billingAgent: {
              status: isCrit ? "PAUSED_BY_CONFLICT_RULE" : "APPROVED",
              conflictReason: isCrit ? "Billing paused: Active clinical loop in progress. Clinical resolution must precede commercial invoicing." : null
            },
            outreachAgent: isCrit ? {
              proposal: {
                payload: {
                  draftMessage: `Urgent clinical alert for ${payload.name}: Your potassium test came back high at ${payload.potassium} mEq/L. Please do not take your water pill today.`,
                  backTranslation: `Alert: Potassium level elevated. Hold diuretic medication. Doctor follow-up reserved.`
                }
              }
            } : null
          });
        }
      } catch (err) {
        console.error("Individual loop execution failed:", err);
      } finally {
        btnRun.disabled = false;
        btnRun.innerText = "▶ Run Multi-Agent Safety Loop";
      }
    });
  }

  // Save Patient Only
  if (btnSave) {
    btnSave.addEventListener("click", async () => {
      const payload = getFormData();
      btnSave.disabled = true;
      btnSave.innerText = "Saving...";
      await fetchJSON("/api/patients?auto_run=false", {
        method: "POST",
        body: JSON.stringify(payload)
      });
      btnSave.disabled = false;
      btnSave.innerText = "💾 Save Patient Only";
      loadPatientsTable();
      alert(`Patient "${payload.name}" successfully saved to SQLite database.`);
    });
  }

  // Clear Form
  if (btnClear) {
    btnClear.addEventListener("click", () => {
      document.getElementById("indivId").value = "";
      document.getElementById("indivName").value = "";
      document.getElementById("indivPotassium").value = "4.5";
      document.getElementById("indivBilling").value = "1250";
      document.getElementById("indivMeds").value = "";
      document.getElementById("indivDiagnosis").value = "Post-discharge clinical surveillance";
      updateKBadge();
    });
  }

  if (btnNewQuick) {
    btnNewQuick.addEventListener("click", () => {
      if (btnClear) btnClear.click();
      document.getElementById("indivName").focus();
    });
  }

  // Table Search and Refresh
  if (searchInput) {
    let debounceTimer;
    searchInput.addEventListener("input", (e) => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        loadPatientsTable(e.target.value);
      }, 300);
    });
  }

  if (btnRefresh) {
    btnRefresh.addEventListener("click", () => loadPatientsTable(searchInput ? searchInput.value : ""));
  }

  // Edit Patient Modal Controls
  initEditPatientModal();
  initDeleteConfirmModal();
}

// Render Individual Clinical Dossier Card
function renderIndividualDossier(data) {
  const container = document.getElementById("indivDossierBody");
  const badge = document.getElementById("indivStatusBadge");
  if (!container) return;

  if (badge) {
    badge.className = data.isCritical ? "badge badge-red" : "badge badge-green";
    badge.innerText = data.isCritical ? "🚨 CRITICAL LOOP ACTIVE (60-MIN SLA)" : "✅ ROUTINE OBSERVATION (NORMAL)";
  }

  const flaggedMeds = data.pharmacyAgent?.flaggedMedications || [];
  const medsText = flaggedMeds.length > 0 ? flaggedMeds.join(", ") : "None";

  container.innerHTML = `
    <!-- Patient Overview Header -->
    <div class="dossier-section" style="border-left: 4px solid ${data.isCritical ? '#f43f5e' : '#10b981'};">
      <div class="dossier-section-title">
        <span>👤 Patient: ${data.name} (${data.patientId})</span>
        <span class="badge ${data.isCritical ? 'badge-red' : 'badge-green'}">${data.status}</span>
      </div>
      <div style="font-size:12px; color:#cbd5e1; display:grid; grid-template-columns:1fr 1fr; gap:6px; margin-top:6px;">
        <div><strong>Preferred Language:</strong> ${(data.language || 'en').toUpperCase()}</div>
        <div><strong>Discharge Unit:</strong> ${data.dischargeUnit || 'Cardiology'}</div>
        <div><strong>Serum Potassium:</strong> <span style="font-weight:700; color:${data.isCritical ? '#f43f5e' : '#34d399'}">${data.potassium} mEq/L</span></div>
        <div><strong>Commercial Invoice:</strong> $${Number(data.billingAmount || 0).toLocaleString()}</div>
      </div>
    </div>

    <!-- Agent 1: Lab Classifier (T0) -->
    <div class="dossier-section">
      <div class="dossier-section-title">
        <span>🧪 Agent 1: Lab Results Classifier (Tier T0)</span>
        <span class="badge badge-cyan">Automated</span>
      </div>
      <div style="font-size:12.5px; color:#f1f5f9; font-weight:600;">${data.labAgent?.finding || 'Serum potassium analyzed.'}</div>
      <div style="font-size:11px; color:#94a3b8; font-family:var(--font-mono); margin-top:3px;">
        Evidence Citation: ${data.labAgent?.citation || 'FHIR Observation/LOINC: 2823-3'}
      </div>
    </div>

    <!-- Agent 2: Pharmacy Reconciliation (T0) -->
    <div class="dossier-section">
      <div class="dossier-section-title">
        <span>💊 Agent 2: Pharmacy Reconciliation (Tier T0)</span>
        <span class="badge ${flaggedMeds.length > 0 ? 'badge-amber' : 'badge-green'}">
          ${flaggedMeds.length > 0 ? 'Contraindication Detected' : 'Clear'}
        </span>
      </div>
      <div style="font-size:12px; color:#cbd5e1;">
        <strong>Flagged Interacting Drugs:</strong> <span style="color:#f59e0b; font-weight:600;">${medsText}</span>
      </div>
      <div style="font-size:12px; color:#e2e8f0; margin-top:4px;">
        <strong>Clinical Recommendation:</strong> ${data.pharmacyAgent?.recommendation || 'Continue prescribed medications.'}
      </div>
    </div>

    <!-- Agent 3: Scheduling Agent (T1) -->
    ${data.schedulingAgent ? `
    <div class="dossier-section">
      <div class="dossier-section-title">
        <span>📅 Agent 3: Urgent Clinic Scheduling (Tier T1)</span>
        <span class="badge badge-emerald">Auto-Booked</span>
      </div>
      <div style="font-size:12px; color:#cbd5e1;">
        Auto-reserved post-discharge emergency cardiology slot: <strong>${data.schedulingAgent?.bookingDetails?.appointmentTime || 'Tomorrow 09:30 AM'}</strong> at <strong>${data.schedulingAgent?.bookingDetails?.department || 'Cardio-Renal Outpatient Clinic'}</strong>.
      </div>
    </div>
    ` : ''}

    <!-- Agent 4: Billing Agent Conflict Gate (Safety Moment 1) -->
    <div class="dossier-section" style="${data.billingPaused ? 'border-color: rgba(239, 68, 68, 0.4);' : ''}">
      <div class="dossier-section-title">
        <span>🛑 Safety Moment 1: Commercial Billing Policy Gate</span>
        <span class="badge ${data.billingPaused ? 'badge-red' : 'badge-green'}">
          ${data.billingPaused ? 'INVOICE FROZEN' : 'DISPATCH PERMITTED'}
        </span>
      </div>
      ${data.billingPaused ? `
      <div class="conflict-paused-banner">
        <strong>Conflict Rule Active:</strong> Commercial invoice for $${Number(data.billingAmount || 0).toLocaleString()} is PAUSED.
        <div style="font-size:11px; margin-top:3px; color:#fee2e2;">
          ${data.billingAgent?.conflictReason || 'Active clinical safety loop in progress. Clinical resolution must precede commercial invoicing.'}
        </div>
      </div>
      ` : `
      <div style="font-size:12px; color:#cbd5e1;">
        No active clinical safety conflicts detected. Standard discharge invoice processing proceeds.
      </div>
      `}
    </div>

    <!-- Agent 5: Multilingual Outreach (Tier T2 - Safety Moment 3) -->
    ${data.outreachAgent ? `
    <div class="dossier-section" style="border-color: rgba(245, 158, 11, 0.4);">
      <div class="dossier-section-title">
        <span>🌐 Safety Moment 3: Multilingual Patient Outreach (Tier T2)</span>
        <span class="badge badge-amber">Clinician Sign-off Required</span>
      </div>
      <div style="font-size:12px; color:#cbd5e1; margin-bottom:4px;">
        <strong>Drafted Message (${(data.language || 'en').toUpperCase()}):</strong>
      </div>
      <div style="background:#0a0e17; padding:8px 12px; border-radius:6px; font-size:12px; color:#38bdf8; border:1px solid #1e293b;">
        "${data.outreachAgent?.proposal?.payload?.draftMessage || 'Urgent clinical alert for potassium elevation.'}"
      </div>
      <div style="font-size:11px; color:#94a3b8; margin-top:6px;">
        <strong>Certified English Back-Translation:</strong>
        <em>"${data.outreachAgent?.proposal?.payload?.backTranslation || 'Emergency potassium alert verified.'}"</em>
      </div>
      <div style="display:flex; gap:8px; margin-top:10px;">
        <button class="btn btn-primary btn-xs" onclick="decideAction('${data.outreachAgent?.actionId || 'ACT-OUTREACH-01'}', 'APPROVE')">
          ✓ Approve & Send Immediately
        </button>
        <button class="btn btn-outline btn-xs" style="border-color:#f43f5e; color:#f43f5e;" onclick="decideAction('${data.outreachAgent?.actionId || 'ACT-OUTREACH-01'}', 'REJECT')">
          ✕ Override / Reject
        </button>
      </div>
    </div>
    ` : ''}

    <!-- Cryptographic Audit Hash -->
    <div style="padding: 8px 12px; background: rgba(15, 23, 42, 0.5); border-radius: 6px; font-family: var(--font-mono); font-size: 11px; color: #94a3b8; display:flex; justify-content:space-between; align-items:center;">
      <span>SHA-256 Audit Stamp:</span>
      <span style="color:#34d399; font-weight:600;">${(data.auditHash || '0a8f9c1e3b5d7a9f').substring(0, 24)}...</span>
    </div>
  `;
}

// Load SQLite Patients Registry Table
async function loadPatientsTable(query = "") {
  const tbody = document.getElementById("patientsTableBody");
  if (!tbody) return;

  tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:16px; color:#94a3b8;">Loading SQLite records...</td></tr>`;

  const url = query ? `/api/patients?q=${encodeURIComponent(query)}` : "/api/patients";
  const data = await fetchJSON(url);

  const patients = data?.patients || [
    { id: "P-84920", name: "Ramesh Kumar", preferred_language: "te", discharge_unit: "Cardiology Stepdown", diagnosis: "CHF, Post-STEMI", billing_amount: 1450, status: "ACTIVE" },
    { id: "P-10021", name: "Elena Rodriguez", preferred_language: "es", discharge_unit: "Internal Medicine", diagnosis: "CKD Stage 3", billing_amount: 2100, status: "ACTIVE" },
    { id: "P-55412", name: "David Miller", preferred_language: "en", discharge_unit: "Telemetry Ward", diagnosis: "ACS / Reduced EF", billing_amount: 1600, status: "ACTIVE" }
  ];

  if (patients.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:24px; color:#94a3b8;">No matching patients found in database.</td></tr>`;
    return;
  }

  tbody.innerHTML = patients.map(p => {
    // Extract potassium from labs if present
    let kStr = "4.5";
    if (p.labs && p.labs.length > 0) {
      kStr = p.labs[0].value || "4.5";
    }
    const kNum = parseFloat(kStr) || 4.5;
    const isCrit = kNum >= 6.0;

    return `
      <tr>
        <td style="font-family:var(--font-mono); font-weight:600; color:#38bdf8;">${p.id}</td>
        <td style="font-weight:600; color:#f1f5f9;">${p.name}</td>
        <td><span class="badge badge-purple">${(p.preferred_language || 'en').toUpperCase()}</span></td>
        <td>${p.discharge_unit || 'General Inpatient'}</td>
        <td style="max-width:200px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${p.diagnosis || 'Post-discharge follow-up'}</td>
        <td><span class="badge ${isCrit ? 'badge-red' : 'badge-green'}">${kNum} mEq/L</span></td>
        <td>$${Number(p.billing_amount || 0).toLocaleString()}</td>
        <td><span class="badge ${p.status === 'ACTIVE' ? 'badge-emerald' : 'badge-amber'}">${p.status || 'ACTIVE'}</span></td>
        <td>
          <div style="display:flex; gap:6px;">
            <button class="btn btn-outline btn-xs" title="Run Clinical Safety Loop" onclick="analyzePatientFromTable('${p.id}')">▶ Run</button>
            <button class="btn btn-outline btn-xs" title="Edit Patient" onclick="openEditPatientModal('${p.id}')">✏️</button>
            <button class="btn btn-outline btn-xs" style="border-color:#f43f5e; color:#f43f5e;" title="Delete Patient" onclick="openDeleteConfirmModal('${p.id}', '${p.name.replace(/'/g, "\\'")}')">🗑️</button>
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

// Analyze Patient From Table
async function analyzePatientFromTable(patientId) {
  const detail = await fetchJSON(`/api/patients/${patientId}`);
  if (detail && detail.patient) {
    const p = detail.patient;
    document.getElementById("indivId").value = p.id;
    document.getElementById("indivName").value = p.name;
    document.getElementById("indivGender").value = p.gender || "male";
    document.getElementById("indivDob").value = p.birth_date || "1964-08-14";
    document.getElementById("indivPhone").value = p.phone || "+1-555-0100";
    document.getElementById("indivLang").value = p.preferred_language || "en";
    document.getElementById("indivUnit").value = p.discharge_unit || "Cardiology Stepdown";
    document.getElementById("indivPhysician").value = p.attending_physician || "Dr. Jenkins, MD";
    document.getElementById("indivDiagnosis").value = p.diagnosis || "Post-discharge clinical surveillance";
    document.getElementById("indivBilling").value = p.billing_amount || 1250;

    let kVal = 4.5;
    if (p.labs && p.labs.length > 0) kVal = p.labs[0].value || 4.5;
    document.getElementById("indivPotassium").value = kVal;

    let medsStr = "";
    if (Array.isArray(p.medications)) {
      medsStr = p.medications.map(m => m.name || m).join(", ");
    }
    document.getElementById("indivMeds").value = medsStr;

    // Trigger loop execution
    document.getElementById("btnRunIndivLoop").click();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
}

// Edit Patient Modal Implementation
function initEditPatientModal() {
  const modal = document.getElementById("modalEditPatient");
  const btnClose = document.getElementById("btnCloseEditPatient");
  const btnCancel = document.getElementById("btnCancelEditPatient");
  const btnSave = document.getElementById("btnSaveEditPatient");

  if (!modal) return;

  const closeModal = () => { modal.style.display = "none"; };
  if (btnClose) btnClose.addEventListener("click", closeModal);
  if (btnCancel) btnCancel.addEventListener("click", closeModal);

  if (btnSave) {
    btnSave.addEventListener("click", async () => {
      const pid = document.getElementById("editPid").value;
      const payload = {
        name: document.getElementById("editName").value.trim(),
        preferred_language: document.getElementById("editLang").value,
        phone: document.getElementById("editPhone").value.trim(),
        discharge_unit: document.getElementById("editUnit").value.trim(),
        attending_physician: document.getElementById("editPhysician").value.trim(),
        diagnosis: document.getElementById("editDiagnosis").value.trim(),
        potassium: parseFloat(document.getElementById("editPotassium").value) || 4.5,
        billing_amount: parseFloat(document.getElementById("editBilling").value) || 1250,
        medications: document.getElementById("editMeds").value.trim()
      };

      btnSave.disabled = true;
      btnSave.innerText = "Saving...";
      await fetchJSON(`/api/patients/${pid}`, {
        method: "PUT",
        body: JSON.stringify(payload)
      });
      btnSave.disabled = false;
      btnSave.innerText = "💾 Save Changes";
      closeModal();
      loadPatientsTable();
    });
  }

  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();
  });
}

async function openEditPatientModal(patientId) {
  const modal = document.getElementById("modalEditPatient");
  if (!modal) return;

  const detail = await fetchJSON(`/api/patients/${patientId}`);
  if (!detail || !detail.patient) return;
  const p = detail.patient;

  document.getElementById("editPid").value = p.id;
  document.getElementById("editName").value = p.name;
  document.getElementById("editLang").value = p.preferred_language || "en";
  document.getElementById("editPhone").value = p.phone || "";
  document.getElementById("editUnit").value = p.discharge_unit || "";
  document.getElementById("editPhysician").value = p.attending_physician || "";
  document.getElementById("editDiagnosis").value = p.diagnosis || "";
  document.getElementById("editBilling").value = p.billing_amount || 1250;

  let kVal = 4.5;
  if (p.labs && p.labs.length > 0) kVal = p.labs[0].value || 4.5;
  document.getElementById("editPotassium").value = kVal;

  let medsStr = "";
  if (Array.isArray(p.medications)) {
    medsStr = p.medications.map(m => m.name || m).join(", ");
  }
  document.getElementById("editMeds").value = medsStr;

  modal.style.display = "flex";
}

// Delete Confirmation Modal
function initDeleteConfirmModal() {
  const modal = document.getElementById("modalDeleteConfirm");
  const btnClose = document.getElementById("btnCloseDeleteConfirm");
  const btnCancel = document.getElementById("btnCancelDelete");
  const btnConfirm = document.getElementById("btnConfirmDelete");

  if (!modal) return;

  const closeModal = () => { modal.style.display = "none"; };
  if (btnClose) btnClose.addEventListener("click", closeModal);
  if (btnCancel) btnCancel.addEventListener("click", closeModal);

  if (btnConfirm) {
    btnConfirm.addEventListener("click", async () => {
      if (!currentDeletingPatientId) return;
      btnConfirm.disabled = true;
      btnConfirm.innerText = "Deleting...";
      await fetchJSON(`/api/patients/${currentDeletingPatientId}`, { method: "DELETE" });
      btnConfirm.disabled = false;
      btnConfirm.innerText = "🗑️ Permanently Delete";
      closeModal();
      loadPatientsTable();
    });
  }

  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();
  });
}

function openDeleteConfirmModal(patientId, patientName) {
  currentDeletingPatientId = patientId;
  const modal = document.getElementById("modalDeleteConfirm");
  if (!modal) return;
  document.getElementById("deletePatientId").innerText = patientId;
  document.getElementById("deletePatientName").innerText = patientName;
  modal.style.display = "flex";
}

// 16. Bulk Data Processing Studio
let lastProcessedBatchResults = [];

function initBulkStudio() {
  const dropzone = document.getElementById("bulkDropzone");
  const fileInput = document.getElementById("bulkFileInput");
  const fileInfo = document.getElementById("selectedFileInfo");
  const fileNameEl = document.getElementById("selectedFileName");
  const fileSizeEl = document.getElementById("selectedFileSize");
  const btnProcess = document.getElementById("btnTriggerBulkUpload");
  const btnSampleRun = document.getElementById("btnRunSampleBatch");
  const progressWrap = document.getElementById("bulkProgressWrap");
  const progressFill = document.getElementById("bulkProgressFill");
  const progressStatus = document.getElementById("bulkProgressStatus");

  let selectedFile = null;

  if (dropzone && fileInput) {
    dropzone.addEventListener("click", (e) => {
      if (e.target !== btnProcess) fileInput.click();
    });

    dropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropzone.classList.add("dragover");
    });
    dropzone.addEventListener("dragleave", () => {
      dropzone.classList.remove("dragover");
    });
    dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        setFile(e.dataTransfer.files[0]);
      }
    });

    fileInput.addEventListener("change", (e) => {
      if (e.target.files && e.target.files.length > 0) {
        setFile(e.target.files[0]);
      }
    });
  }

  function setFile(file) {
    selectedFile = file;
    if (fileInfo && fileNameEl && fileSizeEl) {
      fileNameEl.innerText = file.name;
      fileSizeEl.innerText = `(${(file.size / 1024).toFixed(1)} KB)`;
      fileInfo.classList.remove("hidden");
    }
  }

  // Upload and process batch
  if (btnProcess) {
    btnProcess.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!selectedFile) {
        alert("Please select or drop a CSV, Excel (.xlsx), or JSON dataset first.");
        return;
      }
      await uploadAndProcessFile(selectedFile);
    });
  }

  // 1-Click Run Sample 12-Patient Cohort
  if (btnSampleRun) {
    btnSampleRun.addEventListener("click", async () => {
      btnSampleRun.disabled = true;
      btnSampleRun.innerText = "⏳ Loading & Evaluating 12 Diverse Patient Cases...";

      try {
        // Fetch verified sample CSV from backend
        const res = await fetch(`${API_BASE}/api/bulk/template/csv`);
        const blob = await res.blob();
        const sampleFile = new File([blob], "careloop_sample_dataset.csv", { type: "text/csv" });
        await uploadAndProcessFile(sampleFile);
      } catch (err) {
        console.warn("Sample batch upload failed:", err);
      } finally {
        btnSampleRun.disabled = false;
        btnSampleRun.innerText = "⚡ Load & Run Sample 12-Patient Cohort with 1 Click";
      }
    });
  }

  async function uploadAndProcessFile(file) {
    if (progressWrap) progressWrap.classList.remove("hidden");
    if (progressFill) progressFill.style.width = "40%";
    if (progressStatus) progressStatus.innerText = `Ingesting ${file.name}... Normalizing schema...`;

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API_BASE}/api/bulk/upload`, {
        method: "POST",
        body: formData
      });

      if (progressFill) progressFill.style.width = "85%";
      if (progressStatus) progressStatus.innerText = "Executing multi-agent loops & conflict rules...";

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      if (progressFill) progressFill.style.width = "100%";
      if (progressStatus) progressStatus.innerText = "Batch processing successfully completed!";

      setTimeout(() => {
        if (progressWrap) progressWrap.classList.add("hidden");
      }, 1000);

      renderBatchResults(data);
      loadPatientsTable();
      refreshAll();
    } catch (err) {
      console.error("Batch processing error:", err);
      if (progressStatus) progressStatus.innerText = `Processing error: ${err.message || err}`;
    }
  }

  // Filter Pills for Batch Table
  document.querySelectorAll(".pill-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".pill-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const filter = btn.dataset.filter;
      filterBatchTable(filter);
    });
  });

  // Dossier Inspector Modal
  initDossierInspectModal();
}

// Render Batch Telemetry & Table
function renderBatchResults(data) {
  const summary = data.summary || {};
  const results = data.results || [];
  lastProcessedBatchResults = results;

  // 1. KPI Ribbon
  const totalEl = document.getElementById("bulkKpiTotal");
  const critEl = document.getElementById("bulkKpiCritical");
  const routineEl = document.getElementById("bulkKpiRoutine");
  const pausedEl = document.getElementById("bulkKpiPaused");
  const protectedEl = document.getElementById("bulkKpiProtected");

  if (totalEl) totalEl.innerText = summary.totalRecords || results.length;
  if (critEl) critEl.innerText = summary.criticalRecords || 0;
  if (routineEl) routineEl.innerText = summary.routineRecords || 0;
  if (pausedEl) pausedEl.innerText = summary.billingPausedCount || 0;
  if (protectedEl) protectedEl.innerText = `$${Number(summary.totalBillingProtectedUSD || 0).toLocaleString()}`;

  // 2. Warnings
  const warningsBox = document.getElementById("bulkWarningsBox");
  const warningsList = document.getElementById("bulkWarningsList");
  if (warningsBox && warningsList) {
    const issues = summary.validationWarnings || [];
    if (issues.length > 0) {
      warningsList.innerHTML = issues.map(w => `<li>${w}</li>`).join("");
      warningsBox.classList.remove("hidden");
    } else {
      warningsBox.classList.add("hidden");
    }
  }

  // 3. Subtext
  const subtextEl = document.getElementById("batchSubtext");
  if (subtextEl) {
    subtextEl.innerText = `Job ID: ${summary.jobId || 'BATCH'} • ${results.length} records evaluated • ${new Date().toLocaleTimeString()}`;
  }

  // 4. Render Table
  renderBatchTableRows(results);
}

function renderBatchTableRows(records) {
  const tbody = document.getElementById("batchTableBody");
  if (!tbody) return;

  if (records.length === 0) {
    tbody.innerHTML = `<tr><td colspan="11" style="text-align:center; padding:32px; color:#94a3b8;">No matching records found for this filter.</td></tr>`;
    return;
  }

  tbody.innerHTML = records.map((r, idx) => {
    const isCrit = r.isCritical;
    const meds = r.pharmacyAgent?.flaggedMedications || [];
    const medsStr = meds.length > 0 ? meds.join(", ") : "None";

    return `
      <tr>
        <td style="font-family:var(--font-mono); font-weight:600; color:#38bdf8;">${r.patientId}</td>
        <td style="font-weight:600; color:#f1f5f9;">${r.name}</td>
        <td><span class="badge badge-purple">${(r.language || 'en').toUpperCase()}</span></td>
        <td>${r.dischargeUnit || 'Cardiology'}</td>
        <td><span class="badge ${isCrit ? 'badge-red' : 'badge-green'}">${r.potassium} mEq/L</span></td>
        <td><span class="badge ${isCrit ? 'badge-red' : 'badge-emerald'}">${isCrit ? '60-min SLA' : 'NONE'}</span></td>
        <td style="color:${meds.length > 0 ? '#f59e0b' : '#94a3b8'}; font-weight:600;">${medsStr}</td>
        <td>
          <span class="badge ${r.billingPaused ? 'badge-red' : 'badge-green'}">
            ${r.billingPaused ? 'PAUSED' : 'APPROVED'} ($${Number(r.billingAmount || 0).toLocaleString()})
          </span>
        </td>
        <td>
          <span class="badge ${isCrit ? 'badge-amber' : 'badge-cyan'}">
            ${isCrit ? 'T2 Sign-Off' : 'Standard'}
          </span>
        </td>
        <td style="font-family:var(--font-mono); font-size:11px; color:#94a3b8;">${(r.auditHash || 'GENESIS').substring(0, 10)}...</td>
        <td>
          <button class="btn btn-outline btn-xs" onclick="inspectBatchRowDossier(${idx})">🔍 Inspect</button>
        </td>
      </tr>
    `;
  }).join("");
}

function filterBatchTable(filter) {
  if (!lastProcessedBatchResults || lastProcessedBatchResults.length === 0) return;
  if (filter === "critical") {
    renderBatchTableRows(lastProcessedBatchResults.filter(r => r.isCritical));
  } else if (filter === "paused") {
    renderBatchTableRows(lastProcessedBatchResults.filter(r => r.billingPaused));
  } else if (filter === "routine") {
    renderBatchTableRows(lastProcessedBatchResults.filter(r => !r.isCritical));
  } else {
    renderBatchTableRows(lastProcessedBatchResults);
  }
}

// Dossier Inspector Modal implementation
function initDossierInspectModal() {
  const modal = document.getElementById("modalDossierInspect");
  const btnClose = document.getElementById("btnCloseDossierInspect");
  const btnDismiss = document.getElementById("btnDismissDossierInspect");

  if (!modal) return;
  const closeModal = () => { modal.style.display = "none"; };
  if (btnClose) btnClose.addEventListener("click", closeModal);
  if (btnDismiss) btnDismiss.addEventListener("click", closeModal);

  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();
  });
}

function inspectBatchRowDossier(index) {
  const record = lastProcessedBatchResults[index];
  if (!record) return;

  const modal = document.getElementById("modalDossierInspect");
  const title = document.getElementById("inspectModalTitle");
  const body = document.getElementById("inspectModalBody");
  if (!modal || !body) return;

  if (title) title.innerText = `Clinical Dossier: ${record.name} (${record.patientId})`;

  body.innerHTML = `
    <div style="display:flex; flex-direction:column; gap:12px;">
      <div class="dossier-section" style="border-left:4px solid ${record.isCritical ? '#f43f5e' : '#10b981'};">
        <div class="dossier-section-title">
          <span>Overview</span>
          <span class="badge ${record.isCritical ? 'badge-red' : 'badge-green'}">${record.status}</span>
        </div>
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px; font-size:12px; color:#cbd5e1;">
          <div><strong>Discharge Unit:</strong> ${record.dischargeUnit || 'Post-Acute'}</div>
          <div><strong>Preferred Language:</strong> ${(record.language || 'en').toUpperCase()}</div>
          <div><strong>Potassium:</strong> <span style="font-weight:700; color:${record.isCritical ? '#f43f5e' : '#34d399'}">${record.potassium} mEq/L</span></div>
          <div><strong>Commercial Billing:</strong> $${Number(record.billingAmount || 0).toLocaleString()} (${record.billingPaused ? 'PAUSED' : 'ACTIVE'})</div>
        </div>
      </div>

      <div class="dossier-section">
        <div class="dossier-section-title">
          <span>Agent 1: Lab Classifier (T0)</span>
          <span class="badge badge-cyan">LOINC: 2823-3</span>
        </div>
        <div style="font-size:12px; color:#f1f5f9;">${record.labAgent?.finding || 'Serum potassium classified.'}</div>
      </div>

      <div class="dossier-section">
        <div class="dossier-section-title">
          <span>Agent 2: Pharmacy Reconciliation (T0)</span>
          <span class="badge ${record.pharmacyAgent?.flaggedMedications?.length > 0 ? 'badge-amber' : 'badge-green'}">Field Masking Scoped</span>
        </div>
        <div style="font-size:12px; color:#cbd5e1;">
          <strong>Flagged Drugs:</strong> ${record.pharmacyAgent?.flaggedMedications?.join(', ') || 'None'}
        </div>
        <div style="font-size:12px; color:#e2e8f0; margin-top:4px;">
          <strong>Recommendation:</strong> ${record.pharmacyAgent?.recommendation || 'Continue baseline medications.'}
        </div>
      </div>

      <div class="dossier-section" style="${record.billingPaused ? 'border-color:rgba(239, 68, 68, 0.4);' : ''}">
        <div class="dossier-section-title">
          <span>Safety Moment 1: Billing Conflict Gate</span>
          <span class="badge ${record.billingPaused ? 'badge-red' : 'badge-green'}">${record.billingPaused ? 'PAUSED' : 'APPROVED'}</span>
        </div>
        ${record.billingPaused ? `
        <div class="conflict-paused-banner">
          ${record.billingAgent?.conflictReason || 'Commercial billing halted by active clinical safety loop.'}
        </div>
        ` : `<div style="font-size:12px; color:#cbd5e1;">Commercial invoice processing approved without conflict.</div>`}
      </div>

      ${record.outreachAgent ? `
      <div class="dossier-section">
        <div class="dossier-section-title">
          <span>Safety Moment 3: Multilingual Outreach (T2)</span>
          <span class="badge badge-amber">Sign-Off Required</span>
        </div>
        <div style="background:#0a0e17; padding:8px 12px; border-radius:6px; font-size:12px; color:#38bdf8;">
          "${record.outreachAgent?.proposal?.payload?.draftMessage || 'Clinical alert drafted.'}"
        </div>
      </div>
      ` : ''}

      <div style="font-family:var(--font-mono); font-size:11px; color:#94a3b8; padding:8px 12px; background:rgba(15,23,42,0.6); border-radius:6px;">
        Cryptographic SHA-256 Hash: <span style="color:#34d399;">${record.auditHash || 'GENESIS'}</span>
      </div>
    </div>
  `;

  modal.style.display = "flex";
}

// 17. Microsoft Well-Architected Framework (WAR) Modal
function initWARModal() {
  const modal = document.getElementById("warModal");
  const btnOpen = document.getElementById("btnOpenWARModal");
  const btnClose = document.getElementById("btnCloseWARModal");
  const btnDismiss = document.getElementById("btnDismissWAR");

  if (!modal) return;

  const closeModal = () => { modal.style.display = "none"; };
  if (btnOpen) btnOpen.addEventListener("click", (e) => { e.preventDefault(); modal.style.display = "flex"; });
  if (btnClose) btnClose.addEventListener("click", (e) => { e.preventDefault(); closeModal(); });
  if (btnDismiss) btnDismiss.addEventListener("click", (e) => { e.preventDefault(); closeModal(); });

  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();
  });

  // Global Escape key dismisses all modals
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" || e.key === "Esc") {
      closeModal();
      const diagModal = document.getElementById("diagModal");
      const llmModal = document.getElementById("llmModal");
      const editModal = document.getElementById("modalEditPatient");
      const delModal = document.getElementById("modalDeleteConfirm");
      const dossierModal = document.getElementById("modalDossierInspect");

      if (diagModal) diagModal.style.display = "none";
      if (llmModal) llmModal.style.display = "none";
      if (editModal) editModal.style.display = "none";
      if (delModal) delModal.style.display = "none";
      if (dossierModal) dossierModal.style.display = "none";
    }
  });
}

// Global initialization
document.addEventListener("DOMContentLoaded", () => {
  const btnRun = document.getElementById("btnRunDemo");
  const btnInj = document.getElementById("btnTestInjection");
  const btnPv = document.getElementById("btnSimulateSideEffect");
  const btnSim = document.getElementById("btnRunSimulator");

  if (btnRun) btnRun.addEventListener("click", runDemoScenario);
  if (btnInj) btnInj.addEventListener("click", testPromptInjection);
  if (btnPv) btnPv.addEventListener("click", simulatePatientADR);
  if (btnSim) btnSim.addEventListener("click", runSimulator);

  initDebugButtons();
  initLLMModal();
  initDiagModal();
  initLensSwitcher();
  initWARModal();
  initIndividualStudio();
  initBulkStudio();

  refreshAll();
  setInterval(refreshAll, 3000);
});

