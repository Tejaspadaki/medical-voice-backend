from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

class VoiceSessionCreateRequest(BaseModel):
    patient_id: Optional[int] = None
    language: str = Field(default="kn", description="Preferred language ('kn', 'en', or 'code-mixed')")

class VoiceSessionResponse(BaseModel):
    session_id: str
    doctor_id: Optional[int] = None
    patient_id: Optional[int] = None
    patient_name: Optional[str] = None
    language: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

class PendingActionDTO(BaseModel):
    action_id: str
    session_id: str
    action_type: str
    patient_id: Optional[int] = None
    payload: Dict[str, Any]
    tts_prompt_kannada: str
    tts_prompt_english: Optional[str] = None
    status: str
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True

class VoiceTurnRequest(BaseModel):
    session_id: str
    text_input: Optional[str] = None
    language: Optional[str] = "kn"

class VoiceTurnResponse(BaseModel):
    session_id: str
    turn_id: str
    user_transcript: str
    assistant_reply_text: str
    assistant_tts_prompt: str
    assistant_audio_b64: Optional[str] = None
    language: str
    intent_detected: str
    pending_action: Optional[PendingActionDTO] = None
    patient: Optional[Dict[str, Any]] = None
    requires_confirmation: bool = False

class VoiceConfirmRequest(BaseModel):
    session_id: str
    action_id: str
    confirmed: bool = True
    doctor_notes: Optional[str] = None

class VoiceConfirmResponse(BaseModel):
    success: bool
    action_id: str
    status: str
    message: str
    consultation_id: Optional[int] = None
    report_id: Optional[str] = None
    tts_confirmation: Optional[str] = None
    assistant_audio_b64: Optional[str] = None

class VoiceTTSRequest(BaseModel):
    text: str
    language: Optional[str] = "kn"

class VoiceTTSResponse(BaseModel):
    text: str
    audio_b64: Optional[str] = None
    provider: str = "sarvam"


