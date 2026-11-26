import json
import re
import uuid
from datetime import datetime, date, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.schemas.clinical_assessment import (
    ClinicalAssessmentRequest,
    EmergencyWarningSign,
    PossibleCondition,
    RecommendedInvestigation,
)
from app.services.clinical_reference_kb import (
    EMERGENCY_RED_FLAGS_KB,
    VERIFIED_CONDITIONS_KB,
)


def _compute_age_from_dob(dob_val: Any) -> Optional[int]:
    if not dob_val:
        return None
    try:
        if isinstance(dob_val, date) and not isinstance(dob_val, datetime):
            born = dob_val
        else:
            born = datetime.fromisoformat(str(dob_val).split("T")[0]).date()
        today = date.today()
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    except Exception:
        return None


def _parse_bp(bp_str: Optional[str], systolic: Optional[int], diastolic: Optional[int]) -> Tuple[Optional[int], Optional[int]]:
    if systolic is not None and diastolic is not None:
        return systolic, diastolic
    if bp_str:
        m = re.search(r"(\d{2,3})\s*/\s*(\d{2,3})", str(bp_str))
        if m:
            return int(m.group(1)), int(m.group(2))
    return systolic, diastolic


class ClinicalAssessmentService:
    """
    Patient-specific clinical assessment engine.
    Evaluates symptoms, duration, severity, demographics, history, conditions,
    allergies, current medications, vitals, and lab results.
    Outputs preliminary differential considerations — never confirmed diagnoses.
    """

    @staticmethod
    def normalize_symptoms(raw_symptoms: List[Any], default_duration: Optional[str], default_severity: Optional[str]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for idx, item in enumerate(raw_symptoms or []):
            if isinstance(item, str):
                name = item.strip()
                if name:
                    normalized.append({
                        "symptom_id": f"sym_{idx + 1}",
                        "name": name,
                        "kannada_name": None,
                        "duration": default_duration,
                        "severity": default_severity,
                    })
            elif isinstance(item, dict):
                name = (item.get("name") or item.get("english") or item.get("entity") or "").strip()
                if name:
                    normalized.append({
                        "symptom_id": f"sym_{idx + 1}",
                        "name": name,
                        "kannada_name": item.get("kannada_name") or item.get("kannada") or (item.get("entity") if item.get("english") else None),
                        "duration": item.get("duration") or default_duration,
                        "severity": item.get("severity") or default_severity,
                    })
            else:
                name = getattr(item, "name", "").strip()
                if name:
                    normalized.append({
                        "symptom_id": f"sym_{idx + 1}",
                        "name": name,
                        "kannada_name": getattr(item, "kannada_name", None),
                        "duration": getattr(item, "duration", None) or default_duration,
                        "severity": getattr(item, "severity", None) or default_severity,
                    })
        return normalized

    @staticmethod
    def build_patient_snapshot(patient_doc: Optional[Dict[str, Any]], req: ClinicalAssessmentRequest) -> Dict[str, Any]:
        p = patient_doc or {}
        age = req.age if req.age is not None else p.get("age") or _compute_age_from_dob(p.get("dob"))
        gender = req.gender or p.get("gender") or "Unknown"
        weight_kg = req.weight_kg if req.weight_kg is not None else p.get("weight_kg")
        pregnancy_status = req.pregnancy_status if req.pregnancy_status and req.pregnancy_status != "unknown" else p.get("pregnancy_status", "unknown")

        allergies = list(dict.fromkeys([a.strip() for a in (req.allergies or p.get("allergies") or []) if str(a).strip()]))
        existing_conditions = list(dict.fromkeys([c.strip() for c in (req.existing_conditions or p.get("existing_conditions") or []) if str(c).strip()]))
        medical_history = list(dict.fromkeys([h.strip() for h in (req.medical_history or p.get("medical_history") or []) if str(h).strip()]))
        current_medications = list(dict.fromkeys([m.strip() for m in (req.current_medications or p.get("current_medications") or []) if str(m).strip()]))

        return {
            "patient_id": req.patient_id,
            "full_name": p.get("full_name", f"Patient #{req.patient_id}"),
            "age": age,
            "gender": gender,
            "weight_kg": weight_kg,
            "pregnancy_status": pregnancy_status,
            "blood_group": p.get("blood_group"),
            "allergies": allergies,
            "existing_conditions": existing_conditions,
            "medical_history": medical_history,
            "current_medications": current_medications,
            "vitals": req.vitals.model_dump() if req.vitals else {},
            "lab_results": [l.model_dump() for l in req.lab_results],
        }

    @staticmethod
    def detect_emergency_flags(
        extracted_symptoms: List[Dict[str, Any]],
        clinical_notes: Optional[str],
        vitals: Dict[str, Any],
    ) -> List[EmergencyWarningSign]:
        flags: List[EmergencyWarningSign] = []
        combined_text = " ".join(
            [s.get("name", "") + " " + (s.get("kannada_name") or "") for s in extracted_symptoms]
            + [clinical_notes or ""]
        ).lower()

        for rf in EMERGENCY_RED_FLAGS_KB:
            matched = [t for t in rf["triggers"] if t.lower() in combined_text]
            if matched:
                flags.append(
                    EmergencyWarningSign(
                        sign=rf["sign"],
                        kannada_sign=rf["kannada_sign"],
                        severity=rf["severity"],
                        action_required=rf["action_required"],
                        matched_triggers=matched,
                    )
                )

        sys_bp, dia_bp = _parse_bp(vitals.get("bp"), vitals.get("systolic"), vitals.get("diastolic"))
        if (sys_bp is not None and sys_bp >= 180) or (dia_bp is not None and dia_bp >= 120):
            flags.append(
                EmergencyWarningSign(
                    sign=f"Hypertensive Crisis Range BP ({sys_bp}/{dia_bp} mmHg)",
                    kannada_sign=f"ಅತಿ ತೀವ್ರ ರಕ್ತದೊತ್ತಡ ({sys_bp}/{dia_bp} mmHg)",
                    severity="critical",
                    action_required="Evaluate immediately for end-organ damage (chest pain, neuro deficit, dyspnea) and urgent BP management.",
                    matched_triggers=[f"BP {sys_bp}/{dia_bp}"],
                )
            )

        spo2 = vitals.get("spo2")
        if spo2 is not None and spo2 < 92:
            flags.append(
                EmergencyWarningSign(
                    sign=f"Hypoxemia (SpO2 {spo2}%)",
                    kannada_sign=f"ರಕ್ತದಲ್ಲಿ ಆಮ್ಲಜನಕದ ಕೊರತೆ (SpO2 {spo2}%)",
                    severity="critical",
                    action_required="Administer supplemental oxygen and perform immediate respiratory/cardiopulmonary assessment.",
                    matched_triggers=[f"SpO2 {spo2}%"],
                )
            )

        return flags

    @staticmethod
    def identify_missing_information(
        snapshot: Dict[str, Any],
        extracted_symptoms: List[Dict[str, Any]],
        vitals: Dict[str, Any],
        lab_results: List[Dict[str, Any]],
    ) -> List[str]:
        missing: List[str] = []
        if not extracted_symptoms:
            missing.append("No structured symptoms provided; symptom onset, duration, and severity are needed.")
        else:
            if any(not s.get("duration") for s in extracted_symptoms):
                missing.append("Symptom duration missing for one or more presenting complaints.")
            if any(not s.get("severity") for s in extracted_symptoms):
                missing.append("Symptom severity (mild/moderate/severe) not specified.")

        if not vitals or (not vitals.get("bp") and not vitals.get("systolic") and not vitals.get("temperature") and not vitals.get("spo2")):
            missing.append("Baseline vitals (BP, Temperature, Pulse, SpO2) not recorded.")

        if not snapshot.get("allergies"):
            missing.append("Drug allergy status not explicitly documented (confirm 'No Known Drug Allergies' before prescribing).")

        if snapshot.get("age") is None:
            missing.append("Patient age not recorded (required for pediatric/geriatric dosing precautions).")

        gender_lower = str(snapshot.get("gender", "")).lower()
        age = snapshot.get("age")
        if gender_lower == "female" and age is not None and 12 <= age <= 50 and snapshot.get("pregnancy_status") == "unknown":
            missing.append("Pregnancy/lactation status unknown for female patient of childbearing age (essential before teratogenic drugs like ARBs/NSAIDs).")

        conditions_str = " ".join(snapshot.get("existing_conditions", []) + snapshot.get("medical_history", [])).lower()
        if ("diabetes" in conditions_str or "hypertension" in conditions_str or "kidney" in conditions_str) and not lab_results:
            missing.append("Recent renal function (Serum Creatinine/eGFR) & metabolic labs (HbA1c/Electrolytes) not attached for chronic disease history.")

        return missing

    @classmethod
    def _call_gemini_assessment(cls, snapshot: Dict[str, Any], extracted_symptoms: List[Dict[str, Any]], clinical_notes: Optional[str]) -> Optional[Dict[str, Any]]:
        if not settings.GEMINI_API_KEY:
            return None

        prompt = (
            "You are a clinical decision-support AI assisting a licensed physician in an Indian hospital OPD. "
            "Evaluate the patient-specific data below and return ONLY valid JSON.\n"
            "CRITICAL RULES:\n"
            "1. Do NOT claim predictions are confirmed diagnoses.\n"
            "2. Base differentials strictly on the provided symptoms, vitals, history, and labs.\n"
            "3. Do NOT invent lab results.\n"
            f"Patient Snapshot: {json.dumps(snapshot, default=str)}\n"
            f"Symptoms: {json.dumps(extracted_symptoms, default=str)}\n"
            f"Clinical Notes: {clinical_notes or 'None'}\n\n"
            'Return JSON with keys: "clinical_assessment_summary" (str), "kannada_summary" (str), '
            '"additional_findings" (list of str), "differential_notes" (list of {"condition_name": str, "rationale": str, "likelihood": "high"|"moderate"|"low"}).'
        )
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.15, "responseMimeType": "application/json"},
            }
            with httpx.Client(timeout=8.0) as client:
                resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    text_out = data["candidates"][0]["content"]["parts"][0]["text"]
                    return json.loads(text_out)
        except Exception as e:
            logger.warning(f"Gemini assessment call skipped/fallback: {e}")
        return None

    @classmethod
    def analyze_patient(
        cls,
        req: ClinicalAssessmentRequest,
        patient_doc: Optional[Dict[str, Any]] = None,
        created_by_user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        snapshot = cls.build_patient_snapshot(patient_doc, req)
        extracted_symptoms = cls.normalize_symptoms(req.symptoms, req.symptom_duration, req.severity)
        vitals = snapshot.get("vitals") or {}
        lab_results = snapshot.get("lab_results") or []

        emergency_flags = cls.detect_emergency_flags(extracted_symptoms, req.clinical_notes, vitals)
        missing_info = cls.identify_missing_information(snapshot, extracted_symptoms, vitals, lab_results)

        symptom_text = " ".join(
            [s.get("name", "") + " " + (s.get("kannada_name") or "") for s in extracted_symptoms]
            + [req.clinical_notes or ""]
        ).lower()
        history_text = " ".join(snapshot.get("existing_conditions", []) + snapshot.get("medical_history", [])).lower()
        labs_text = " ".join([f"{l.get('test_name', '')} {l.get('value', '')} {l.get('interpretation', '')}" for l in lab_results]).lower()
        sys_bp, dia_bp = _parse_bp(vitals.get("bp"), vitals.get("systolic"), vitals.get("diastolic"))

        matched_conditions: List[Tuple[float, PossibleCondition, List[Dict[str, Any]]]] = []
        supporting_findings: List[str] = []

        if sys_bp is not None and dia_bp is not None:
            supporting_findings.append(f"Recorded Blood Pressure: {sys_bp}/{dia_bp} mmHg")
        if vitals.get("temperature"):
            supporting_findings.append(f"Recorded Temperature: {vitals['temperature']}")
        if vitals.get("spo2") is not None:
            supporting_findings.append(f"Recorded SpO2: {vitals['spo2']}%")
        if snapshot.get("existing_conditions"):
            supporting_findings.append(f"Existing conditions: {', '.join(snapshot['existing_conditions'])}")
        if snapshot.get("allergies"):
            supporting_findings.append(f"Documented allergies: {', '.join(snapshot['allergies'])}")
        for l in lab_results:
            supporting_findings.append(f"Lab: {l.get('test_name')} = {l.get('value')} {l.get('unit') or ''} ({l.get('interpretation') or 'pending review'})".strip())

        for cond in VERIFIED_CONDITIONS_KB:
            matched_syms = [kw for kw in cond["symptom_keywords"] if kw.lower() in symptom_text]
            history_hit = any(kw.lower() in history_text for kw in cond["symptom_keywords"])
            vital_hit = False
            vt = cond.get("vital_triggers") or {}
            if vt and sys_bp is not None and dia_bp is not None:
                if sys_bp >= vt.get("bp_systolic_gte", 999) or dia_bp >= vt.get("bp_diastolic_gte", 999):
                    vital_hit = True

            lab_hit = False
            if cond["condition_id"] == "type2_diabetes" and ("hba1c" in labs_text or "glucose" in labs_text or "sugar" in labs_text):
                lab_hit = True

            score = len(matched_syms) * 0.22 + (0.25 if history_hit else 0.0) + (0.35 if vital_hit else 0.0) + (0.25 if lab_hit else 0.0)
            if len(matched_syms) >= cond.get("min_matches", 1) or vital_hit or (history_hit and len(matched_syms) >= 1) or lab_hit:
                bounded_conf = round(min(0.88, max(0.35, score)), 2)
                likelihood = "high" if bounded_conf >= 0.7 else "moderate" if bounded_conf >= 0.5 else "low"

                rationale_parts = []
                if matched_syms:
                    rationale_parts.append(f"Symptoms aligned: {', '.join(dict.fromkeys(matched_syms))}")
                if vital_hit:
                    rationale_parts.append(f"Elevated BP ({sys_bp}/{dia_bp} mmHg)")
                if history_hit:
                    rationale_parts.append("Consistent with documented medical history")
                if lab_hit:
                    rationale_parts.append("Supported by attached laboratory findings")

                pc = PossibleCondition(
                    condition_id=cond["condition_id"],
                    condition_name=cond["condition_name"],
                    kannada_name=cond["kannada_name"],
                    icd10_code=cond.get("icd10_code"),
                    likelihood=likelihood,
                    confidence_score=bounded_conf,
                    supporting_symptoms=list(dict.fromkeys(matched_syms)),
                    rationale="; ".join(rationale_parts) or "Clinical presentation match",
                    is_preliminary=True,
                )
                matched_conditions.append((bounded_conf, pc, cond.get("investigations", [])))

        matched_conditions.sort(key=lambda x: x[0], reverse=True)

        possible_conditions = [item[1] for item in matched_conditions[:2]]
        differential_diagnosis = [item[1] for item in matched_conditions[2:5]]

        # Collect deduplicated investigations relevant to matched conditions
        inv_seen = set()
        investigations: List[RecommendedInvestigation] = []
        for _, _, invs in matched_conditions[:3]:
            for inv in invs:
                if inv["investigation_id"] not in inv_seen:
                    inv_seen.add(inv["investigation_id"])
                    investigations.append(RecommendedInvestigation(**inv))

        # If no specific condition matched, explicitly state clinical uncertainty instead of guessing!
        if not possible_conditions:
            investigations.append(
                RecommendedInvestigation(
                    investigation_id="inv_baseline_eval",
                    test_name="Comprehensive History, Physical Exam & Baseline Vitals/CBC",
                    kannada_name="ಸಮಗ್ರ ವೈದ್ಯಕೀಯ ತಪಾಸಣೆ ಮತ್ತು ಪ್ರಾಥಮಿಕ ರಕ್ತ ಪರೀಕ್ಷೆ",
                    rationale="Presenting complaints are non-specific or insufficient for narrow differential.",
                    priority="routine",
                )
            )

        # Optional Gemini enrichment (strictly advisory)
        gemini_data = cls._call_gemini_assessment(snapshot, extracted_symptoms, req.clinical_notes)
        if gemini_data:
            summary_en = gemini_data.get("clinical_assessment_summary") or cls._build_summary_en(snapshot, possible_conditions, emergency_flags)
            summary_kn = gemini_data.get("kannada_summary") or cls._build_summary_kn(snapshot, possible_conditions, emergency_flags)
            for af in gemini_data.get("additional_findings", [])[:3]:
                if isinstance(af, str) and af not in supporting_findings:
                    supporting_findings.append(af)
        else:
            summary_en = cls._build_summary_en(snapshot, possible_conditions, emergency_flags)
            summary_kn = cls._build_summary_kn(snapshot, possible_conditions, emergency_flags)

        uncertainty_reasons = []
        if missing_info:
            uncertainty_reasons.append(f"{len(missing_info)} clinical data gap(s) identified")
        if not lab_results:
            uncertainty_reasons.append("No laboratory confirmation attached")
        if not possible_conditions:
            uncertainty_reasons.append("Insufficient specific symptom/vital triggers for ranked condition match")

        uncertainty_and_confidence = {
            "overall_confidence": possible_conditions[0].confidence_score if possible_conditions else None,
            "is_validated_clinical_probability": False,
            "confidence_basis": "Heuristic symptom/vital/history alignment score (not a validated diagnostic probability)",
            "uncertainty_reasons": uncertainty_reasons,
            "requires_doctor_confirmation": True,
        }

        now = datetime.now(timezone.utc)
        return {
            "assessment_id": f"ASM-{uuid.uuid4().hex[:10].upper()}",
            "patient_id": req.patient_id,
            "patient_snapshot": snapshot,
            "extracted_symptoms": extracted_symptoms,
            "clinical_assessment_summary": summary_en,
            "kannada_summary": summary_kn,
            "disclaimer": (
                "AI-generated clinical decision support only. Not a confirmed diagnosis. "
                "Mandatory qualified doctor review and approval required before prescribing."
            ),
            "possible_conditions": [c.model_dump() for c in possible_conditions],
            "differential_diagnosis": [d.model_dump() for d in differential_diagnosis],
            "supporting_clinical_findings": supporting_findings,
            "missing_clinical_information": missing_info,
            "recommended_investigations": [i.model_dump() for i in investigations],
            "emergency_warning_signs": [e.model_dump() for e in emergency_flags],
            "has_emergency_flags": len(emergency_flags) > 0,
            "uncertainty_and_confidence": uncertainty_and_confidence,
            "medication_options": [],
            "drug_interaction_alerts": [],
            "allergy_warnings": [],
            "unsupported_requests": [],
            "status": "PENDING_DOCTOR_REVIEW",
            "created_by_user_id": created_by_user_id,
            "reviewed_by_user_id": None,
            "approved_by_user_id": None,
            "consultation_id": None,
            "created_at": now,
            "updated_at": now,
            "approved_at": None,
        }

    @staticmethod
    def _build_summary_en(snapshot: Dict[str, Any], possible: List[PossibleCondition], flags: List[EmergencyWarningSign]) -> str:
        name = snapshot.get("full_name", "Patient")
        age = snapshot.get("age")
        age_str = f"{age}y" if age is not None else "age unknown"
        if flags:
            return (
                f"URGENT CLINICAL ALERT for {name} ({age_str}, {snapshot.get('gender')}): "
                f"{len(flags)} emergency warning sign(s) detected ({flags[0].sign}). "
                f"Immediate physician evaluation required."
            )
        if possible:
            cond_names = ", ".join([c.condition_name for c in possible])
            return (
                f"Preliminary clinical decision-support assessment for {name} ({age_str}, {snapshot.get('gender')}): "
                f"Consider {cond_names} based on presenting symptoms, vitals, and history. "
                f"Doctor verification required before diagnosis or prescribing."
            )
        return (
            f"Preliminary assessment for {name} ({age_str}, {snapshot.get('gender')}): "
            f"Presenting clinical data is insufficient for a specific condition match. "
            f"Gather missing clinical history/vitals and perform physician evaluation."
        )

    @staticmethod
    def _build_summary_kn(snapshot: Dict[str, Any], possible: List[PossibleCondition], flags: List[EmergencyWarningSign]) -> str:
        name = snapshot.get("full_name", "ರೋಗಿ")
        if flags:
            return f"ತುರ್ತು ಎಚ್ಚರಿಕೆ ({name}): {flags[0].kannada_sign}. ತಕ್ಷಣ ವೈದ್ಯರ ತುರ್ತು ತಪಾಸಣೆ ಅಗತ್ಯವಿದೆ."
        if possible:
            cond_kn = ", ".join([c.kannada_name for c in possible])
            return f"ರೋಗಿ {name} ಅವರ ಪ್ರಾಥಮಿಕ AI ವಿಶ್ಲೇಷಣೆ: {cond_kn} ಸಾಧ್ಯತೆ ಪರಿಗಣಿಸಬಹುದು. ವೈದ್ಯರ ಅಂತಿಮ ದೃಢೀಕರಣ ಕಡ್ಡಾಯವಾಗಿದೆ."
        return f"ರೋಗಿ {name} ಅವರ ಲಕ್ಷಣಗಳ ಆಧಾರದ ಮೇಲೆ ಹೆಚ್ಚಿನ ವೈದ್ಯಕೀಯ ಮಾಹಿತಿ ಮತ್ತು ತಪಾಸಣೆ ಅಗತ್ಯವಿದೆ."
