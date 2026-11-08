from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

class ClinicalEntity(BaseModel):
    entity: str
    english: Optional[str] = None
    duration: Optional[str] = None
    confidence: Optional[float] = None

class MedicationItem(BaseModel):
    drug_name: str
    dosage: str
    frequency: str
    duration: str

class AdviceItem(BaseModel):
    instruction: str

class ConsultationCreateRequest(BaseModel):
    patient_id: int
    transcript_text: str
    language: str = "kn"
    original_english_speech: Optional[str] = None
    symptoms: List[Dict[str, Any]] = Field(default_factory=list)
    diagnosis: List[Dict[str, Any]] = Field(default_factory=list)
    medications: List[Dict[str, Any]] = Field(default_factory=list)
    advice: List[Dict[str, Any]] = Field(default_factory=list)
    doctor_signature_confirmed: bool = True
    audio_filename: Optional[str] = None

class EnglishConsultationTextRequest(BaseModel):
    patient_id: int
    english_text: str

class ConsultationResponse(BaseModel):
    consultation_id: int
    patient_id: int
    doctor_id: Optional[int] = None
    report_id: str
    input_language: str
    original_english_speech: Optional[str] = None
    kannada_transcript: str
    symptoms: List[Dict[str, Any]]
    diagnosis: List[Dict[str, Any]]
    medications: List[Dict[str, Any]]
    advice: List[Dict[str, Any]]
    status: str
    signed_by_name: Optional[str] = None
    signed_doctor_reg: Optional[str] = None
    audio_filename: Optional[str] = None
    created_at: datetime
    signed_at: datetime

    class Config:
        from_attributes = True

class ConsultationListResponse(BaseModel):
    items: List[ConsultationResponse]
    total: int
