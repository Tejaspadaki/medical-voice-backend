from sqlalchemy import Column, Integer, String, JSON, Text
from sqlalchemy.orm import relationship
from app.db.session import Base

class Role(Base):
    __tablename__ = "roles"

    role_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False, index=True) # e.g. 'Doctor', 'Admin', 'Staff'
    description = Column(String(255), nullable=True)
    permissions = Column(JSON, nullable=True, default=list) # e.g. ["read:patients", "create:consultations"]

    # Relationships
    users = relationship("User", back_populates="role", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Role(role_id={self.role_id}, name='{self.name}')>"
