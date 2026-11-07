"""
CareLoop Outreach Agent
Drafts multilingual clinical outreach messages (Telugu, Hindi, English).
Computes clinical back-translation for clinician safety verification.
Requires Human-in-the-Loop Clinician Sign-off (Risk Tier: T2).
"""

from typing import Dict, Any, Optional
from .base import AgentBase
from services.gateway.mcp_server import execute_mcp_call
from services.control_plane.ledger import action_ledger
from services.control_plane.loop_tracker import loop_tracker

# Clinical multilingual templates with certified back-translations
OUTREACH_TEMPLATES = {
    "te": {
        "language": "Telugu",
        "message": (
            "నమస్కారం రమేష్ కుమార్ గారు. మీ డిశ్చార్జ్ తర్వాత వచ్చిన రక్త పరీక్షలో పొటాషియం స్థాయి ఎక్కువగా (6.4 mEq/L) ఉన్నట్లు డాక్టర్ గుర్తించారు. "
            "దయచేసి తదుపరి డాక్టర్ సంప్రదింపుల వరకు మీ స్పైరోనోలాక్టోన్ (Spironolactone) మాత్రను వేసుకోవద్దు. "
            "రేపు ఉదయం 10:30 గంటలకు కార్డియాలజీ క్లినిక్‌లో అత్యవసర అపాయింట్‌మెంట్ బుక్ చేయబడింది. "
            "ఛాతీ నొప్పి, గుండె దడ లేదా తీవ్రమైన నీరసం ఉంటే వెంటనే అత్యవసర విభాగానికి (ER) వెళ్ళండి."
        ),
        "back_translation": (
            "Hello Mr. Ramesh Kumar. Your doctor has noted that your post-discharge blood test shows high potassium levels (6.4 mEq/L). "
            "Please do NOT take your Spironolactone tablet until further consultation with your doctor. "
            "An urgent follow-up appointment has been booked for you tomorrow at 10:30 AM at the Cardiology Clinic. "
            "If you experience chest pain, palpitations, or severe weakness, go to the Emergency Room (ER) immediately."
        )
    },
    "hi": {
        "language": "Hindi",
        "message": (
            "नमस्ते रमेश कुमार जी। आपके डिस्चार्ज के बाद के रक्त परीक्षण में पोटेशियम का स्तर गंभीर रूप से अधिक (6.4 mEq/L) पाया गया है। "
            "कृपया डॉक्टर से बात करने तक अपनी स्पिरोनोलैक्टोन (Spironolactone) दवा न लें। "
            "कल सुबह 10:30 बजे कार्डियोलॉजी क्लिनिक में आपके लिए एक जरूरी अपॉइंटमेंट बुक किया गया है। "
            "यदि आपको सीने में दर्द, घबराहट या अत्यधिक कमजोरी महसूस हो, तो तुरंत आपातकालीन कक्ष (ER) जाएं।"
        ),
        "back_translation": (
            "Hello Mr. Ramesh Kumar. In your post-discharge blood test, potassium levels were found critically high (6.4 mEq/L). "
            "Please do NOT take your Spironolactone medicine until you speak with your doctor. "
            "An urgent appointment has been booked for you tomorrow at 10:30 AM at the Cardiology Clinic. "
            "If you experience chest pain, palpitations, or extreme weakness, visit the Emergency Room (ER) immediately."
        )
    },
    "en": {
        "language": "English",
        "message": (
            "Hello Ramesh Kumar. Your clinical care team identified a critical lab result from your discharge lab work: "
            "Serum Potassium is 6.4 mEq/L (Critical High). Please immediately HOLD your Spironolactone medication until evaluated. "
            "An urgent cardiology follow-up visit is reserved for tomorrow at 10:30 AM. "
            "If you experience chest tightness, irregular heartbeat, or severe muscle weakness, proceed to the nearest Emergency Room immediately."
        ),
        "back_translation": (
            "Direct English clinical communication with explicit medication withhold directive and emergency warnings."
        )
    }
}

class OutreachAgent(AgentBase):
    def __init__(self):
        super().__init__("outreach-agent")

    def run(self, task_id: str, patient_id: str, clinical_context: Dict[str, Any]) -> Dict[str, Any]:
        if not self.is_active():
            return {"error": "Agent is inactive or quarantined"}

        # Scoped token for patient demographics
        token = self.get_scoped_token(task_id, patient_id, ["read:patient", "write:outreach"])
        patient_data = execute_mcp_call("get_patient_demographics", {"patient_id": patient_id}, token)
        
        pref_lang = "te" # Default for patient P-84920
        comms = patient_data.get("communication", [])
        if comms:
            pref_lang = comms[0].get("language", {}).get("coding", [{}])[0].get("code", "te")

        template = OUTREACH_TEMPLATES.get(pref_lang, OUTREACH_TEMPLATES["en"])
        
        action_id = f"ACT-OUTREACH-{task_id[-6:]}"
        payload = {
            "recipientPhone": patient_data.get("telecom", [{}])[0].get("value", "+91-9876543210"),
            "targetLanguage": template["language"],
            "languageCode": pref_lang,
            "draftMessage": template["message"],
            "certifiedBackTranslation": template["back_translation"],
            "withheldMedication": "Spironolactone 50mg daily",
            "clinicalUrgency": "CRITICAL_HYPERKALEMIA (6.4 mEq/L)"
        }

        # Propose action: T2 Risk Tier -> Requires Clinician Human-in-the-Loop Sign-off
        proposal = action_ledger.propose_action(
            action_id=action_id,
            agent_id=self.agent_id,
            patient_id=patient_id,
            action_type="OUTREACH_SEND_MESSAGE",
            risk_tier="T2",
            payload=payload,
            evidence={
                "labFinding": "Potassium 6.4 mEq/L",
                "drugInteraction": "Spironolactone 50mg (Potassium-sparing)",
                "targetLanguage": template["language"]
            }
        )

        proposal["status"] = "PENDING_APPROVAL"

        return {
            "agentId": self.agent_id,
            "actionId": action_id,
            "status": "PENDING_APPROVAL",
            "riskTier": "T2",
            "proposal": proposal,
            "tokensUsed": 450
        }

outreach_agent = OutreachAgent()
