import uuid
from datetime import datetime, timezone
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.dependencies import MongoUser, require_roles
from app.core.logging import logger
from app.db.mongo import clean_doc, get_mongo_db
from app.schemas.clinical_assessment import (
    ClinicalApproveRequest,
    ClinicalAssessmentRequest,
    ClinicalAssessmentResponse,
    ClinicalReviewRequest,
    MedicationEvaluationRequest,
)
from app.schemas.consultation import ConsultationCreateRequest
from app.services.clinical_assessment_service import ClinicalAssessmentService
from app.services.consultation_service import ConsultationService
from app.services.medication_decision_service import MedicationDecisionService

router = APIRouter(prefix="/clinical-assessment", tags=["Clinical Assessment & Medication Decision Support"])


def _write_audit_log(db: Any, assessment_id: str, action: str, user: MongoUser, details: Dict[str, Any]) -> None:
    try:
        db.clinical_audit_logs.insert_one({
            "audit_id": f"AUD-{uuid.uuid4().hex[:10].upper()}",
            "assessment_id": assessment_id,
            "action": action,
            "actor_user_id": getattr(user, "user_id", None),
            "actor_role": getattr(getattr(user, "role", None), "name", "Unknown"),
            "actor_email": getattr(user, "email", None),
            "details": details,
            "timestamp": datetime.now(timezone.utc),
        })
    except Exception as e:
        logger.warning(f"Audit log write warning: {e}")


@router.post(
    "/analyze",
    response_model=ClinicalAssessmentResponse,
    summary="Run Patient-Specific Clinical Assessment & Medication Safety Analysis",
)
def analyze_clinical_case(
    payload: ClinicalAssessmentRequest,
    db=Depends(get_mongo_db),
    current_user: MongoUser = Depends(require_roles(["Doctor", "Admin", "Staff"])),
):
    patient = db.patients.find_one({"patient_id": payload.patient_id})
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient #{payload.patient_id} not found",
        )

    assessment = ClinicalAssessmentService.analyze_patient(
        req=payload,
        patient_doc=patient,
        created_by_user_id=getattr(current_user, "user_id", None),
    )

    options, interactions, allergies, unsupported = MedicationDecisionService.evaluate_medications(
        assessment_doc=assessment,
        requested_medications=payload.requested_medications,
    )
    assessment["medication_options"] = options
    assessment["drug_interaction_alerts"] = interactions
    assessment["allergy_warnings"] = allergies
    assessment["unsupported_requests"] = unsupported

    db.clinical_assessments.insert_one(dict(assessment))
    _write_audit_log(
        db,
        assessment["assessment_id"],
        "CLINICAL_ASSESSMENT_ANALYZED",
        current_user,
        {
            "patient_id": payload.patient_id,
            "has_emergency_flags": assessment["has_emergency_flags"],
            "possible_conditions_count": len(assessment["possible_conditions"]),
            "medication_options_count": len(options),
        },
    )
    return ClinicalAssessmentResponse(**(clean_doc(assessment) or {}))


@router.get(
    "/{assessment_id}",
    response_model=ClinicalAssessmentResponse,
    summary="Retrieve Clinical Assessment Draft or Approved Record",
)
def get_clinical_assessment(
    assessment_id: str,
    db=Depends(get_mongo_db),
    current_user: MongoUser = Depends(require_roles(["Doctor", "Admin", "Staff"])),
):
    doc = db.clinical_assessments.find_one({"assessment_id": assessment_id})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Clinical assessment {assessment_id} not found")
    return ClinicalAssessmentResponse(**(clean_doc(doc) or {}))


@router.post(
    "/{assessment_id}/medications",
    response_model=ClinicalAssessmentResponse,
    summary="Evaluate Verified Medication Options, Allergies & Drug Interactions",
)
def evaluate_medications_for_assessment(
    assessment_id: str,
    payload: MedicationEvaluationRequest,
    db=Depends(get_mongo_db),
    current_user: MongoUser = Depends(require_roles(["Doctor", "Admin", "Staff"])),
):
    doc = db.clinical_assessments.find_one({"assessment_id": assessment_id})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Clinical assessment {assessment_id} not found")

    options, interactions, allergies, unsupported = MedicationDecisionService.evaluate_medications(
        assessment_doc=doc,
        requested_medications=payload.requested_medications,
        target_indication=payload.target_indication,
    )
    now = datetime.now(timezone.utc)
    db.clinical_assessments.update_one(
        {"assessment_id": assessment_id},
        {
            "$set": {
                "medication_options": options,
                "drug_interaction_alerts": interactions,
                "allergy_warnings": allergies,
                "unsupported_requests": unsupported,
                "updated_at": now,
            }
        },
    )
    _write_audit_log(
        db,
        assessment_id,
        "MEDICATIONS_EVALUATED",
        current_user,
        {
            "requested_medications": payload.requested_medications,
            "options_count": len(options),
            "interaction_alerts": len(interactions),
            "allergy_warnings": len(allergies),
            "unsupported_requests": unsupported,
        },
    )
    updated = db.clinical_assessments.find_one({"assessment_id": assessment_id})
    return ClinicalAssessmentResponse(**(clean_doc(updated) or {}))


@router.post(
    "/{assessment_id}/review",
    response_model=ClinicalAssessmentResponse,
    summary="Doctor Review: Edit, Reject, or Approve Individual AI Recommendations",
)
def review_clinical_assessment(
    assessment_id: str,
    payload: ClinicalReviewRequest,
    db=Depends(get_mongo_db),
    current_user: MongoUser = Depends(require_roles(["Doctor", "Admin"])),
):
    doc = db.clinical_assessments.find_one({"assessment_id": assessment_id})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Clinical assessment {assessment_id} not found")

    meds = list(doc.get("medication_options") or [])
    invs = list(doc.get("recommended_investigations") or [])

    for item in payload.items:
        action = item.action.lower()
        if action not in ("approve", "edit", "reject"):
            raise HTTPException(status_code=400, detail=f"Invalid review action '{item.action}'")

        if item.item_type == "medication":
            for m in meds:
                if m.get("option_id") == item.item_id:
                    m["review_status"] = "approved" if action == "approve" else "edited" if action == "edit" else "rejected"
                    if item.doctor_notes is not None:
                        m["doctor_notes"] = item.doctor_notes
                    if item.edited_data:
                        if "dosage" in item.edited_data:
                            m["doctor_edited_dosage"] = item.edited_data["dosage"]
                        if "frequency" in item.edited_data:
                            m["doctor_edited_frequency"] = item.edited_data["frequency"]
                        if "duration" in item.edited_data:
                            m["doctor_edited_duration"] = item.edited_data["duration"]
        elif item.item_type == "investigation":
            for inv in invs:
                if inv.get("investigation_id") == item.item_id:
                    inv["review_status"] = "approved" if action == "approve" else "edited" if action == "edit" else "rejected"

    update_fields: Dict[str, Any] = {
        "medication_options": meds,
        "recommended_investigations": invs,
        "status": "IN_REVIEW",
        "reviewed_by_user_id": getattr(current_user, "user_id", None),
        "updated_at": datetime.now(timezone.utc),
    }
    if payload.final_diagnosis_override is not None:
        update_fields["doctor_diagnosis_override"] = payload.final_diagnosis_override
    if payload.doctor_notes is not None:
        update_fields["doctor_review_notes"] = payload.doctor_notes

    db.clinical_assessments.update_one({"assessment_id": assessment_id}, {"$set": update_fields})
    _write_audit_log(
        db,
        assessment_id,
        "DOCTOR_REVIEW_UPDATED",
        current_user,
        {"items_reviewed": [i.model_dump() for i in payload.items]},
    )
    updated = db.clinical_assessments.find_one({"assessment_id": assessment_id})
    return ClinicalAssessmentResponse(**(clean_doc(updated) or {}))


@router.post(
    "/{assessment_id}/approve",
    summary="Doctor Final Approval & Sign-Off (Persists Approved Consultation & Bilingual PDF)",
)
def approve_clinical_assessment(
    assessment_id: str,
    payload: ClinicalApproveRequest,
    db=Depends(get_mongo_db),
    current_user: MongoUser = Depends(require_roles(["Doctor", "Admin"])),
):
    doc = db.clinical_assessments.find_one({"assessment_id": assessment_id})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Clinical assessment {assessment_id} not found")

    if not payload.doctor_signature_confirmed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Doctor signature confirmation is mandatory before final approval.",
        )

    now = datetime.now(timezone.utc)
    consultation_result = None

    if payload.generate_consultation_report:
        approved_meds = payload.approved_medications
        if approved_meds is None:
            approved_meds = [
                {
                    "drug_name": m.get("kannada_name") or m.get("generic_name"),
                    "dosage": m.get("doctor_edited_dosage") or m.get("suggested_dosage_reference") or "",
                    "frequency": m.get("doctor_edited_frequency") or m.get("suggested_frequency_reference") or "",
                    "duration": m.get("doctor_edited_duration") or m.get("suggested_duration_reference") or "",
                }
                for m in (doc.get("medication_options") or [])
                if m.get("review_status") in ("approved", "edited")
            ]

        approved_diag = payload.approved_diagnosis
        if approved_diag is None:
            approved_diag = [
                {
                    "entity": c.get("kannada_name") or c.get("condition_name"),
                    "english": c.get("condition_name"),
                    "confidence": c.get("confidence_score"),
                }
                for c in (doc.get("possible_conditions") or [])[:1]
            ]

        formatted_symptoms = [
            {
                "entity": s.get("kannada_name") or s.get("name"),
                "english": s.get("name"),
                "duration": s.get("duration") or "",
            }
            for s in (doc.get("extracted_symptoms") or [])
        ]

        c_req = ConsultationCreateRequest(
            patient_id=doc["patient_id"],
            transcript_text=payload.transcript_text or doc.get("kannada_summary") or "",
            language=payload.language,
            original_english_speech=doc.get("clinical_assessment_summary"),
            symptoms=formatted_symptoms,
            diagnosis=approved_diag,
            medications=approved_meds,
            advice=payload.approved_advice or [],
            doctor_signature_confirmed=True,
        )
        consultation_result = ConsultationService.create_and_approve_consultation(
            db=db,
            payload=c_req,
            current_user=current_user,
        )

    db.clinical_assessments.update_one(
        {"assessment_id": assessment_id},
        {
            "$set": {
                "status": "APPROVED",
                "approved_by_user_id": getattr(current_user, "user_id", None),
                "approved_at": now,
                "updated_at": now,
                "consultation_id": consultation_result.get("consultation_id") if consultation_result else None,
            }
        },
    )
    _write_audit_log(
        db,
        assessment_id,
        "CLINICAL_ASSESSMENT_APPROVED",
        current_user,
        {
            "consultation_id": consultation_result.get("consultation_id") if consultation_result else None,
            "report_id": consultation_result.get("report_id") if consultation_result else None,
        },
    )

    updated = db.clinical_assessments.find_one({"assessment_id": assessment_id})
    return {
        "success": True,
        "assessment": ClinicalAssessmentResponse(**(clean_doc(updated) or {})),
        "consultation": consultation_result,
    }
