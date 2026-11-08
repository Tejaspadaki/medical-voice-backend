from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.db.session import Base

class VoiceChatSession(Base):
    __tablename__ = "voice_chat_sessions"

    session_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    doctor_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id", ondelete="SET NULL"), nullable=True)
    language = Column(String(20), default="kn", nullable=False) # 'kn', 'en', 'code-mixed'
    status = Column(String(20), default="active", nullable=False) # 'active', 'completed', 'closed'
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    patient = relationship("Patient")
    doctor = relationship("User")
    turns = relationship("VoiceChatTurn", back_populates="session", cascade="all, delete-orphan", order_by="VoiceChatTurn.created_at")
    pending_actions = relationship("PendingClinicalAction", back_populates="session", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<VoiceChatSession(session_id='{self.session_id}', patient_id={self.patient_id}, status='{self.status}')>"


class VoiceChatTurn(Base):
    __tablename__ = "voice_chat_turns"

    turn_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("voice_chat_sessions.session_id", ondelete="CASCADE"), nullable=False, index=True)
    speaker = Column(String(20), nullable=False) # 'doctor', 'assistant', 'system'
    transcript = Column(Text, nullable=False)
    audio_url = Column(String(500), nullable=True)
    intent_detected = Column(String(50), nullable=True)
    tool_calls = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    session = relationship("VoiceChatSession", back_populates="turns")

    def __repr__(self):
        return f"<VoiceChatTurn(turn_id='{self.turn_id}', speaker='{self.speaker}', intent='{self.intent_detected}')>"


class PendingClinicalAction(Base):
    __tablename__ = "pending_clinical_actions"

    action_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("voice_chat_sessions.session_id", ondelete="CASCADE"), nullable=False, index=True)
    action_type = Column(String(50), nullable=False) # 'CREATE_PRESCRIPTION', 'RECORD_VITALS', 'ADD_DIAGNOSIS', 'FINALIZE_CONSULTATION'
    patient_id = Column(Integer, nullable=True)
    payload = Column(JSON, nullable=False, default=dict) # symptoms, diagnosis, medications, advice, vitals
    tts_prompt_kannada = Column(Text, nullable=False)
    tts_prompt_english = Column(Text, nullable=True)
    status = Column(String(20), default="pending", nullable=False) # 'pending', 'confirmed', 'rejected', 'expired'
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime, nullable=False)

    # Relationships
    session = relationship("VoiceChatSession", back_populates="pending_actions")

    def __repr__(self):
        return f"<PendingClinicalAction(action_id='{self.action_id}', type='{self.action_type}', status='{self.status}')>"

