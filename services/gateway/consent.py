"""
CareLoop Consent Verification Engine
Validates patient consent against the data fetch purpose.
Refuses and logs unauthorized fetches.
"""

from typing import Dict, Any, Tuple
from data.fhir_store import fhir_store

class ConsentEngine:
    @staticmethod
    def verify_consent(patient_id: str, purpose: str) -> Tuple[bool, str]:
        """
        Verifies if patient has granted consent for the specified clinical or operational purpose.
        Returns: (allowed: bool, reason: str)
        """
        consent_record = fhir_store.get_consent(patient_id)
        if not consent_record:
            # Default to restrictive clinical care coordination if not explicitly forbidden
            if purpose in ["emergency_contact", "critical_alert_outreach"]:
                return True, "Default emergency consent implied"
            return False, f"No consent record found on file for patient {patient_id}"

        permitted = consent_record.get("provision", {}).get("action", [])
        denied = consent_record.get("denied", [])

        if purpose in denied:
            return False, f"Patient explicitly opted out of purpose: '{purpose}'"

        if purpose in permitted or purpose in ["critical_alert_outreach", "emergency_contact"]:
            return True, f"Patient granted explicit consent for purpose: '{purpose}'"

        return False, f"Purpose '{purpose}' is not authorized in patient consent preferences"

consent_engine = ConsentEngine()
