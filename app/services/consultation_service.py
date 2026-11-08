import random
from typing import List, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.consultation import Consultation
from app.models.patient import Patient
from app.models.user import User
from app.models.medical_report import MedicalReport
from app.schemas.consultation import ConsultationCreateRequest
from app.services.pdf_service import PdfReportService

class ConsultationService:
    @staticmethod
    def create_and_approve_consultation(
        db: Session,
        payload: ConsultationCreateRequest,
        current_user: User
    ) -> Consultation:
        patient = db.query(Patient).filter(Patient.patient_id == payload.patient_id).first()
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patient #{payload.patient_id} not found"
            )

        doctor_profile = current_user.doctor_profile
        doctor_name = current_user.full_name or "ಡಾ. ಆನಂದ್ ದೇಶಮುಖ್ (Dr. Anand Deshmukh)"
        reg_no = doctor_profile.registration_no if doctor_profile else "KMC-84920"

        # Generate standard clinical report ID
        current_year = datetime.now(timezone.utc).year
        rand_num = random.randint(1000, 9999)
        report_id = f"REP-KN-{payload.patient_id}-{current_year}-{rand_num}"

        consultation = Consultation(
            patient_id=payload.patient_id,
            doctor_id=current_user.user_id,
            report_id=report_id,
            input_language=payload.language,
            original_english_speech=payload.original_english_speech,
            kannada_transcript=payload.transcript_text,
            symptoms=payload.symptoms,
            diagnosis=payload.diagnosis,
            medications=payload.medications,
            advice=payload.advice,
            status="APPROVED",
            signed_by_name=doctor_name,
            signed_doctor_reg=reg_no,
            audio_filename=payload.audio_filename,
            created_at=datetime.now(timezone.utc),
            signed_at=datetime.now(timezone.utc)
        )

        db.add(consultation)
        db.commit()
        db.refresh(consultation)

        # Generate PDF File and Save to SQL Database (medical_reports table)
        try:
            PdfReportService.generate_and_save_pdf_report(
                db=db,
                consultation=consultation,
                patient=patient,
                doctor_name=doctor_name,
                doctor_reg=reg_no
            )
            db.refresh(consultation)
        except Exception as e:
            # Fallback if PDF build encounters environment issues
            print(f"PDF generation error (handled): {e}")

        return consultation

    @staticmethod
    def get_consultation_by_id(db: Session, consultation_id: int) -> Consultation:
        consultation = db.query(Consultation).filter(Consultation.consultation_id == consultation_id).first()
        if not consultation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Consultation report #{consultation_id} not found"
            )
        return consultation

    @staticmethod
    def get_consultations_for_patient(db: Session, patient_id: int) -> List[Consultation]:
        patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patient #{patient_id} not found"
            )
        return db.query(Consultation).filter(Consultation.patient_id == patient_id).order_by(Consultation.created_at.desc()).all()

    @staticmethod
    def delete_consultation(db: Session, consultation_id: int) -> bool:
        consultation = ConsultationService.get_consultation_by_id(db, consultation_id)
        db.delete(consultation)
        db.commit()
        return True
