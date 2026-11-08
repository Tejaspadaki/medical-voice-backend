from datetime import datetime, timezone, date
from sqlalchemy import Column, Integer, String, Date, DateTime, Text
from sqlalchemy.orm import relationship
from app.db.session import Base

class Patient(Base):
    __tablename__ = "patients"

    patient_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    full_name = Column(String(150), nullable=False, index=True)
    dob = Column(Date, nullable=True) # Date of Birth
    gender = Column(String(20), nullable=False) # Male, Female, Other
    phone = Column(String(20), nullable=False, index=True)
    email = Column(String(255), nullable=True)
    address = Column(Text, nullable=True)
    emergency_contact = Column(String(100), nullable=True)
    blood_group = Column(String(10), nullable=True) # A+, O+, etc.
    preferred_language = Column(String(30), default="Kannada") # Primary spoken language for consultations
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    consultations = relationship("Consultation", back_populates="patient", cascade="all, delete-orphan", order_by="desc(Consultation.created_at)")

    @property
    def age(self) -> int:
        if not self.dob:
            return 35
        today = date.today()
        return today.year - self.dob.year - ((today.month, today.day) < (self.dob.month, self.dob.day))

    def __repr__(self):
        return f"<Patient(patient_id={self.patient_id}, full_name='{self.full_name}', phone='{self.phone}')>"
