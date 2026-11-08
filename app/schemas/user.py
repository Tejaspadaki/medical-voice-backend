from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, ConfigDict
from app.schemas.role import RoleResponse

class DoctorProfileOut(BaseModel):
    doctor_id: int
    specialization: str
    registration_no: str
    department: Optional[str] = None
    contact_phone: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    is_active: bool = True

class UserCreate(UserBase):
    password: str
    role_id: int
    specialization: Optional[str] = None
    registration_no: Optional[str] = None

class UserOut(UserBase):
    user_id: int
    role_id: int
    role: Optional[RoleResponse] = None
    doctor_profile: Optional[DoctorProfileOut] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
