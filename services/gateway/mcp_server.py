"""
CareLoop MCP Gateway Server
Enforces:
1. Task-scoped bearer token verification
2. Patient consent & purpose checking
3. Strict field masking (e.g. Pharmacy agent cannot access non-medication clinical notes or billing)
4. Audit logging of all data accesses
"""

from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, Header, Query
from pydantic import BaseModel
from data.fhir_store import fhir_store
from .scoping import token_manager
from .consent import consent_engine

app = FastAPI(title="CareLoop MCP Gateway", version="1.0.0")

# Access audit log
gateway_access_logs: List[Dict[str, Any]] = []

def record_access_log(agent_id: str, task_id: str, patient_id: str, resource: str, action: str, status: str, detail: str):
    gateway_access_logs.append({
        "timestamp": time_now(),
        "agentId": agent_id,
        "taskId": task_id,
        "patientId": patient_id,
        "resource": resource,
        "action": action,
        "status": status,
        "detail": detail
    })

def time_now() -> str:
    from datetime import datetime
    return datetime.utcnow().isoformat() + "Z"

class MCPToolRequest(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]
    purpose: str = "care_coordination"

@app.get("/health")
def health():
    return {"status": "ok", "service": "mcp-gateway"}

@app.get("/logs")
def get_logs():
    return gateway_access_logs[-100:]

@app.post("/mcp/call")
def call_tool(req: MCPToolRequest, authorization: Optional[str] = Header(None)):
    """
    Executes an MCP tool with token verification, consent check, and field masking.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization bearer token")

    token = authorization.split(" ")[1]
    token_claims = token_manager.verify_token(token)
    if not token_claims:
        raise HTTPException(status_code=403, detail="Invalid or expired task-scoped token")

    agent_id = token_claims.get("sub", "unknown")
    task_id = token_claims.get("task_id", "")
    token_patient_id = token_claims.get("patient_id", "")
    scopes = token_claims.get("scopes", [])

    requested_patient_id = req.arguments.get("patient_id", token_patient_id)

    # Cross-patient access protection
    if token_patient_id and requested_patient_id != token_patient_id:
        record_access_log(agent_id, task_id, requested_patient_id, req.tool_name, "CALL", "DENIED", "Cross-patient access attempt blocked")
        raise HTTPException(status_code=403, detail="Cross-patient access forbidden: token scoped to another patient")

    # Consent check
    allowed, consent_reason = consent_engine.verify_consent(requested_patient_id, req.purpose)
    if not allowed:
        record_access_log(agent_id, task_id, requested_patient_id, req.tool_name, "CALL", "DENIED", f"Consent refused: {consent_reason}")
        raise HTTPException(status_code=403, detail=f"Consent refusal: {consent_reason}")

    # Dispatch tool
    tool_name = req.tool_name

    if tool_name == "get_medications":
        if "read:medications" not in scopes and "*" not in scopes:
            record_access_log(agent_id, task_id, requested_patient_id, "MedicationRequest", "READ", "DENIED", "Missing 'read:medications' scope")
            raise HTTPException(status_code=403, detail="Scope 'read:medications' required")

        meds = fhir_store.get_medications(requested_patient_id)
        # Field masking: Only expose medication entity, no unrelated encounters or billing data
        masked_meds = [
            {
                "id": m["id"],
                "name": m["medicationCodeableConcept"]["text"],
                "code": m["medicationCodeableConcept"]["coding"][0]["code"],
                "class": m.get("clinicalClass"),
                "highRiskWithHyperkalemia": m.get("highRiskWithHyperkalemia", False)
            }
            for m in meds
        ]
        record_access_log(agent_id, task_id, requested_patient_id, "MedicationRequest", "READ", "ALLOWED", f"Returned {len(masked_meds)} masked medications")
        return {"patientId": requested_patient_id, "medications": masked_meds}

    elif tool_name == "get_labs":
        if "read:labs" not in scopes and "*" not in scopes:
            record_access_log(agent_id, task_id, requested_patient_id, "Observation", "READ", "DENIED", "Missing 'read:labs' scope")
            raise HTTPException(status_code=403, detail="Scope 'read:labs' required")

        test_code = req.arguments.get("test_code")
        labs = fhir_store.get_observations(requested_patient_id, test_code)
        record_access_log(agent_id, task_id, requested_patient_id, "Observation", "READ", "ALLOWED", f"Returned {len(labs)} lab records")
        return {"patientId": requested_patient_id, "observations": labs}

    elif tool_name == "get_patient_demographics":
        # Check if pharmacy agent is requesting outside demographics
        if agent_id == "pharmacy-agent":
            record_access_log(agent_id, task_id, requested_patient_id, "Patient", "READ", "DENIED", "Pharmacy agent field masking: demographics restricted")
            raise HTTPException(status_code=403, detail="Access denied: Pharmacy agent is restricted to medications only (Field Masking)")

        if "read:patient" not in scopes and "*" not in scopes:
            record_access_log(agent_id, task_id, requested_patient_id, "Patient", "READ", "DENIED", "Missing 'read:patient' scope")
            raise HTTPException(status_code=403, detail="Scope 'read:patient' required")

        patient = fhir_store.get_patient(requested_patient_id)
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")
        record_access_log(agent_id, task_id, requested_patient_id, "Patient", "READ", "ALLOWED", "Demographics accessed")
        return patient

    elif tool_name == "get_discharge_summary":
        if agent_id == "pharmacy-agent":
            record_access_log(agent_id, task_id, requested_patient_id, "Encounter", "READ", "DENIED", "Field masking: Pharmacy agent cannot read encounters")
            raise HTTPException(status_code=403, detail="Field masking active: Pharmacy agent cannot read inpatient discharge notes")

        encounters = fhir_store.get_encounters(requested_patient_id)
        record_access_log(agent_id, task_id, requested_patient_id, "Encounter", "READ", "ALLOWED", f"Returned {len(encounters)} encounters")
        return {"patientId": requested_patient_id, "encounters": encounters}

    else:
        raise HTTPException(status_code=400, detail=f"Unknown tool '{tool_name}'")

# Helper direct function call for in-process testing
def execute_mcp_call(tool_name: str, arguments: Dict[str, Any], token: str, purpose: str = "care_coordination") -> Dict[str, Any]:
    req = MCPToolRequest(tool_name=tool_name, arguments=arguments, purpose=purpose)
    return call_tool(req, authorization=f"Bearer {token}")
