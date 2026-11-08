from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.db.session import Base

class Doctor(Base):
    __tablename__ = "doctors"

    doctor_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), unique=True, nullable=False)
    specialization = Column(String(100), nullable=False, default="General Medicine")
    registration_no = Column(String(50), unique=True, nullable=False, index=True) # e.g. KMC-12345
    department = Column(String(100), nullable=True, default="Outpatient Department (OPD)")
    contact_phone = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    user = relationship("User", back_populates="doctor_profile")

    def __repr__(self):
        return f"<Doctor(doctor_id={self.doctor_id}, user_id={self.user_id}, registration_no='{self.registration_no}')>"
