"""
CareLoop Persistent Database Layer (SQLite)
Ensures persistent, production-ready storage for Patients, Clinical Loops,
Action Proposals, and Bulk Processing Jobs.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

DB_PATH = Path(__file__).parent.parent.parent / "data" / "careloop.db"
SYNTHETIC_PATH = Path(__file__).parent.parent.parent / "data" / "synthetic_patients.json"

class Database:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            # 1. Patients Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS patients (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    birth_date TEXT,
                    gender TEXT,
                    phone TEXT,
                    preferred_language TEXT DEFAULT 'en',
                    discharge_date TEXT,
                    discharge_unit TEXT,
                    attending_physician TEXT,
                    diagnosis TEXT,
                    medications_json TEXT DEFAULT '[]',
                    labs_json TEXT DEFAULT '[]',
                    billing_amount REAL DEFAULT 0.0,
                    status TEXT DEFAULT 'ACTIVE',
                    created_at TEXT,
                    updated_at TEXT
                )
            """)

            # 2. Clinical Loops Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS clinical_loops (
                    loop_id TEXT PRIMARY KEY,
                    patient_id TEXT NOT NULL,
                    description TEXT,
                    status TEXT DEFAULT 'OPEN',
                    opened_at TEXT,
                    closed_at TEXT,
                    deadline_minutes INTEGER DEFAULT 60,
                    time_to_contact_minutes REAL,
                    resolution_summary TEXT,
                    FOREIGN KEY(patient_id) REFERENCES patients(id) ON DELETE CASCADE
                )
            """)

            # 3. Action Proposals Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS proposals (
                    action_id TEXT PRIMARY KEY,
                    loop_id TEXT,
                    patient_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    risk_tier TEXT NOT NULL,
                    status TEXT DEFAULT 'PROPOSED',
                    conflict_status TEXT DEFAULT 'NONE',
                    conflict_reason TEXT,
                    payload_json TEXT DEFAULT '{}',
                    evidence_json TEXT DEFAULT '{}',
                    notes TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    FOREIGN KEY(patient_id) REFERENCES patients(id) ON DELETE CASCADE
                )
            """)

            # 4. Bulk Jobs Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bulk_jobs (
                    job_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    total_records INTEGER DEFAULT 0,
                    valid_records INTEGER DEFAULT 0,
                    critical_records INTEGER DEFAULT 0,
                    billing_paused_count INTEGER DEFAULT 0,
                    total_billing_protected REAL DEFAULT 0.0,
                    status TEXT DEFAULT 'COMPLETED',
                    created_at TEXT
                )
            """)
            conn.commit()

        # Seed initial patients if empty
        self._seed_initial_patients()

    def _seed_initial_patients(self):
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) as count FROM patients")
            if cursor.fetchone()["count"] > 0:
                return

        if not SYNTHETIC_PATH.exists():
            return

        try:
            with open(SYNTHETIC_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                for p in data.get("patients", []):
                    now = datetime.utcnow().isoformat() + "Z"
                    self.save_patient({
                        "id": p["id"],
                        "name": p["name"],
                        "birth_date": p.get("birthDate"),
                        "gender": p.get("gender"),
                        "phone": p.get("phone"),
                        "preferred_language": p.get("preferredLanguage", "en"),
                        "discharge_date": p.get("dischargeDate", now),
                        "discharge_unit": p.get("dischargeUnit", "General Inpatient"),
                        "attending_physician": p.get("attendingPhysician", "Dr. Jenkins, MD"),
                        "diagnosis": ", ".join(c.get("display", "") for c in p.get("activeConditions", [])),
                        "medications": p.get("medications", []),
                        "labs": p.get("recentLabs", []),
                        "billing_amount": 1450.0 if p["id"] == "P-84920" else 850.0
                    })
        except Exception as e:
            print(f"[Database] Warning: Initial seeding skipped: {e}")

    # --- Patient CRUD ---
    def save_patient(self, p: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.utcnow().isoformat() + "Z"
        pid = p.get("id") or f"P-{abs(hash(p.get('name', '') + now)) % 100000:05d}"
        
        meds = p.get("medications", [])
        if isinstance(meds, str):
            try:
                meds = json.loads(meds)
            except Exception:
                meds = [{"name": m.strip()} for m in meds.split(",") if m.strip()]

        labs = p.get("labs", [])
        if isinstance(labs, str):
            try:
                labs = json.loads(labs)
            except Exception:
                labs = []

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO patients (
                    id, name, birth_date, gender, phone, preferred_language,
                    discharge_date, discharge_unit, attending_physician, diagnosis,
                    medications_json, labs_json, billing_amount, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    birth_date=excluded.birth_date,
                    gender=excluded.gender,
                    phone=excluded.phone,
                    preferred_language=excluded.preferred_language,
                    discharge_date=excluded.discharge_date,
                    discharge_unit=excluded.discharge_unit,
                    attending_physician=excluded.attending_physician,
                    diagnosis=excluded.diagnosis,
                    medications_json=excluded.medications_json,
                    labs_json=excluded.labs_json,
                    billing_amount=excluded.billing_amount,
                    status=excluded.status,
                    updated_at=excluded.updated_at
            """, (
                pid,
                p.get("name", "Unknown Patient"),
                p.get("birth_date") or p.get("birthDate"),
                p.get("gender", "unknown"),
                p.get("phone", "+91-9876543210"),
                p.get("preferred_language") or p.get("preferredLanguage", "en"),
                p.get("discharge_date") or p.get("dischargeDate", now),
                p.get("discharge_unit") or p.get("dischargeUnit", "Ambulatory Stepdown"),
                p.get("attending_physician") or p.get("attendingPhysician", "Dr. Jenkins, MD"),
                p.get("diagnosis", "Post-discharge follow-up"),
                json.dumps(meds),
                json.dumps(labs),
                float(p.get("billing_amount", p.get("billingAmount", 1250.0))),
                p.get("status", "ACTIVE"),
                now,
                now
            ))
            conn.commit()

        return self.get_patient(pid)

    def get_patient(self, patient_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,))
            row = cursor.fetchone()
            if not row:
                return None
            res = dict(row)
            res["medications"] = json.loads(res.get("medications_json") or "[]")
            res["labs"] = json.loads(res.get("labs_json") or "[]")
            return res

    def list_patients(self, query: Optional[str] = None, limit: int = 200, offset: int = 0) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            if query:
                q = f"%{query.strip().lower()}%"
                cursor = conn.execute("""
                    SELECT * FROM patients
                    WHERE lower(name) LIKE ? OR lower(id) LIKE ? OR lower(diagnosis) LIKE ?
                    ORDER BY updated_at DESC LIMIT ? OFFSET ?
                """, (q, q, q, limit, offset))
            else:
                cursor = conn.execute("SELECT * FROM patients ORDER BY updated_at DESC LIMIT ? OFFSET ?", (limit, offset))
            
            patients = []
            for row in cursor.fetchall():
                p = dict(row)
                p["medications"] = json.loads(p.get("medications_json") or "[]")
                p["labs"] = json.loads(p.get("labs_json") or "[]")
                patients.append(p)
            return patients

    def delete_patient(self, patient_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
            conn.commit()
            return cursor.rowcount > 0

    # --- Loops & Proposals ---
    def save_loop(self, loop: Dict[str, Any]):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO clinical_loops (
                    loop_id, patient_id, description, status, opened_at, closed_at,
                    deadline_minutes, time_to_contact_minutes, resolution_summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(loop_id) DO UPDATE SET
                    status=excluded.status,
                    closed_at=excluded.closed_at,
                    time_to_contact_minutes=excluded.time_to_contact_minutes,
                    resolution_summary=excluded.resolution_summary
            """, (
                loop["loopId"],
                loop["patientId"],
                loop.get("description", ""),
                loop.get("status", "OPEN"),
                loop.get("openedAt"),
                loop.get("closedAt"),
                loop.get("deadlineMinutes", 60),
                loop.get("timeToContactMinutes"),
                loop.get("resolutionSummary")
            ))
            conn.commit()

    def get_loops_for_patient(self, patient_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM clinical_loops WHERE patient_id = ? ORDER BY opened_at DESC", (patient_id,))
            return [dict(r) for r in cursor.fetchall()]

    def save_proposal(self, prop: Dict[str, Any]):
        now = datetime.utcnow().isoformat() + "Z"
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO proposals (
                    action_id, loop_id, patient_id, agent_id, action_type, risk_tier,
                    status, conflict_status, conflict_reason, payload_json, evidence_json, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(action_id) DO UPDATE SET
                    status=excluded.status,
                    conflict_status=excluded.conflict_status,
                    conflict_reason=excluded.conflict_reason,
                    notes=excluded.notes,
                    updated_at=excluded.updated_at
            """, (
                prop["actionId"],
                prop.get("loopId"),
                prop["patientId"],
                prop.get("agentId", "agent"),
                prop.get("actionType", "ACTION"),
                prop.get("riskTier", "T1"),
                prop.get("status", "PROPOSED"),
                prop.get("conflictStatus", "NONE"),
                prop.get("conflictReason"),
                json.dumps(prop.get("payload", {})),
                json.dumps(prop.get("evidence", {})),
                prop.get("notes"),
                prop.get("createdAt", now),
                now
            ))
            conn.commit()

    def record_bulk_job(self, job: Dict[str, Any]):
        now = datetime.utcnow().isoformat() + "Z"
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO bulk_jobs (
                    job_id, filename, file_type, total_records, valid_records,
                    critical_records, billing_paused_count, total_billing_protected,
                    status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job["job_id"],
                job.get("filename", "dataset"),
                job.get("file_type", "csv"),
                job.get("total_records", 0),
                job.get("valid_records", 0),
                job.get("critical_records", 0),
                job.get("billing_paused_count", 0),
                job.get("total_billing_protected", 0.0),
                job.get("status", "COMPLETED"),
                now
            ))
            conn.commit()

    def get_analytics(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            p_count = conn.execute("SELECT COUNT(*) as c FROM patients").fetchone()["c"]
            loop_open = conn.execute("SELECT COUNT(*) as c FROM clinical_loops WHERE status = 'OPEN'").fetchone()["c"]
            loop_closed = conn.execute("SELECT COUNT(*) as c FROM clinical_loops WHERE status = 'CLOSED'").fetchone()["c"]
            paused_bills = conn.execute("SELECT COUNT(*) as c FROM proposals WHERE conflict_status = 'CONFLICT_DETECTED'").fetchone()["c"]
            total_billing = conn.execute("SELECT SUM(billing_amount) as s FROM patients").fetchone()["s"] or 0.0
            
            # Language breakdown
            lang_rows = conn.execute("SELECT preferred_language, COUNT(*) as c FROM patients GROUP BY preferred_language").fetchall()
            lang_dist = {r["preferred_language"]: r["c"] for r in lang_rows}

            # Tiers
            t2_pending = conn.execute("SELECT COUNT(*) as c FROM proposals WHERE risk_tier = 'T2' AND status = 'PENDING_APPROVAL'").fetchone()["c"]

            return {
                "totalPatients": p_count,
                "activeLoops": loop_open,
                "closedLoops": loop_closed,
                "closureRatePct": round((loop_closed / (loop_open + loop_closed) * 100) if (loop_open + loop_closed) > 0 else 100, 1),
                "pausedBillingCount": paused_bills,
                "totalBillingTrackedUSD": round(total_billing, 2),
                "pendingT2Approvals": t2_pending,
                "languageDistribution": lang_dist
            }

db = Database()
