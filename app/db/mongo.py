import os
import certifi
from datetime import datetime, timezone, date
from typing import Dict, Any, Optional, List
from pymongo import MongoClient, ReturnDocument
from app.core.config import settings
from app.core.logging import logger
from app.core.security import get_password_hash

# Global MongoDB Client
mongo_client: Optional[MongoClient] = None

def get_mongo_client() -> MongoClient:
    global mongo_client
    if mongo_client is None:
        logger.info(f"Connecting to MongoDB: {settings.MONGODB_URL.split('@')[-1] if '@' in settings.MONGODB_URL else 'localhost'}...")
        try:
            ca = certifi.where()
            mongo_client = MongoClient(
                settings.MONGODB_URL,
                serverSelectionTimeoutMS=8000,
                tlsCAFile=ca
            )
        except Exception as e:
            logger.warning(f"Failed to use certifi CA bundle, falling back: {e}")
            mongo_client = MongoClient(settings.MONGODB_URL, serverSelectionTimeoutMS=8000)
    return mongo_client

def get_mongo_db():
    client = get_mongo_client()
    return client[settings.MONGODB_DB_NAME]

def get_next_sequence(sequence_name: str, db = None) -> int:
    """
    Atomic sequence generator for numeric IDs (patient_id, consultation_id, user_id).
    """
    if db is None:
        db = get_mongo_db()
    
    counter = db.counters.find_one_and_update(
        {"_id": sequence_name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    return counter["seq"]

def clean_doc(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Cleans a MongoDB document for JSON/Pydantic serialization.
    Converts ObjectId to string, ensures date/datetime fields serialize cleanly.
    """
    if not doc:
        return None
    res = dict(doc)
    if "_id" in res:
        res["_id"] = str(res["_id"])
    return res

def clean_docs(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [clean_doc(d) for d in docs if d]

class DictObj:
    """Wrapper that allows dot attribute access on dictionary keys."""
    def __init__(self, d):
        self._d = d or {}
    def __getattr__(self, item):
        val = self._d.get(item)
        if isinstance(val, dict):
            return DictObj(val)
        return val
    def __getitem__(self, item):
        return self._d[item]
    def get(self, item, default=None):
        return self._d.get(item, default)


def init_mongo_db():
    """
    Initializes indexes and seeds default clinical roles, doctor, and sample patients into MongoDB.
    """
    try:
        db = get_mongo_db()
        logger.info(f"Initializing MongoDB collections and indexes for database '{settings.MONGODB_DB_NAME}'...")

        # 1. Create Indexes
        db.users.create_index("email", unique=True)
        db.users.create_index("user_id", unique=True)
        db.roles.create_index("name", unique=True)
        db.patients.create_index("patient_id", unique=True)
        db.patients.create_index("phone")
        db.patients.create_index("full_name")
        db.consultations.create_index("consultation_id", unique=True)
        db.consultations.create_index("report_id", unique=True)
        db.consultations.create_index("patient_id")
        db.voice_chat_sessions.create_index("session_id", unique=True)
        db.voice_chat_turns.create_index("turn_id", unique=True)
        db.voice_chat_turns.create_index("session_id")
        db.pending_clinical_actions.create_index("action_id", unique=True)
        db.pending_clinical_actions.create_index("session_id")

        # 2. Seed Default Roles
        roles_data = [
            {"role_id": 1, "name": "Admin", "description": "System Administrator", "permissions": ["all"]},
            {"role_id": 2, "name": "Doctor", "description": "Licensed Medical Practitioner", "permissions": ["read:patients", "write:patients", "record:consultation", "review:report", "approve:report"]},
            {"role_id": 3, "name": "Staff", "description": "Clinical Intake Staff", "permissions": ["read:patients", "write:patients", "schedule:appointment"]}
        ]
        for r in roles_data:
            db.roles.update_one({"name": r["name"]}, {"$setOnInsert": r}, upsert=True)

        # 3. Seed Default Doctor Account
        doctor_email = "doctor@hospital.org"
        existing_doc = db.users.find_one({"email": doctor_email})
        if not existing_doc:
            doc_id = get_next_sequence("user_id", db)
            db.users.insert_one({
                "user_id": doc_id,
                "email": doctor_email,
                "hashed_password": get_password_hash("Doctor123!"),
                "full_name": "Dr. Anand Deshmukh, MD",
                "role_id": 2,
                "role_name": "Doctor",
                "is_active": True,
                "created_at": datetime.now(timezone.utc),
                "doctor_profile": {
                    "specialization": "General Medicine & Pulmonology",
                    "registration_no": "KMC-84920",
                    "department": "Outpatient Department (OPD - Room 4)",
                    "contact_phone": "+919845012345"
                }
            })
            logger.info("MongoDB: Seeded default doctor account (doctor@hospital.org / Doctor123!)")

        # 4. Seed Default Admin Account
        admin_email = "admin@hospital.org"
        if not db.users.find_one({"email": admin_email}):
            admin_id = get_next_sequence("user_id", db)
            db.users.insert_one({
                "user_id": admin_id,
                "email": admin_email,
                "hashed_password": get_password_hash("Admin123!"),
                "full_name": "Hospital Administrator",
                "role_id": 1,
                "role_name": "Admin",
                "is_active": True,
                "created_at": datetime.now(timezone.utc)
            })

        # 5. Seed Initial Patients if none exist
        if db.patients.count_documents({}) == 0:
            sample_patients = [
                {
                    "full_name": "Basavaraj Patil (ಬಸವರಾಜ್ ಪಾಟೀಲ್)",
                    "dob": "1968-06-15",
                    "gender": "Male",
                    "phone": "+919880123456",
                    "email": "basavaraj.patil@example.com",
                    "address": "Gandhi Nagar, 2nd Cross, Hubballi, Karnataka 580020",
                    "emergency_contact": "+919880998877 (Suresh Patil - Son)",
                    "blood_group": "B+",
                    "preferred_language": "Kannada",
                    "created_at": datetime.now(timezone.utc)
                },
                {
                    "full_name": "Lakshmi Gowda (ಲಕ್ಷ್ಮಿ ಗೌಡ)",
                    "dob": "1982-11-23",
                    "gender": "Female",
                    "phone": "+919945234567",
                    "email": "lakshmi.gowda@example.com",
                    "address": "Kuvempu Layout, Mandya, Karnataka 571401",
                    "emergency_contact": "+919945112233 (Ramesh Gowda - Husband)",
                    "blood_group": "O+",
                    "preferred_language": "Kannada",
                    "created_at": datetime.now(timezone.utc)
                },
                {
                    "full_name": "Mohammed Farooq (ಮೊಹಮ್ಮದ್ ಫಾರೂಕ್)",
                    "dob": "1955-03-08",
                    "gender": "Male",
                    "phone": "+919731345678",
                    "email": "farooq.m@example.com",
                    "address": "Bhatkal Street, Mangaluru, Karnataka 575001",
                    "emergency_contact": "+919731887766 (Ayesha - Daughter)",
                    "blood_group": "A+",
                    "preferred_language": "Kannada",
                    "created_at": datetime.now(timezone.utc)
                }
            ]
            for p in sample_patients:
                pid = get_next_sequence("patient_id", db)
                p["patient_id"] = pid
                db.patients.insert_one(p)
            logger.info("MongoDB: Seeded 3 initial sample patients.")

        logger.info("MongoDB Atlas: Schema initialization and seeding complete.")

    except Exception as e:
        logger.error(f"MongoDB Atlas initialization error: {e}")
