from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, ConfigDict

class PatientBase(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=150, json_schema_extra={"example": "Ramesh Kumar"})
    dob: Optional[date] = Field(None, json_schema_extra={"example": "1985-04-12"})
    gender: str = Field(..., json_schema_extra={"example": "Male"}) # Male, Female, Other
    phone: str = Field(..., min_length=8, max_length=20, json_schema_extra={"example": "+919876543210"})
    email: Optional[EmailStr] = Field(None, json_schema_extra={"example": "ramesh.k@example.com"})
    address: Optional[str] = Field(None, json_schema_extra={"example": "12th Cross, Malleshwaram, Bengaluru, Karnataka"})
    emergency_contact: Optional[str] = Field(None, json_schema_extra={"example": "+919876543211 (Brother)"})
    blood_group: Optional[str] = Field(None, json_schema_extra={"example": "B+"})
    preferred_language: Optional[str] = Field("Kannada", json_schema_extra={"example": "Kannada"})
    allergies: List[str] = Field(default_factory=list)
    existing_conditions: List[str] = Field(default_factory=list)
    medical_history: List[str] = Field(default_factory=list)
    current_medications: List[str] = Field(default_factory=list)
    weight_kg: Optional[float] = Field(None, gt=0, le=500)
    pregnancy_status: Optional[str] = Field("unknown")

class PatientCreate(PatientBase):
    pass

class PatientUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=150)
    dob: Optional[date] = None
    gender: Optional[str] = None
    phone: Optional[str] = Field(None, min_length=8, max_length=20)
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    emergency_contact: Optional[str] = None
    blood_group: Optional[str] = None
    preferred_language: Optional[str] = None
    allergies: Optional[List[str]] = None
    existing_conditions: Optional[List[str]] = None
    medical_history: Optional[List[str]] = None
    current_medications: Optional[List[str]] = None
    weight_kg: Optional[float] = Field(None, gt=0, le=500)
    pregnancy_status: Optional[str] = None

class PatientResponse(PatientBase):
    patient_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class PatientListResponse(BaseModel):
    items: List[PatientResponse]
    total: int
    page: int
    size: int
