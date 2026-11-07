# CareLoop: Multi-Agent Clinical Safety Control Plane

[![Evaluation Suite](https://img.shields.io/badge/Evals-30%2F30%20Pass%20(100%25)-brightgreen)](evals/)
[![Audit Chain](https://img.shields.io/badge/Audit%20Ledger-SHA--256%20Tamper--Proof-blue)](services/control_plane/ledger.py)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)
[![Zero-Cost](https://img.shields.io/badge/Cost-100%25%20Free%20Local%20Run-emerald)](docs/ARCHITECTURE_AND_PRODUCTION.md)

CareLoop is an autonomous clinical safety control plane that closes critical-result loops end-to-end post-discharge, enforces OPA risk tiers (T0–T3), blocks unsafe actions live, and immutably records every decision in a SHA-256 hash-chained audit trail.

Developed by **Team Coders**:
- **Cheviti Dhathri (Lead)**: Control plane, agent registry, router, OPA risk tiers, action ledger, write-back.
- **Amaravathi Sai Ashritha**: Multi-agent suite (5 agents), prompt-injection guard, pharmacovigilance bridge, evals runner.
- **Chinthakunta Padma Tejaswini**: Synthea & HAPI FHIR store, event bus partitioning, MCP gateway, consent checks, replay simulator.
- **Katamraj Gari Ediga Jaswanth Goud**: Ops console, clinician approval inbox, Docker Compose, monitoring.

---

## Key Features & Deliverables

1. **End-to-End Critical Result Loop**: Detects post-discharge critical potassium ($K^+ = 6.4\text{ mEq/L}$), enforces a 60-minute contact SLA, orchestrates 4 agents + PV bridge, and resolves the loop with clinical sign-off.
2. **Three Live Safety Moments**:
   - **Moment 1 (Conflict Rule)**: Pauses commercial billing invoice while clinical safety loop is active.
   - **Moment 2 (Prompt-Injection Defense)**: Intercepts and blocks malicious prompt smuggling in untrusted patient text.
   - **Moment 3 (Human-in-the-Loop Sign-off)**: Risky medication withhold directives (Spironolactone) require certified back-translation review and 1-click clinician approval.
3. **MCP Security Gateway**: Task-scoped cryptographic bearer tokens, patient consent checking, and strict field masking (Pharmacy agent is restricted to medications only).
4. **Drug Safety / Pharmacovigilance Bridge**: Automatically converts suspected adverse drug reactions (ADRs) into regulatory **ICH-E2B (R3)** ICSR drafts with MedDRA coding.
5. **Replay Simulator**: Forecasts approval load reduction (e.g. $-35.3\%$) and billing conflicts over historical synthetic event streams.
6. **Emergency Kill Switch & Behaviour Monitor**: Real-time anomaly detection and 1-click agent quarantine.
7. **Tamper-Proof Audit Ledger**: Mathematically linked SHA-256 hash chain providing cryptographic proof of provenance.

---

## Quickstart Guide

### Option 1: Run Standalone Demo (Terminal)
Zero dependencies outside Python! Runs locally in seconds:
```bash
python run_demo.py
```

### Option 2: Run Unified Web Dashboard
Launches both the FastAPI Control Plane API and the Ops Console on a single local port:
```bash
python run_demo.py --serve
```
Then open your browser to **[http://127.0.0.1:8000](http://127.0.0.1:8000)**.
- Interactive **Clinician Approval Inbox**
- Live **60-minute Deadline SLA Counter**
- **1-Click Critical Result Scenario Trigger**
- **Interactive Prompt-Injection Tester**
- **E2B ICSR Case Viewer**
- **Policy Replay Simulator**
- **Real-Time Cryptographic Hash Chain Inspector**

### Option 3: Run Evaluation Suite & Policy Tests
Run the 30-case clinical and safety evaluation benchmark:
```bash
python evals/runner.py
python policies/test_policies.py
```

### Option 4: Docker Compose
```bash
docker-compose up --build
```

---

## Repository Structure

```
careloop/
├── docker-compose.yml              # Multi-container orchestration (FastAPI, Redis, Postgres)
├── Dockerfile                      # Container definition
├── requirements.txt                # Python dependencies
├── run_demo.py                     # Standalone CLI & web dashboard runner
├── data/
│   ├── synthetic_patients.json     # Synthea synthetic patient seed data
│   └── fhir_store.py               # In-process HAPI FHIR R4 server
├── services/
│   ├── ingestion/                  # HL7 v2 (ADT^A03, ORU^R01) parser & partitioned event bus
│   ├── control_plane/              # Agent registry, router, risk gate, action ledger, loop tracker
│   ├── gateway/                    # MCP gateway: task-scoped tokens, field masking, consent
│   ├── agents/                     # 5 agents: lab, pharmacy, scheduling, billing, outreach
│   ├── safety/                     # Injection guard, behaviour monitor, drug-safety bridge
│   ├── simulator/                  # Replay simulator over historical synthetic events
│   └── console/                    # Clinician inbox & ops console (FastAPI + HTML/CSS/JS)
├── policies/                       # OPA Rego policies (risk_tiers.rego, conflicts.rego)
├── evals/                          # 30-case evaluation set & test runner
└── docs/                           # Architecture document & live demo script
```

---

## Demo Acceptance Checklist

- [x] A critical potassium result for a discharged patient opens a loop with a 60-minute contact deadline
- [x] The billing agent's final invoice is paused by a conflict rule
- [x] The pharmacy agent sees medications only and flags the potassium-sparing diuretic
- [x] The outreach message waits for clinician approval, then sends
- [x] The scheduling agent books an urgent slot automatically (T1)
- [x] An injected instruction in the patient's reply is blocked and logged
- [x] The patient's side-effect reply creates a drug-safety case draft
- [x] The ops console shows the closed loop and its full audit trail
- [x] The kill switch stops an agent mid-demo
