from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class SymptomInput(BaseModel):
    name: str
    kannada_name: Optional[str] = None
    duration: Optional[str] = None
    severity: Optional[str] = Field(None, description="mild, moderate, or severe")


class VitalsInput(BaseModel):
    bp: Optional[str] = None
    systolic: Optional[int] = None
    diastolic: Optional[int] = None
    pulse: Optional[int] = None
    temperature: Optional[str] = None
    spo2: Optional[int] = None
    respiratory_rate: Optional[int] = None


class LabResultInput(BaseModel):
    test_name: str
    value: str
    unit: Optional[str] = None
    interpretation: Optional[str] = None


class ClinicalAssessmentRequest(BaseModel):
    patient_id: int = Field(..., ge=1)
    symptoms: List[Union[SymptomInput, Dict[str, Any], str]] = Field(default_factory=list)
    symptom_duration: Optional[str] = None
    severity: Optional[str] = None
    age: Optional[int] = Field(None, ge=0, le=130)
    gender: Optional[str] = None
    weight_kg: Optional[float] = Field(None, gt=0, le=500)
    pregnancy_status: Optional[str] = Field("unknown", description="not_pregnant, pregnant, lactating, unknown")
    medical_history: List[str] = Field(default_factory=list)
    existing_conditions: List[str] = Field(default_factory=list)
    allergies: List[str] = Field(default_factory=list)
    current_medications: List[str] = Field(default_factory=list)
    vitals: Optional[VitalsInput] = None
    lab_results: List[LabResultInput] = Field(default_factory=list)
    clinical_notes: Optional[str] = None
    requested_medications: List[str] = Field(default_factory=list)
    language: str = "en"


class PossibleCondition(BaseModel):
    condition_id: str
    condition_name: str
    kannada_name: str
    icd10_code: Optional[str] = None
    likelihood: str = "moderate"
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    supporting_symptoms: List[str] = Field(default_factory=list)
    rationale: str
    is_preliminary: bool = True


class EmergencyWarningSign(BaseModel):
    sign: str
    kannada_sign: str
    severity: str = "critical"
    action_required: str
    matched_triggers: List[str] = Field(default_factory=list)


class RecommendedInvestigation(BaseModel):
    investigation_id: str
    test_name: str
    kannada_name: str
    rationale: str
    priority: str = "routine"
    review_status: str = "pending_review"


class MedicationOption(BaseModel):
    option_id: str
    generic_name: str
    kannada_name: str
    drug_class: str
    indication: str
    suggested_dosage_reference: Optional[str] = None
    suggested_frequency_reference: Optional[str] = None
    suggested_duration_reference: Optional[str] = None
    contraindications: List[str] = Field(default_factory=list)
    side_effects: List[str] = Field(default_factory=list)
    interaction_warnings: List[Dict[str, Any]] = Field(default_factory=list)
    allergy_alerts: List[Dict[str, Any]] = Field(default_factory=list)
    precautions: List[str] = Field(default_factory=list)
    local_availability: Dict[str, Any] = Field(default_factory=dict)
    evidence_references: List[str] = Field(default_factory=list)
    safety_status: str = "safe_to_consider"
    review_status: str = "pending_review"
    doctor_edited_dosage: Optional[str] = None
    doctor_edited_frequency: Optional[str] = None
    doctor_edited_duration: Optional[str] = None
    doctor_notes: Optional[str] = None


class ClinicalAssessmentResponse(BaseModel):
    assessment_id: str
    patient_id: int
    patient_snapshot: Dict[str, Any] = Field(default_factory=dict)
    extracted_symptoms: List[Dict[str, Any]] = Field(default_factory=list)
    clinical_assessment_summary: str
    kannada_summary: str
    disclaimer: str = (
        "AI-generated clinical decision support only. Not a confirmed diagnosis. "
        "Mandatory qualified doctor review and approval required before prescribing."
    )
    possible_conditions: List[PossibleCondition] = Field(default_factory=list)
    differential_diagnosis: List[PossibleCondition] = Field(default_factory=list)
    supporting_clinical_findings: List[str] = Field(default_factory=list)
    missing_clinical_information: List[str] = Field(default_factory=list)
    recommended_investigations: List[RecommendedInvestigation] = Field(default_factory=list)
    emergency_warning_signs: List[EmergencyWarningSign] = Field(default_factory=list)
    has_emergency_flags: bool = False
    uncertainty_and_confidence: Dict[str, Any] = Field(default_factory=dict)
    medication_options: List[MedicationOption] = Field(default_factory=list)
    drug_interaction_alerts: List[Dict[str, Any]] = Field(default_factory=list)
    allergy_warnings: List[Dict[str, Any]] = Field(default_factory=list)
    unsupported_requests: List[str] = Field(default_factory=list)
    status: str = "PENDING_DOCTOR_REVIEW"
    created_by_user_id: Optional[int] = None
    reviewed_by_user_id: Optional[int] = None
    approved_by_user_id: Optional[int] = None
    consultation_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    approved_at: Optional[datetime] = None


class MedicationEvaluationRequest(BaseModel):
    requested_medications: List[str] = Field(default_factory=list)
    target_indication: Optional[str] = None


class RecommendationReviewItem(BaseModel):
    item_type: str = Field(..., description="condition, medication, or investigation")
    item_id: str
    action: str = Field(..., description="approve, edit, or reject")
    edited_data: Optional[Dict[str, Any]] = None
    doctor_notes: Optional[str] = None


class ClinicalReviewRequest(BaseModel):
    items: List[RecommendationReviewItem] = Field(default_factory=list)
    doctor_notes: Optional[str] = None
    final_diagnosis_override: Optional[List[Dict[str, Any]]] = None


class ClinicalApproveRequest(BaseModel):
    doctor_signature_confirmed: bool = True
    approved_diagnosis: Optional[List[Dict[str, Any]]] = None
    approved_medications: Optional[List[Dict[str, Any]]] = None
    approved_advice: Optional[List[Dict[str, Any]]] = None
    transcript_text: Optional[str] = None
    language: str = "kn"
    generate_consultation_report: bool = True
