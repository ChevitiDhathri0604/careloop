"""
CareLoop MCP Gateway: Task-Scoped Tokens & Access Control
Generates short-lived, task-scoped cryptographic tokens for agents.
Ensures agents only have access to strictly required FHIR fields.
"""

import time
import hmac
import hashlib
import json
import base64
from typing import Dict, Any, List, Optional

SECRET_KEY = b"careloop_task_secret_key_2026_dhathri"

class TokenManager:
    @staticmethod
    def generate_task_token(agent_id: str, task_id: str, patient_id: str, scopes: List[str], ttl_seconds: int = 300) -> str:
        """
        Creates a signed, task-scoped bearer token.
        """
        payload = {
            "sub": agent_id,
            "task_id": task_id,
            "patient_id": patient_id,
            "scopes": scopes,
            "exp": int(time.time()) + ttl_seconds,
            "iat": int(time.time())
        }
        raw_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        payload_b64 = base64.urlsafe_b64encode(raw_bytes).decode("utf-8")
        sig = hmac.new(SECRET_KEY, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{payload_b64}.{sig}"

    @staticmethod
    def verify_token(token: str) -> Optional[Dict[str, Any]]:
        """
        Validates token signature and expiration.
        """
        try:
            parts = token.split(".")
            if len(parts) != 2:
                return None
            payload_b64, sig = parts
            expected_sig = hmac.new(SECRET_KEY, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, expected_sig):
                return None
            payload_json = base64.urlsafe_b64decode(payload_b64.encode("utf-8")).decode("utf-8")
            payload = json.loads(payload_json)
            if payload.get("exp", 0) < time.time():
                return None # Expired
            return payload
        except Exception:
            return None

token_manager = TokenManager()
