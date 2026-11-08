import random
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from fastapi import HTTPException, status
from app.db.mongo import clean_doc, clean_docs, get_next_sequence
from app.schemas.consultation import ConsultationCreateRequest

class ConsultationService:
    @staticmethod
    def _format_consultation(doc: Dict[str, Any]) -> Dict[str, Any]:
        doc = clean_doc(doc)
        if not doc:
            return {}
        if "created_at" not in doc or not doc["created_at"]:
            doc["created_at"] = datetime.now(timezone.utc)
        if "signed_at" not in doc or not doc["signed_at"]:
            doc["signed_at"] = doc["created_at"]
        return doc

    @staticmethod
    def create_and_approve_consultation(
        db: Any,
        payload: ConsultationCreateRequest,
        current_user: Any
    ) -> Dict[str, Any]:
        patient = db.patients.find_one({"patient_id": payload.patient_id})
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patient #{payload.patient_id} not found"
            )

        doctor_profile = getattr(current_user, "doctor_profile", None)
        if hasattr(doctor_profile, "registration_no"):
            reg_no = doctor_profile.registration_no
        elif isinstance(doctor_profile, dict):
            reg_no = doctor_profile.get("registration_no", "KMC-84920")
        else:
            reg_no = "KMC-84920"

        doctor_name = getattr(current_user, "full_name", None) or "Dr. Anand Deshmukh, MD"
        doctor_id = getattr(current_user, "user_id", None) or 1

        # Generate standard clinical report ID
        current_year = datetime.now(timezone.utc).year
        rand_num = random.randint(1000, 9999)
        report_id = f"REP-KN-{payload.patient_id}-{current_year}-{rand_num}"
        consultation_id = get_next_sequence("consultation_id", db)
        now = datetime.now(timezone.utc)

        doc = {
            "consultation_id": consultation_id,
            "patient_id": payload.patient_id,
            "doctor_id": doctor_id,
            "report_id": report_id,
            "input_language": payload.language,
            "original_english_speech": payload.original_english_speech,
            "kannada_transcript": payload.transcript_text,
            "symptoms": payload.symptoms,
            "diagnosis": payload.diagnosis,
            "medications": payload.medications,
            "advice": payload.advice,
            "status": "APPROVED",
            "signed_by_name": doctor_name,
            "signed_doctor_reg": reg_no,
            "audio_filename": payload.audio_filename,
            "created_at": now,
            "signed_at": now
        }

        db.consultations.insert_one(doc)

        # Generate PDF Report and save metadata in Mongo
        try:
            from app.services.pdf_service import PdfReportService
            PdfReportService.generate_and_save_pdf_report(
                db=db,
                consultation=doc,
                patient=patient,
                doctor_name=doctor_name,
                doctor_reg=reg_no
            )
        except Exception as e:
            print(f"PDF generation error (handled): {e}")

        return ConsultationService._format_consultation(doc)

    @staticmethod
    def get_consultation_by_id(db: Any, consultation_id: int) -> Dict[str, Any]:
        doc = db.consultations.find_one({"consultation_id": consultation_id})
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Consultation report #{consultation_id} not found"
            )
        return ConsultationService._format_consultation(doc)

    @staticmethod
    def get_consultations_for_patient(db: Any, patient_id: int) -> List[Dict[str, Any]]:
        patient = db.patients.find_one({"patient_id": patient_id})
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patient #{patient_id} not found"
            )
        cursor = db.consultations.find({"patient_id": patient_id}).sort("created_at", -1)
        return [ConsultationService._format_consultation(c) for c in cursor]

    @staticmethod
    def delete_consultation(db: Any, consultation_id: int) -> bool:
        ConsultationService.get_consultation_by_id(db, consultation_id)
        db.consultations.delete_one({"consultation_id": consultation_id})
        db.medical_reports.delete_one({"consultation_id": consultation_id})
        return True
