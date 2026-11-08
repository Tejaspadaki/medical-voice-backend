from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import or_
from fastapi import HTTPException, status

from app.models.patient import Patient
from app.schemas.patient import PatientCreate, PatientUpdate

class PatientService:
    @staticmethod
    def create_patient(db: Session, patient_in: PatientCreate) -> Patient:
        db_patient = Patient(
            full_name=patient_in.full_name,
            dob=patient_in.dob,
            gender=patient_in.gender,
            phone=patient_in.phone,
            email=patient_in.email,
            address=patient_in.address,
            emergency_contact=patient_in.emergency_contact,
            blood_group=patient_in.blood_group,
            preferred_language=patient_in.preferred_language or "Kannada"
        )
        db.add(db_patient)
        db.commit()
        db.refresh(db_patient)
        return db_patient

    @staticmethod
    def get_patient_by_id(db: Session, patient_id: int) -> Patient:
        patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patient with ID {patient_id} not found"
            )
        return patient

    @staticmethod
    def list_patients(
        db: Session,
        search: Optional[str] = None,
        gender: Optional[str] = None,
        language: Optional[str] = None,
        page: int = 1,
        size: int = 20
    ) -> Tuple[List[Patient], int]:
        query = db.query(Patient)

        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                or_(
                    Patient.full_name.ilike(search_pattern),
                    Patient.phone.ilike(search_pattern),
                    Patient.email.ilike(search_pattern)
                )
            )

        if gender:
            query = query.filter(Patient.gender.ilike(gender))

        if language:
            query = query.filter(Patient.preferred_language.ilike(language))

        total = query.count()
        offset = (page - 1) * size
        patients = query.order_by(Patient.created_at.desc()).offset(offset).limit(size).all()
        return patients, total

    @staticmethod
    def update_patient(db: Session, patient_id: int, update_in: PatientUpdate) -> Patient:
        patient = PatientService.get_patient_by_id(db, patient_id)
        update_data = update_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(patient, field, value)
        db.commit()
        db.refresh(patient)
        return patient

    @staticmethod
    def delete_patient(db: Session, patient_id: int) -> bool:
        patient = PatientService.get_patient_by_id(db, patient_id)
        db.delete(patient)
        db.commit()
        return True

