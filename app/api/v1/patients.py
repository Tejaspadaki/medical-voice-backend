from typing import Optional
from fastapi import APIRouter, Depends, Query, Path, status

from app.db.mongo import get_mongo_db
from app.core.dependencies import get_current_user, require_roles, MongoUser
from app.schemas.patient import (
    PatientCreate,
    PatientUpdate,
    PatientResponse,
    PatientListResponse
)
from app.services.patient_service import PatientService

router = APIRouter(prefix="/patients", tags=["Patients"])

@router.post(
    "",
    response_model=PatientResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create New Patient Record",
    description="Register a new patient into the hospital documentation system. Requires Doctor, Admin, or Staff role."
)
def create_patient(
    patient_in: PatientCreate,
    db = Depends(get_mongo_db),
    current_user: MongoUser = Depends(require_roles(["Doctor", "Admin", "Staff"]))
):
    return PatientService.create_patient(db, patient_in)

@router.get(
    "",
    response_model=PatientListResponse,
    summary="List & Search Patients",
    description="Retrieve paginated list of patients with optional query search on name, phone, or email."
)
def list_patients(
    search: Optional[str] = Query(None, description="Search term for name, phone, or email"),
    gender: Optional[str] = Query(None, description="Filter by gender (Male, Female, Other)"),
    language: Optional[str] = Query(None, description="Filter by preferred language"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    db = Depends(get_mongo_db),
    current_user: MongoUser = Depends(get_current_user)
):
    items, total = PatientService.list_patients(
        db=db,
        search=search,
        gender=gender,
        language=language,
        page=page,
        size=size
    )
    return PatientListResponse(
        items=[PatientResponse.model_validate(p) for p in items],
        total=total,
        page=page,
        size=size
    )

@router.get(
    "/{patient_id}",
    response_model=PatientResponse,
    summary="Get Patient by ID",
    description="Fetch single patient demographics and contact details."
)
def get_patient(
    patient_id: int = Path(..., ge=1, description="Primary key ID of patient"),
    db = Depends(get_mongo_db),
    current_user: MongoUser = Depends(get_current_user)
):
    patient = PatientService.get_patient_by_id(db, patient_id)
    return PatientResponse.model_validate(patient)

@router.put(
    "/{patient_id}",
    response_model=PatientResponse,
    summary="Update Patient Details",
    description="Update existing patient information. Requires Doctor or Admin role."
)
def update_patient(
    patient_id: int = Path(..., ge=1),
    update_in: PatientUpdate = ...,
    db = Depends(get_mongo_db),
    current_user: MongoUser = Depends(require_roles(["Doctor", "Admin", "Staff"]))
):
    patient = PatientService.update_patient(db, patient_id, update_in)
    return PatientResponse.model_validate(patient)

@router.delete(
    "/{patient_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Patient Record",
    description="Remove patient and associated consultations. Requires Admin role."
)
def delete_patient(
    patient_id: int = Path(..., ge=1),
    db = Depends(get_mongo_db),
    current_user: MongoUser = Depends(require_roles(["Admin", "Doctor"]))
):
    PatientService.delete_patient(db, patient_id)
    return None
