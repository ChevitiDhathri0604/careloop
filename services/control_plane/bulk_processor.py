"""
CareLoop Enterprise Bulk Data Ingestion & Processing Engine
Supports CSV, Excel (.xlsx), and JSON batch file uploads.
Features:
- Flexible column header aliasing and schema normalization
- Row-level data validation and error resilience
- Automated multi-agent clinical safety loop execution per record
- Conflict rule evaluation (commercial billing paused during clinical loops)
- Aggregated enterprise telemetry (critical rates, billing protected, languages)
- Persistent SQLite storage and export to CSV/Excel
"""

import io
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

import pandas as pd
from services.db.database import db
from services.control_plane.pipeline import process_patient_clinical_loop

UPLOAD_DIR = Path(__file__).parent.parent.parent / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Standardized column aliases
COLUMN_ALIASES = {
    "id": ["id", "patient_id", "patientid", "mrn", "patient mrn", "record_id"],
    "name": ["name", "patient_name", "patientname", "full_name", "fullname"],
    "birth_date": ["birth_date", "birthdate", "dob", "date_of_birth", "birth date"],
    "gender": ["gender", "sex"],
    "phone": ["phone", "phone_number", "contact", "mobile", "telephone"],
    "preferred_language": ["preferred_language", "language", "lang", "pref_lang", "preferred language"],
    "discharge_date": ["discharge_date", "dischargedate", "discharge", "discharge date"],
    "discharge_unit": ["discharge_unit", "unit", "department", "ward", "discharge unit"],
    "attending_physician": ["attending_physician", "physician", "doctor", "dr", "attending physician"],
    "diagnosis": ["diagnosis", "condition", "conditions", "primary_diagnosis", "indication"],
    "potassium": ["potassium", "k_level", "k_value", "potassium_meq_l", "lab_value", "k+"],
    "medications": ["medications", "meds", "active_medications", "prescriptions", "drugs"],
    "billing_amount": ["billing_amount", "billingamount", "amount_due", "invoice_amount", "bill", "cost"]
}

def normalize_column_name(col: str) -> str:
    cleaned = col.strip().lower().replace("-", "_").replace(" ", "_")
    for standard_name, aliases in COLUMN_ALIASES.items():
        if cleaned in aliases or col.strip().lower() in aliases:
            return standard_name
    return cleaned

class BulkProcessor:
    def __init__(self):
        self.last_batch_results: List[Dict[str, Any]] = []
        self.last_batch_summary: Dict[str, Any] = {}

    def parse_file(self, filename: str, content_bytes: bytes) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Parses CSV, XLSX, or JSON file bytes into raw patient records and warnings."""
        ext = filename.split(".")[-1].lower() if "." in filename else ""
        warnings = []
        records = []

        try:
            if ext == "csv":
                df = pd.read_csv(io.BytesIO(content_bytes))
                records = self._df_to_records(df)
            elif ext in ["xlsx", "xls"]:
                df = pd.read_excel(io.BytesIO(content_bytes))
                records = self._df_to_records(df)
            elif ext == "json":
                parsed = json.loads(content_bytes.decode("utf-8"))
                if isinstance(parsed, list):
                    records = parsed
                elif isinstance(parsed, dict):
                    # Check for "patients" key or similar wrapper
                    records = parsed.get("patients", parsed.get("data", [parsed]))
                else:
                    warnings.append("Unexpected JSON format: root is not a list or object.")
            else:
                raise ValueError(f"Unsupported file format '{ext}'. Please upload .csv, .xlsx, or .json files.")
        except Exception as e:
            raise ValueError(f"Failed to parse {filename}: {str(e)}")

        return records, warnings

    def _df_to_records(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        # Rename columns using normalized aliases
        rename_map = {}
        for col in df.columns:
            norm = normalize_column_name(str(col))
            rename_map[col] = norm
        df = df.rename(columns=rename_map)

        # Replace NaN with None
        df = df.where(pd.notnull(df), None)
        return df.to_dict(orient="records")

    def validate_and_normalize_record(self, raw: Dict[str, Any], index: int) -> Tuple[Dict[str, Any], List[str]]:
        """Validates record fields and assigns safe clinical defaults."""
        issues = []
        now = datetime.utcnow().isoformat() + "Z"

        # Normalize keys in dict
        norm_dict = {}
        for k, v in raw.items():
            norm_k = normalize_column_name(str(k))
            norm_dict[norm_k] = v

        pid = norm_dict.get("id")
        if not pid:
            pid = f"P-BATCH-{index+1:04d}"
            issues.append(f"Row {index+1}: Missing Patient ID, generated '{pid}'")

        name = norm_dict.get("name")
        if not name:
            name = f"Patient {pid}"
            issues.append(f"Row {index+1}: Missing Patient Name, defaulted to '{name}'")

        # Potassium
        k_val = norm_dict.get("potassium")
        try:
            k_float = float(k_val) if k_val is not None else 4.5
        except (ValueError, TypeError):
            k_float = 4.5
            issues.append(f"Row {index+1}: Invalid potassium value '{k_val}', defaulted to 4.5 mEq/L")

        # Medications
        meds = norm_dict.get("medications", [])
        if isinstance(meds, str):
            med_str = meds.strip()
            if med_str.startswith("["):
                try:
                    meds = json.loads(med_str)
                except Exception:
                    meds = [{"name": m.strip()} for m in med_str.split(",") if m.strip()]
            else:
                meds = [{"name": m.strip()} for m in med_str.split(",") if m.strip()]
        elif not isinstance(meds, list):
            meds = []

        # Billing amount
        bill = norm_dict.get("billing_amount", 1250.0)
        try:
            bill_float = float(bill) if bill is not None else 1250.0
        except (ValueError, TypeError):
            bill_float = 1250.0

        patient_record = {
            "id": str(pid).strip(),
            "name": str(name).strip(),
            "birth_date": str(norm_dict.get("birth_date") or "1965-05-15"),
            "gender": str(norm_dict.get("gender") or "unknown").lower(),
            "phone": str(norm_dict.get("phone") or "+1-555-0100"),
            "preferred_language": str(norm_dict.get("preferred_language") or "en").lower()[:5],
            "discharge_date": str(norm_dict.get("discharge_date") or now),
            "discharge_unit": str(norm_dict.get("discharge_unit") or "Post-Acute Inpatient"),
            "attending_physician": str(norm_dict.get("attending_physician") or "Dr. Jenkins, MD"),
            "diagnosis": str(norm_dict.get("diagnosis") or "Congestive Heart Failure / Post-discharge"),
            "potassium": k_float,
            "medications": meds,
            "billing_amount": bill_float,
            "status": "ACTIVE"
        }

        return patient_record, issues

    def process_batch(self, filename: str, content_bytes: bytes) -> Dict[str, Any]:
        """
        Executes end-to-end bulk processing:
        1. Persists raw file in data/uploads/
        2. Parses and validates all records
        3. Executes multi-agent clinical loop for each record
        4. Calculates enterprise analytics
        5. Records job in SQLite database
        """
        job_id = f"JOB-{uuid.uuid4().hex[:8].upper()}"
        file_ext = filename.split(".")[-1].lower() if "." in filename else "dat"

        # 1. Save uploaded file
        saved_path = UPLOAD_DIR / f"{job_id}_{filename}"
        with open(saved_path, "wb") as f:
            f.write(content_bytes)

        # 2. Parse file
        raw_records, parse_warnings = self.parse_file(filename, content_bytes)
        
        results = []
        validation_warnings = []
        critical_count = 0
        normal_count = 0
        paused_billing_count = 0
        total_billing_protected = 0.0
        languages = {}

        # 3. Process each record
        for idx, raw in enumerate(raw_records):
            patient_dict, issues = self.validate_and_normalize_record(raw, idx)
            validation_warnings.extend(issues)

            # Run through multi-agent clinical pipeline
            res = process_patient_clinical_loop(patient_dict)
            results.append(res)

            # Aggregate statistics
            if res.get("isCritical"):
                critical_count += 1
            else:
                normal_count += 1

            if res.get("billingPaused"):
                paused_billing_count += 1
                total_billing_protected += res.get("billingAmount", 0.0)

            lang = res.get("language", "en")
            languages[lang] = languages.get(lang, 0) + 1

        summary = {
            "jobId": job_id,
            "filename": filename,
            "fileType": file_ext,
            "totalRecords": len(results),
            "validRecords": len(results),
            "criticalRecords": critical_count,
            "routineRecords": normal_count,
            "billingPausedCount": paused_billing_count,
            "totalBillingProtectedUSD": round(total_billing_protected, 2),
            "languagesDistribution": languages,
            "validationWarnings": validation_warnings[:20],
            "totalWarningsCount": len(validation_warnings),
            "processedAt": datetime.utcnow().isoformat() + "Z"
        }

        # 4. Save bulk job to SQLite
        db.record_bulk_job({
            "job_id": job_id,
            "filename": filename,
            "file_type": file_ext,
            "total_records": len(results),
            "valid_records": len(results),
            "critical_records": critical_count,
            "billing_paused_count": paused_billing_count,
            "total_billing_protected": total_billing_protected,
            "status": "COMPLETED"
        })

        self.last_batch_results = results
        self.last_batch_summary = summary

        return {
            "status": "COMPLETED",
            "summary": summary,
            "results": results
        }

    def export_results_csv(self, results: Optional[List[Dict[str, Any]]] = None) -> str:
        """Exports processed batch results to a CSV string."""
        data = results or self.last_batch_results
        rows = []
        for r in data:
            meds = r.get("pharmacyAgent", {}).get("flaggedMedications", [])
            rows.append({
                "Patient ID": r.get("patientId"),
                "Name": r.get("name"),
                "Language": r.get("language"),
                "Discharge Unit": r.get("dischargeUnit"),
                "Potassium (mEq/L)": r.get("potassium"),
                "Clinical Status": r.get("status"),
                "Emergency Loop": "ACTIVE (60-min SLA)" if r.get("isCritical") else "NONE",
                "Flagged Medications": ", ".join(meds) if meds else "None",
                "Billing Invoice Status": "PAUSED (Conflict Gate)" if r.get("billingPaused") else "APPROVED",
                "Invoice Amount ($)": f"${r.get('billingAmount', 0):,.2f}",
                "Outreach Status": "T2 Clinician Sign-Off Required" if r.get("isCritical") else "NOT_REQUIRED",
                "Cryptographic Audit Hash": r.get("auditHash")
            })
        df = pd.DataFrame(rows)
        return df.to_csv(index=False)

    def export_results_excel(self, results: Optional[List[Dict[str, Any]]] = None) -> bytes:
        """Exports processed batch results to Excel bytes (.xlsx)."""
        data = results or self.last_batch_results
        rows = []
        for r in data:
            meds = r.get("pharmacyAgent", {}).get("flaggedMedications", [])
            rows.append({
                "Patient ID": r.get("patientId"),
                "Name": r.get("name"),
                "Language": r.get("language"),
                "Discharge Unit": r.get("dischargeUnit"),
                "Potassium (mEq/L)": r.get("potassium"),
                "Clinical Status": r.get("status"),
                "Emergency Loop": "ACTIVE (60-min SLA)" if r.get("isCritical") else "NONE",
                "Flagged Medications": ", ".join(meds) if meds else "None",
                "Billing Invoice Status": "PAUSED (Conflict Gate)" if r.get("billingPaused") else "APPROVED",
                "Invoice Amount ($)": f"${r.get('billingAmount', 0):,.2f}",
                "Outreach Status": "T2 Clinician Sign-Off Required" if r.get("isCritical") else "NOT_REQUIRED",
                "Cryptographic Audit Hash": r.get("auditHash")
            })
        df = pd.DataFrame(rows)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="CareLoop Clinical Batch")
        return output.getvalue()

bulk_processor = BulkProcessor()
