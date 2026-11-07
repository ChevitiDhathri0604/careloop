"""
CareLoop FHIR Store
Simulates an in-process and REST-compatible HAPI FHIR R4 server with Synthea patients.
Provides Patient, Observation (Labs), MedicationRequest, and Consent resource queries.
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional

DATA_PATH = Path(__file__).parent / "synthetic_patients.json"

class FHIRStore:
    def __init__(self, data_path: Path = DATA_PATH):
        self.data_path = data_path
        self.patients: Dict[str, Dict[str, Any]] = {}
        self.observations: Dict[str, List[Dict[str, Any]]] = {}
        self.medications: Dict[str, List[Dict[str, Any]]] = {}
        self.consents: Dict[str, Dict[str, Any]] = {}
        self.encounters: Dict[str, List[Dict[str, Any]]] = {}
        self.load_data()

    def load_data(self):
        if not self.data_path.exists():
            return
        with open(self.data_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        for p in raw.get("patients", []):
            pid = p["id"]
            # Build FHIR Patient
            self.patients[pid] = {
                "resourceType": "Patient",
                "id": pid,
                "name": [{"use": "official", "text": p["name"]}],
                "gender": p.get("gender"),
                "birthDate": p.get("birthDate"),
                "telecom": [{"system": "phone", "value": p.get("phone")}],
                "communication": [{"language": {"coding": [{"code": p.get("preferredLanguage", "en")}]}}],
                "active": True
            }

            # Build FHIR Consent
            consent_rules = p.get("consent", {})
            self.consents[pid] = {
                "resourceType": "Consent",
                "id": f"CONSENT-{pid}",
                "status": "active",
                "patient": {"reference": f"Patient/{pid}"},
                "provision": {
                    "type": "permit",
                    "action": [k for k, v in consent_rules.items() if v]
                },
                "denied": [k for k, v in consent_rules.items() if not v]
            }

            # Build FHIR Encounters
            if "dischargeDate" in p:
                self.encounters[pid] = [{
                    "resourceType": "Encounter",
                    "id": f"ENC-{pid}-01",
                    "status": "finished",
                    "class": {"code": "IMP", "display": "inpatient encounter"},
                    "subject": {"reference": f"Patient/{pid}"},
                    "period": {
                        "end": p["dischargeDate"]
                    },
                    "serviceProvider": {"display": p.get("dischargeUnit", "General Hospital")},
                    "participant": [{"individual": {"display": p.get("attendingPhysician")}}]
                }]

            # Build FHIR MedicationRequests
            self.medications[pid] = []
            for med in p.get("medications", []):
                self.medications[pid].append({
                    "resourceType": "MedicationRequest",
                    "id": med["id"],
                    "status": "active",
                    "intent": "order",
                    "subject": {"reference": f"Patient/{pid}"},
                    "medicationCodeableConcept": {
                        "coding": [{
                            "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                            "code": med.get("rxNorm"),
                            "display": med.get("name")
                        }],
                        "text": f"{med.get('name')} {med.get('dosage')}"
                    },
                    "clinicalClass": med.get("class"),
                    "highRiskWithHyperkalemia": med.get("highRiskWithHyperkalemia", False)
                })

            # Build FHIR Observations
            self.observations[pid] = []
            for lab in p.get("recentLabs", []):
                self.observations[pid].append({
                    "resourceType": "Observation",
                    "id": lab["id"],
                    "status": "final",
                    "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "laboratory"}]}],
                    "code": {
                        "coding": [{
                            "system": "http://loinc.org",
                            "code": lab.get("testCode"),
                            "display": lab.get("testName")
                        }],
                        "text": lab.get("testName")
                    },
                    "subject": {"reference": f"Patient/{pid}"},
                    "effectiveDateTime": lab.get("collectedAt"),
                    "issued": lab.get("resultedAt"),
                    "valueQuantity": {
                        "value": lab.get("value"),
                        "unit": lab.get("unit"),
                        "system": "http://unitsofmeasure.org"
                    },
                    "referenceRange": [{"text": lab.get("referenceRange")}],
                    "interpretation": [{"coding": [{"code": lab.get("flag", "N")}]}]
                })

    def get_patient(self, patient_id: str) -> Optional[Dict[str, Any]]:
        return self.patients.get(patient_id)

    def get_medications(self, patient_id: str) -> List[Dict[str, Any]]:
        return self.medications.get(patient_id, [])

    def get_observations(self, patient_id: str, test_code: Optional[str] = None) -> List[Dict[str, Any]]:
        obs = self.observations.get(patient_id, [])
        if test_code:
            return [o for o in obs if any(c.get("code") == test_code for c in o.get("code", {}).get("coding", []))]
        return obs

    def get_encounters(self, patient_id: str) -> List[Dict[str, Any]]:
        return self.encounters.get(patient_id, [])

    def get_consent(self, patient_id: str) -> Optional[Dict[str, Any]]:
        return self.consents.get(patient_id)

# Global singleton
fhir_store = FHIRStore()
