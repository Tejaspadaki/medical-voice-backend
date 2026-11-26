from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, EmailStr, Field

from app.core.dependencies import MongoUser, require_roles
from app.core.security import get_password_hash
from app.db.mongo import clean_doc, get_mongo_db, get_next_sequence

router = APIRouter(prefix="/admin", tags=["Admin - Doctor & Staff Management"])


class AdminCreateUserRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=100)
    role_name: str = Field("Doctor", description="Doctor or Staff")
    specialization: Optional[str] = "General Medicine"
    registration_no: Optional[str] = "KMC-00000"
    department: Optional[str] = "Outpatient Department (OPD)"
    contact_phone: Optional[str] = "+919845000000"


class AdminUserStatusRequest(BaseModel):
    is_active: bool


def _sanitize_user(doc: Dict[str, Any]) -> Dict[str, Any]:
    d = clean_doc(doc) or {}
    d.pop("hashed_password", None)
    return d


@router.get("/users", summary="List All Doctors, Staff & Admin Accounts (Admin Only)")
def list_users(
    db=Depends(get_mongo_db),
    current_user: MongoUser = Depends(require_roles(["Admin"])),
):
    docs = list(db.users.find().sort("user_id", 1))
    users = [_sanitize_user(u) for u in docs]
    return {
        "items": users,
        "total": len(users),
        "doctors_count": sum(1 for u in users if u.get("role_name") == "Doctor"),
        "staff_count": sum(1 for u in users if u.get("role_name") == "Staff"),
        "admin_count": sum(1 for u in users if u.get("role_name") == "Admin"),
    }


@router.post("/users", status_code=status.HTTP_201_CREATED, summary="Add New Doctor or Staff Account (Admin Only)")
def create_doctor_or_staff(
    payload: AdminCreateUserRequest,
    db=Depends(get_mongo_db),
    current_user: MongoUser = Depends(require_roles(["Admin"])),
):
    role_name = payload.role_name.strip().title()
    if role_name not in ("Doctor", "Staff"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin can only create 'Doctor' or 'Staff' accounts here.",
        )

    existing = db.users.find_one({"email": payload.email.lower().strip()})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"An account with email '{payload.email}' already exists.",
        )

    user_id = get_next_sequence("user_id", db)
    role_id = 2 if role_name == "Doctor" else 3
    now = datetime.now(timezone.utc)

    doc: Dict[str, Any] = {
        "user_id": user_id,
        "email": payload.email.lower().strip(),
        "hashed_password": get_password_hash(payload.password),
        "full_name": payload.full_name.strip(),
        "role_id": role_id,
        "role_name": role_name,
        "is_active": True,
        "created_at": now,
    }

    if role_name == "Doctor":
        doc["doctor_profile"] = {
            "doctor_id": user_id,
            "specialization": payload.specialization or "General Medicine",
            "registration_no": payload.registration_no or f"KMC-{90000 + user_id}",
            "department": payload.department or "Outpatient Department (OPD)",
            "contact_phone": payload.contact_phone or "+919845000000",
        }

    db.users.insert_one(dict(doc))
    return _sanitize_user(doc)


@router.patch("/users/{user_id}/status", summary="Activate or Deactivate Doctor/Staff Account (Admin Only)")
def toggle_user_status(
    user_id: int = Path(..., ge=1),
    payload: AdminUserStatusRequest = ...,
    db=Depends(get_mongo_db),
    current_user: MongoUser = Depends(require_roles(["Admin"])),
):
    if user_id == getattr(current_user, "user_id", None) and not payload.is_active:
        raise HTTPException(status_code=400, detail="Admin cannot deactivate their own account.")

    target = db.users.find_one({"user_id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail=f"User #{user_id} not found.")

    db.users.update_one({"user_id": user_id}, {"$set": {"is_active": payload.is_active}})
    updated = db.users.find_one({"user_id": user_id})
    return _sanitize_user(updated)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove Doctor/Staff Account (Admin Only)")
def delete_user(
    user_id: int = Path(..., ge=1),
    db=Depends(get_mongo_db),
    current_user: MongoUser = Depends(require_roles(["Admin"])),
):
    if user_id == getattr(current_user, "user_id", None):
        raise HTTPException(status_code=400, detail="Admin cannot delete their own account.")

    target = db.users.find_one({"user_id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail=f"User #{user_id} not found.")

    db.users.delete_one({"user_id": user_id})
    return None
