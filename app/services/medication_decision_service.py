import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.clinical_assessment import MedicationOption
from app.services.clinical_reference_kb import (
    DRUG_INTERACTIONS_KB,
    VERIFIED_CONDITIONS_KB,
    VERIFIED_DRUGS_KB,
)


class MedicationDecisionService:
    """
    Verified Medication Decision-Support Engine.
    Retrieves medication options strictly from VERIFIED_DRUGS_KB and evaluates:
    - Clinical indication & drug class
    - Patient allergies & cross-reactivity
    - Contraindications (existing conditions, pregnancy, labs/symptoms)
    - Drug-drug interactions against current medications & co-considered drugs
    - Age-related, weight-based, and pregnancy precautions
    - Local medicine availability & evidence references
    Never invents drug names, dosages, or durations, and never autonomously prescribes.
    """

    @staticmethod
    def _resolve_drug_key(drug_name: str) -> Optional[str]:
        q = (drug_name or "").strip().lower()
        if not q:
            return None
        if q in VERIFIED_DRUGS_KB:
            return q
        for key, info in VERIFIED_DRUGS_KB.items():
            if q == info["generic_name"].lower():
                return key
            if any(alias in q or q in alias for alias in info.get("aliases", [])):
                return key
        return None

    @staticmethod
    def _check_allergies(drug_key: str, drug_info: Dict[str, Any], patient_allergies: List[str]) -> List[Dict[str, Any]]:
        alerts: List[Dict[str, Any]] = []
        allergy_classes = [c.lower() for c in drug_info.get("allergy_classes", [])]
        aliases = [a.lower() for a in drug_info.get("aliases", [])]
        for allergen in patient_allergies:
            al = allergen.strip().lower()
            if not al:
                continue
            if any(al in cls or cls in al for cls in allergy_classes + aliases + [drug_key]):
                alerts.append({
                    "allergen": allergen,
                    "matched_drug": drug_info["generic_name"],
                    "cross_reactivity": drug_info["drug_class"],
                    "severity": "critical",
                    "message": f"ALLERGY ALERT: Patient has documented '{allergen}' allergy — {drug_info['generic_name']} ({drug_info['drug_class']}) is contraindicated.",
                })
        return alerts

    @staticmethod
    def _check_contraindications(
        drug_key: str,
        drug_info: Dict[str, Any],
        snapshot: Dict[str, Any],
        symptom_text: str,
    ) -> List[str]:
        matched_contras: List[str] = []
        cond_text = " ".join(snapshot.get("existing_conditions", []) + snapshot.get("medical_history", [])).lower()
        combined = f"{cond_text} {symptom_text}".lower()

        for cc in drug_info.get("condition_contraindications", []):
            if cc.lower() in combined:
                matched_contras.append(f"Condition/symptom contraindication match: '{cc}' present in patient history/presentation.")

        preg_status = str(snapshot.get("pregnancy_status", "unknown")).lower()
        if preg_status == "pregnant":
            preg_note = drug_info.get("pregnancy_category", "")
            if "CONTRAINDICATED" in preg_note.upper():
                matched_contras.append(f"Pregnancy contraindication: {preg_note}")

        return matched_contras

    @staticmethod
    def _check_interactions(
        drug_key: str,
        drug_info: Dict[str, Any],
        current_medications: List[str],
        other_candidate_keys: List[str],
    ) -> List[Dict[str, Any]]:
        warnings: List[Dict[str, Any]] = []
        drug_tokens = [drug_key] + [a.lower() for a in drug_info.get("aliases", [])] + [drug_info["drug_class"].lower()]

        def _matches_group(tokens: List[str], group: List[str]) -> bool:
            return any(g.lower() in t or t in g.lower() for t in tokens for g in group)

        # Check against patient's active current medications
        for cur_med in current_medications:
            cm_lower = cur_med.strip().lower()
            if not cm_lower:
                continue
            cm_tokens = [cm_lower]
            resolved_cm = MedicationDecisionService._resolve_drug_key(cm_lower)
            if resolved_cm and resolved_cm in VERIFIED_DRUGS_KB:
                cm_tokens.append(resolved_cm)
                cm_tokens.append(VERIFIED_DRUGS_KB[resolved_cm]["drug_class"].lower())

            for rule in DRUG_INTERACTIONS_KB:
                a_self = _matches_group(drug_tokens, rule["drug_a"])
                b_other = _matches_group(cm_tokens, rule["drug_b"])
                b_self = _matches_group(drug_tokens, rule["drug_b"])
                a_other = _matches_group(cm_tokens, rule["drug_a"])
                if (a_self and b_other) or (b_self and a_other):
                    warnings.append({
                        "interacting_drug": cur_med,
                        "source": "current_medication",
                        "severity": rule["severity"],
                        "mechanism": rule["mechanism"],
                        "recommendation": rule["recommendation"],
                    })

        # Check against other co-considered options
        for other_key in other_candidate_keys:
            if other_key == drug_key or other_key not in VERIFIED_DRUGS_KB:
                continue
            other_info = VERIFIED_DRUGS_KB[other_key]
            other_tokens = [other_key] + [a.lower() for a in other_info.get("aliases", [])] + [other_info["drug_class"].lower()]
            for rule in DRUG_INTERACTIONS_KB:
                a_self = _matches_group(drug_tokens, rule["drug_a"])
                b_other = _matches_group(other_tokens, rule["drug_b"])
                b_self = _matches_group(drug_tokens, rule["drug_b"])
                a_other = _matches_group(other_tokens, rule["drug_a"])
                if (a_self and b_other) or (b_self and a_other):
                    warnings.append({
                        "interacting_drug": other_info["generic_name"],
                        "source": "co_recommended_option",
                        "severity": rule["severity"],
                        "mechanism": rule["mechanism"],
                        "recommendation": rule["recommendation"],
                    })

        return warnings

    @staticmethod
    def _build_precautions(drug_info: Dict[str, Any], snapshot: Dict[str, Any]) -> List[str]:
        precautions: List[str] = []
        age = snapshot.get("age")
        weight_kg = snapshot.get("weight_kg")
        age_rules = drug_info.get("age_precautions") or {}

        if age is not None:
            if age_rules.get("pediatric_max_age") and age <= age_rules["pediatric_max_age"]:
                precautions.append(f"Pediatric precaution (age {age}y): {age_rules.get('pediatric_note')}")
            if age_rules.get("geriatric_min_age") and age >= age_rules["geriatric_min_age"]:
                precautions.append(f"Geriatric precaution (age {age}y): {age_rules.get('geriatric_note')}")

        if weight_kg is not None and age is not None and age <= 12:
            precautions.append(f"Weight-based verification required (recorded weight: {weight_kg} kg).")

        preg = str(snapshot.get("pregnancy_status", "unknown")).lower()
        if preg in ("pregnant", "lactating"):
            precautions.append(f"Pregnancy/Lactation ({preg}): {drug_info.get('pregnancy_category')}")
        elif str(snapshot.get("gender", "")).lower() == "female" and age is not None and 12 <= age <= 50:
            if "CONTRAINDICATED" in drug_info.get("pregnancy_category", "").upper():
                precautions.append(f"Childbearing-age caution: Confirm pregnancy status — {drug_info.get('pregnancy_category')}")

        return precautions

    @classmethod
    def evaluate_medications(
        cls,
        assessment_doc: Dict[str, Any],
        requested_medications: Optional[List[str]] = None,
        target_indication: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
        snapshot = assessment_doc.get("patient_snapshot") or {}
        possible_conditions = assessment_doc.get("possible_conditions") or []
        extracted_symptoms = assessment_doc.get("extracted_symptoms") or []
        symptom_text = " ".join([s.get("name", "") for s in extracted_symptoms]).lower()

        candidate_keys: List[str] = []
        indication_map: Dict[str, str] = {}
        unsupported_requests: List[str] = []

        # 1. Resolve explicit requested medications (flag unsupported ones instead of inventing!)
        for req_med in (requested_medications or []):
            resolved = cls._resolve_drug_key(req_med)
            if resolved:
                if resolved not in candidate_keys:
                    candidate_keys.append(resolved)
                    indication_map[resolved] = target_indication or "Doctor/Consultation requested evaluation"
            else:
                unsupported_requests.append(
                    f"Requested medication '{req_med}' is not in the verified clinical formulary reference; cannot invent dosage or safety profile."
                )

        # 2. Retrieve condition-appropriate drugs from verified conditions KB
        cond_by_id = {c["condition_id"]: c for c in VERIFIED_CONDITIONS_KB}
        for pc in possible_conditions:
            cid = pc.get("condition_id")
            kb_cond = cond_by_id.get(cid)
            if kb_cond:
                for dk in kb_cond.get("first_line_drugs", []):
                    if dk not in candidate_keys and dk in VERIFIED_DRUGS_KB:
                        candidate_keys.append(dk)
                        indication_map[dk] = pc.get("condition_name", kb_cond["condition_name"])

        options: List[Dict[str, Any]] = []
        all_interaction_alerts: List[Dict[str, Any]] = []
        all_allergy_warnings: List[Dict[str, Any]] = []

        patient_allergies = snapshot.get("allergies") or []
        current_medications = snapshot.get("current_medications") or []

        for dk in candidate_keys:
            info = VERIFIED_DRUGS_KB[dk]
            allergy_alerts = cls._check_allergies(dk, info, patient_allergies)
            contra_matches = cls._check_contraindications(dk, info, snapshot, symptom_text)
            interactions = cls._check_interactions(dk, info, current_medications, candidate_keys)
            precautions = cls._build_precautions(info, snapshot)

            safety_status = "safe_to_consider"
            if allergy_alerts or contra_matches:
                safety_status = "contraindicated"
            elif interactions or precautions:
                if any(w.get("severity") == "major" for w in interactions):
                    safety_status = "contraindicated"
                else:
                    safety_status = "caution_required"

            for al in allergy_alerts:
                all_allergy_warnings.append(al)
            for iw in interactions:
                all_interaction_alerts.append({
                    "drug": info["generic_name"],
                    **iw,
                })

            opt = MedicationOption(
                option_id=f"MED-{uuid.uuid4().hex[:8].upper()}",
                generic_name=info["generic_name"],
                kannada_name=info["kannada_name"],
                drug_class=info["drug_class"],
                indication=indication_map.get(dk) or ", ".join(info["indications"]),
                suggested_dosage_reference=info["dosage_reference"],
                suggested_frequency_reference=info["frequency_reference"],
                suggested_duration_reference=info["duration_reference"],
                contraindications=contra_matches + info["contraindications"],
                side_effects=info["side_effects"],
                interaction_warnings=interactions,
                allergy_alerts=allergy_alerts,
                precautions=precautions,
                local_availability=info["local_availability"],
                evidence_references=info["evidence_references"],
                safety_status=safety_status,
                review_status="pending_review",
            )
            options.append(opt.model_dump())

        return options, all_interaction_alerts, all_allergy_warnings, unsupported_requests
