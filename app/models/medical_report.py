from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, BigInteger
from sqlalchemy.orm import relationship
from app.db.session import Base

class MedicalReport(Base):
    __tablename__ = "medical_reports"

    report_record_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    consultation_id = Column(Integer, ForeignKey("consultations.consultation_id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False, index=True)
    doctor_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    report_code = Column(String(100), unique=True, index=True, nullable=False)
    
    # PDF File Storage Details in SQL Database
    pdf_filename = Column(String(255), nullable=False)
    pdf_file_path = Column(String(500), nullable=False)
    pdf_base64_data = Column(Text, nullable=True) # Full base64 string of the PDF
    file_size_bytes = Column(Integer, nullable=True)
    mime_type = Column(String(50), default="application/pdf", nullable=False)
    
    # Sign-off metadata
    signed_doctor_name = Column(String(150), nullable=False)
    signed_doctor_reg = Column(String(50), nullable=False)
    status = Column(String(30), default="CONFIRMED_SIGNED", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    consultation = relationship("Consultation", back_populates="medical_report")
    patient = relationship("Patient")
    doctor = relationship("User")

    def __repr__(self):
        return f"<MedicalReport(id={self.report_record_id}, code='{self.report_code}', pdf='{self.pdf_filename}')>"
