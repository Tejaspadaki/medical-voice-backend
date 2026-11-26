"""
Synthetic test scenarios for AuraDoc Clinical AI Decision Support.
NOTE: Synthetic tests verify software behavior, safety gating, and non-static outputs;
they do NOT constitute clinical validation.
"""
from datetime import datetime, timezone
import pytest
from fastapi import HTTPException

from app.api.v1.clinical_assessment import (
    analyze_clinical_case,
    approve_clinical_assessment,
    evaluate_medications_for_assessment,
    get_clinical_assessment,
    review_clinical_assessment,
)
from app.core.dependencies import MongoUser, require_roles
from app.schemas.clinical_assessment import (
    ClinicalApproveRequest,
    ClinicalAssessmentRequest,
    ClinicalReviewRequest,
    LabResultInput,
    MedicationEvaluationRequest,
    RecommendationReviewItem,
    VitalsInput,
)
from app.services.clinical_assessment_service import ClinicalAssessmentService
from app.services.medical_translator import EnglishToKannadaMedicalTranslator
from app.services.medication_decision_service import MedicationDecisionService


class FakeCollection:
    def __init__(self, initial=None):
        self.docs = list(initial or [])

    def find_one(self, query):
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                return dict(d)
        return None

    def find(self, query=None):
        query = query or {}
        return [dict(d) for d in self.docs if all(d.get(k) == v for k, v in query.items())]

    def insert_one(self, doc):
        self.docs.append(dict(doc))
        return True

    def update_one(self, query, update):
        for i, d in enumerate(self.docs):
            if all(d.get(k) == v for k, v in query.items()):
                if "$set" in update:
                    self.docs[i].update(update["$set"])
                return True
        return False


class FakeDB:
    def __init__(self):
        self.patients = FakeCollection([
            {
                "patient_id": 10,
                "full_name": "Synthetic Patient A",
                "gender": "Male",
                "age": 58,
                "allergies": ["Penicillin"],
                "existing_conditions": ["Hypertension", "Type 2 Diabetes"],
                "medical_history": ["Hypertension"],
                "current_medications": ["Telmisartan", "Metformin"],
            },
            {
                "patient_id": 11,
                "full_name": "Synthetic Patient B",
                "gender": "Female",
                "age": 26,
                "pregnancy_status": "pregnant",
                "allergies": [],
                "existing_conditions": ["Gastritis"],
                "medical_history": [],
                "current_medications": [],
            },
            {
                "patient_id": 12,
                "full_name": "Synthetic Patient C",
                "gender": "Male",
                "age": 62,
                "allergies": [],
                "existing_conditions": ["Coronary Artery Disease"],
                "medical_history": [],
                "current_medications": ["Clopidogrel"],
            },
        ])
        self.clinical_assessments = FakeCollection()
        self.clinical_audit_logs = FakeCollection()
        self.consultations = FakeCollection()
        self.medical_reports = FakeCollection()
        self.counters = FakeCollection()

    def __getattr__(self, name):
        col = FakeCollection()
        setattr(self, name, col)
        return col


def _doctor_user():
    return MongoUser({
        "user_id": 2,
        "email": "doctor@hospital.org",
        "full_name": "Dr. Test Doctor, MD",
        "role_id": 2,
        "role_name": "Doctor",
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
        "doctor_profile": {"registration_no": "KMC-99999"},
    })


def _staff_user():
    return MongoUser({
        "user_id": 3,
        "email": "staff@hospital.org",
        "full_name": "Nurse Test",
        "role_id": 3,
        "role_name": "Staff",
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    })


def test_different_disease_presentations_do_not_return_static_recommendations():
    req_gastritis = ClinicalAssessmentRequest(
        patient_id=10,
        symptoms=["epigastric pain", "burning sensation", "nausea"],
        symptom_duration="2 days",
        severity="moderate",
        age=42,
        gender="Male",
    )
    res_gastritis = ClinicalAssessmentService.analyze_patient(req_gastritis)
    meds_g, _, _, _ = MedicationDecisionService.evaluate_medications(res_gastritis)

    req_asthma = ClinicalAssessmentRequest(
        patient_id=11,
        symptoms=["wheezing", "cough"],
        symptom_duration="4 days",
        severity="moderate",
        age=29,
        gender="Female",
    )
    res_asthma = ClinicalAssessmentService.analyze_patient(req_asthma)
    meds_a, _, _, _ = MedicationDecisionService.evaluate_medications(res_asthma)

    assert res_gastritis["possible_conditions"][0]["condition_id"] == "acute_gastritis_apd"
    assert res_asthma["possible_conditions"][0]["condition_id"] == "bronchospasm_asthma"
    assert {m["generic_name"] for m in meds_g} != {m["generic_name"] for m in meds_a}
    assert all(c["is_preliminary"] is True for c in res_gastritis["possible_conditions"])


def test_identical_symptoms_different_patient_histories():
    req_htn = ClinicalAssessmentRequest(
        patient_id=1,
        symptoms=["headache", "fatigue"],
        age=58,
        gender="Male",
        existing_conditions=["Hypertension", "Type 2 Diabetes"],
        vitals=VitalsInput(bp="162/98"),
        lab_results=[LabResultInput(test_name="HbA1c", value="8.4", unit="%", interpretation="Elevated")],
    )
    res_htn = ClinicalAssessmentService.analyze_patient(req_htn)

    req_migraine = ClinicalAssessmentRequest(
        patient_id=2,
        symptoms=["headache", "fatigue"],
        age=24,
        gender="Female",
        existing_conditions=["Migraine"],
        vitals=VitalsInput(bp="114/74"),
    )
    res_migraine = ClinicalAssessmentService.analyze_patient(req_migraine)

    htn_ids = {c["condition_id"] for c in res_htn["possible_conditions"]}
    assert "essential_hypertension" in htn_ids
    assert "type2_diabetes" in htn_ids
    assert res_migraine["possible_conditions"][0]["condition_id"] == "migraine_headache"
    assert res_htn["possible_conditions"][0]["condition_id"] != res_migraine["possible_conditions"][0]["condition_id"]


def test_known_drug_allergy_flags_contraindicated():
    req = ClinicalAssessmentRequest(
        patient_id=10,
        symptoms=["fever", "sore throat", "cough"],
        allergies=["Penicillin"],
        requested_medications=["Amoxicillin"],
    )
    assessment = ClinicalAssessmentService.analyze_patient(req)
    opts, _, allergies, _ = MedicationDecisionService.evaluate_medications(assessment, ["Amoxicillin"])

    amox = next(o for o in opts if "Amoxicillin" in o["generic_name"])
    assert amox["safety_status"] == "contraindicated"
    assert len(amox["allergy_alerts"]) == 1
    assert len(allergies) >= 1


def test_existing_medication_interactions_and_contraindications():
    # Case 1: Telmisartan + Ibuprofen -> major interaction + Gastritis contraindication
    req = ClinicalAssessmentRequest(
        patient_id=10,
        symptoms=["headache"],
        existing_conditions=["Gastritis"],
        current_medications=["Telmisartan"],
        requested_medications=["Ibuprofen"],
    )
    assessment = ClinicalAssessmentService.analyze_patient(req)
    opts, interactions, _, _ = MedicationDecisionService.evaluate_medications(assessment, ["Ibuprofen"])
    ibu = next(o for o in opts if "Ibuprofen" in o["generic_name"])
    assert ibu["safety_status"] == "contraindicated"
    assert any(i["severity"] == "major" for i in interactions)

    # Case 2: Clopidogrel + Omeprazole -> major CYP2C19 interaction
    req2 = ClinicalAssessmentRequest(
        patient_id=12,
        symptoms=["acidity"],
        current_medications=["Clopidogrel"],
        requested_medications=["Omeprazole"],
    )
    a2 = ClinicalAssessmentService.analyze_patient(req2)
    opts2, inter2, _, _ = MedicationDecisionService.evaluate_medications(a2, ["Omeprazole"])
    ome = next(o for o in opts2 if "Omeprazole" in o["generic_name"])
    assert ome["safety_status"] == "contraindicated"
    assert any("Clopidogrel" in i["interacting_drug"] for i in inter2)


def test_incomplete_patient_information_and_unsupported_medication():
    req = ClinicalAssessmentRequest(
        patient_id=99,
        symptoms=["unspecified malaise"],
        requested_medications=["NonExistentWonderDrug 999mg"],
    )
    assessment = ClinicalAssessmentService.analyze_patient(req)
    opts, _, _, unsupported = MedicationDecisionService.evaluate_medications(assessment, ["NonExistentWonderDrug 999mg"])

    assert len(assessment["missing_clinical_information"]) >= 3
    assert len(unsupported) == 1
    assert "not in the verified clinical formulary" in unsupported[0]
    assert len(opts) == 0  # Never invents unsupported drugs or Paracetamol


def test_emergency_symptoms_and_critical_vitals():
    req = ClinicalAssessmentRequest(
        patient_id=12,
        symptoms=["chest pain", "shortness of breath"],
        vitals=VitalsInput(bp="190/122", spo2=88),
    )
    assessment = ClinicalAssessmentService.analyze_patient(req)
    assert assessment["has_emergency_flags"] is True
    assert len(assessment["emergency_warning_signs"]) >= 3


def test_kannada_terminology_and_no_paracetamol_fallback():
    res = EnglishToKannadaMedicalTranslator.extract_from_english_text("ರೋಗಿಗೆ ಹೊಟ್ಟೆ ಉರಿ ಮತ್ತು ವಾಂತಿ ಇದೆ")
    assert len(res["symptoms"]) >= 2
    assert res["medications"] == []  # No static Paracetamol fallback!


def test_api_endpoints_review_reject_approve_and_rbac(monkeypatch):
    monkeypatch.setattr(ClinicalAssessmentService, "_call_gemini_assessment", staticmethod(lambda *a, **kw: None))
    fake_db = FakeDB()
    doc_user = _doctor_user()
    staff_user = _staff_user()

    # 1. Analyze
    data = analyze_clinical_case(
        payload=ClinicalAssessmentRequest(
            patient_id=10,
            symptoms=["fever", "sore throat", "cough"],
            vitals=VitalsInput(bp="130/84"),
            requested_medications=["Amoxicillin", "Paracetamol"],
        ),
        db=fake_db,
        current_user=doc_user,
    )
    aid = data.assessment_id
    assert data.status == "PENDING_DOCTOR_REVIEW"
    assert len(data.allergy_warnings) >= 1

    # 2. Get
    fetched = get_clinical_assessment(assessment_id=aid, db=fake_db, current_user=doc_user)
    assert fetched.assessment_id == aid

    # 3. Evaluate additional medication
    eval_res = evaluate_medications_for_assessment(
        assessment_id=aid,
        payload=MedicationEvaluationRequest(requested_medications=["Cetirizine"]),
        db=fake_db,
        current_user=doc_user,
    )
    assert any("Cetirizine" in m.generic_name for m in eval_res.medication_options)

    # 4. Doctor Review (reject Amoxicillin, edit Paracetamol)
    amox_id = next(m.option_id for m in data.medication_options if "Amoxicillin" in m.generic_name)
    para_id = next(m.option_id for m in data.medication_options if "Paracetamol" in m.generic_name)

    rev_data = review_clinical_assessment(
        assessment_id=aid,
        payload=ClinicalReviewRequest(
            items=[
                RecommendationReviewItem(item_type="medication", item_id=amox_id, action="reject", doctor_notes="Penicillin allergy"),
                RecommendationReviewItem(item_type="medication", item_id=para_id, action="edit", edited_data={"dosage": "500mg", "duration": "3 days"}),
            ]
        ),
        db=fake_db,
        current_user=doc_user,
    )
    assert rev_data.status == "IN_REVIEW"

    # 5. Staff cannot approve (RBAC check)
    checker = require_roles(["Doctor", "Admin"])
    with pytest.raises(HTTPException) as exc_info:
        checker(current_user=staff_user)
    assert exc_info.value.status_code == 403

    # 6. Doctor approves
    app_resp = approve_clinical_assessment(
        assessment_id=aid,
        payload=ClinicalApproveRequest(doctor_signature_confirmed=True, generate_consultation_report=False),
        db=fake_db,
        current_user=doc_user,
    )
    assert app_resp["success"] is True
    assert app_resp["assessment"].status == "APPROVED"
    assert len(fake_db.clinical_audit_logs.docs) >= 4
