"""
CareLoop HL7 v2 Parser
Parses HL7 v2 messages (specifically ADT^A03 Discharge and ORU^R01 Lab Results)
into normalized per-patient event objects.
"""

from typing import Dict, Any, Optional
from datetime import datetime

class HL7Parser:
    @staticmethod
    def parse_message(hl7_text: str) -> Dict[str, Any]:
        """
        Parses pipe-delimited HL7 message into a structured per-patient event.
        """
        lines = [line.strip() for line in hl7_text.strip().split("\n") if line.strip()]
        segments: Dict[str, list] = {}
        
        for line in lines:
            fields = line.split("|")
            seg_name = fields[0]
            if seg_name not in segments:
                segments[seg_name] = []
            segments[seg_name].append(fields)

        # Parse MSH
        msh = segments.get("MSH", [[]])[0]
        msg_type_field = msh[8] if len(msh) > 8 else ""
        msg_type = msg_type_field.split("^")[0] if "^" in msg_type_field else msg_type_field
        trigger_event = msg_type_field.split("^")[1] if "^" in msg_type_field else ""

        # Parse PID
        pid = segments.get("PID", [[]])[0]
        patient_id = ""
        patient_name = ""
        if len(pid) > 3:
            raw_pid = pid[3]
            patient_id = raw_pid.split("^")[0]
        if len(pid) > 5:
            patient_name = pid[5].replace("^", " ")

        timestamp = datetime.utcnow().isoformat() + "Z"

        if msg_type == "ADT" and trigger_event == "A03":
            # Discharge Event
            pv1 = segments.get("PV1", [[]])[0]
            discharge_disposition = pv1[36] if len(pv1) > 36 else "HOME"
            discharge_time = pv1[45] if len(pv1) > 45 else timestamp
            return {
                "eventType": "PATIENT_DISCHARGED",
                "patientId": patient_id,
                "patientName": patient_name,
                "timestamp": timestamp,
                "sourceMessage": f"ADT^{trigger_event}",
                "data": {
                    "dischargeTime": discharge_time,
                    "disposition": discharge_disposition
                }
            }

        elif msg_type == "ORU" and trigger_event == "R01":
            # Lab Result Event
            obx_list = segments.get("OBX", [])
            results = []
            is_critical = False
            for obx in obx_list:
                if len(obx) > 8:
                    code_field = obx[3].split("^")
                    loinc_code = code_field[0]
                    test_name = code_field[1] if len(code_field) > 1 else "Unknown Lab"
                    val = obx[5]
                    units = obx[6] if len(obx) > 6 else ""
                    ref_range = obx[7] if len(obx) > 7 else ""
                    abnormal_flag = obx[8] if len(obx) > 8 else "N"
                    
                    try:
                        numeric_val = float(val)
                    except ValueError:
                        numeric_val = val

                    if abnormal_flag in ["CH", "CL", "CRITICAL_HIGH", "CRITICAL_LOW"]:
                        is_critical = True

                    results.append({
                        "loinc": loinc_code,
                        "testName": test_name,
                        "value": numeric_val,
                        "unit": units,
                        "referenceRange": ref_range,
                        "flag": abnormal_flag
                    })

            return {
                "eventType": "CRITICAL_LAB_RESULT" if is_critical else "LAB_RESULT",
                "patientId": patient_id,
                "patientName": patient_name,
                "timestamp": timestamp,
                "sourceMessage": f"ORU^{trigger_event}",
                "data": {
                    "isCritical": is_critical,
                    "observations": results
                }
            }

        return {
            "eventType": "UNKNOWN",
            "patientId": patient_id,
            "patientName": patient_name,
            "timestamp": timestamp,
            "sourceMessage": f"{msg_type}^{trigger_event}",
            "data": {}
        }
