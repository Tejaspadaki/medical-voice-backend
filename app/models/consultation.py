from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.db.session import Base

class Consultation(Base):
    __tablename__ = "consultations"

    consultation_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False, index=True)
    doctor_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    report_id = Column(String(100), unique=True, index=True, nullable=False)
    input_language = Column(String(30), default="kn")
    original_english_speech = Column(Text, nullable=True)
    kannada_transcript = Column(Text, nullable=False)
    symptoms = Column(JSON, nullable=False, default=list)
    diagnosis = Column(JSON, nullable=False, default=list)
    medications = Column(JSON, nullable=False, default=list)
    advice = Column(JSON, nullable=False, default=list)
    status = Column(String(30), default="APPROVED", nullable=False) # DRAFT, APPROVED, SIGNED
    signed_by_name = Column(String(150), nullable=True)
    signed_doctor_reg = Column(String(50), nullable=True)
    audio_filename = Column(String(255), nullable=True)
    pdf_filename = Column(String(255), nullable=True)
    pdf_file_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    signed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    patient = relationship("Patient", back_populates="consultations")
    doctor = relationship("User")
    medical_report = relationship("MedicalReport", back_populates="consultation", uselist=False, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Consultation(id={self.consultation_id}, report_id='{self.report_id}', patient_id={self.patient_id}, status='{self.status}')>"
