from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime, timezone, date
from fastapi import HTTPException, status
from app.db.mongo import clean_doc, clean_docs, get_next_sequence
from app.schemas.patient import PatientCreate, PatientUpdate

class PatientService:
    @staticmethod
    def _format_patient(doc: Dict[str, Any]) -> Dict[str, Any]:
        doc = clean_doc(doc)
        if not doc:
            return {}
        if "created_at" not in doc or not doc["created_at"]:
            doc["created_at"] = datetime.now(timezone.utc)
        if "updated_at" not in doc or not doc["updated_at"]:
            doc["updated_at"] = doc["created_at"]
        return doc

    @staticmethod
    def create_patient(db: Any, patient_in: PatientCreate) -> Dict[str, Any]:
        patient_id = get_next_sequence("patient_id", db)
        now = datetime.now(timezone.utc)
        doc = {
            "patient_id": patient_id,
            "full_name": patient_in.full_name,
            "dob": patient_in.dob.isoformat() if isinstance(patient_in.dob, date) else patient_in.dob,
            "gender": patient_in.gender,
            "phone": patient_in.phone,
            "email": patient_in.email,
            "address": patient_in.address,
            "emergency_contact": patient_in.emergency_contact,
            "blood_group": patient_in.blood_group,
            "preferred_language": patient_in.preferred_language or "Kannada",
            "created_at": now,
            "updated_at": now
        }
        db.patients.insert_one(doc)
        return PatientService._format_patient(doc)

    @staticmethod
    def get_patient_by_id(db: Any, patient_id: int) -> Dict[str, Any]:
        doc = db.patients.find_one({"patient_id": patient_id})
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patient with ID {patient_id} not found"
            )
        return PatientService._format_patient(doc)

    @staticmethod
    def list_patients(
        db: Any,
        search: Optional[str] = None,
        gender: Optional[str] = None,
        language: Optional[str] = None,
        page: int = 1,
        size: int = 20
    ) -> Tuple[List[Dict[str, Any]], int]:
        mongo_filter: Dict[str, Any] = {}

        if search:
            mongo_filter["$or"] = [
                {"full_name": {"$regex": search, "$options": "i"}},
                {"phone": {"$regex": search, "$options": "i"}},
                {"email": {"$regex": search, "$options": "i"}}
            ]

        if gender:
            mongo_filter["gender"] = {"$regex": f"^{gender}$", "$options": "i"}

        if language:
            mongo_filter["preferred_language"] = {"$regex": f"^{language}$", "$options": "i"}

        total = db.patients.count_documents(mongo_filter)
        offset = (page - 1) * size
        cursor = db.patients.find(mongo_filter).sort("created_at", -1).skip(offset).limit(size)
        patients = [PatientService._format_patient(p) for p in cursor]
        return patients, total

    @staticmethod
    def update_patient(db: Any, patient_id: int, update_in: PatientUpdate) -> Dict[str, Any]:
        PatientService.get_patient_by_id(db, patient_id)
        update_data = update_in.model_dump(exclude_unset=True)
        if "dob" in update_data and isinstance(update_data["dob"], date):
            update_data["dob"] = update_data["dob"].isoformat()
        update_data["updated_at"] = datetime.now(timezone.utc)
        
        db.patients.update_one({"patient_id": patient_id}, {"$set": update_data})
        updated = db.patients.find_one({"patient_id": patient_id})
        return PatientService._format_patient(updated)

    @staticmethod
    def delete_patient(db: Any, patient_id: int) -> bool:
        PatientService.get_patient_by_id(db, patient_id)
        db.patients.delete_one({"patient_id": patient_id})
        db.consultations.delete_many({"patient_id": patient_id})
        return True
