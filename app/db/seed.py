from datetime import date, datetime, timezone
from sqlalchemy.orm import Session
from app.db.session import SessionLocal, engine, Base
from app.models.role import Role
from app.models.user import User
from app.models.doctor import Doctor
from app.models.patient import Patient
from app.models.consultation import Consultation
from app.core.security import get_password_hash
from app.core.logging import logger

def seed_database(db: Session = None):
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)
    
    close_session = False
    if db is None:
        db = SessionLocal()
        close_session = True

    try:
        logger.info("Seeding roles...")
        roles_data = [
            {
                "name": "Admin",
                "description": "System Administrator with full access to user management, audit logs, and settings",
                "permissions": ["all"]
            },
            {
                "name": "Doctor",
                "description": "Licensed Medical Practitioner with consultation recording, transcription, and report approval privileges",
                "permissions": ["read:patients", "write:patients", "record:consultation", "review:report", "approve:report"]
            },
            {
                "name": "Staff",
                "description": "Clinical intake and front-desk staff with patient intake and scheduling permissions",
                "permissions": ["read:patients", "write:patients", "schedule:appointment"]
            }
        ]

        roles_dict = {}
        for r_data in roles_data:
            role = db.query(Role).filter(Role.name == r_data["name"]).first()
            if not role:
                role = Role(
                    name=r_data["name"],
                    description=r_data["description"],
                    permissions=r_data["permissions"]
                )
                db.add(role)
                db.commit()
                db.refresh(role)
                logger.info(f"Created role: {role.name}")
            roles_dict[role.name] = role

        logger.info("Seeding users...")
        # 1. Default Doctor
        doctor_email = "doctor@hospital.org"
        doc_user = db.query(User).filter(User.email == doctor_email).first()
        if not doc_user:
            doc_user = User(
                email=doctor_email,
                hashed_password=get_password_hash("Doctor123!"),
                full_name="Dr. Anand Deshmukh, MD",
                role_id=roles_dict["Doctor"].role_id,
                is_active=True
            )
            db.add(doc_user)
            db.commit()
            db.refresh(doc_user)

            doc_profile = Doctor(
                user_id=doc_user.user_id,
                specialization="General Medicine & Pulmonology",
                registration_no="KMC-84920",
                department="Outpatient Department (OPD - Room 4)",
                contact_phone="+919845012345"
            )
            db.add(doc_profile)
            db.commit()
            logger.info(f"Created doctor account: {doctor_email} with registration KMC-84920")

        # 2. Default Admin
        admin_email = "admin@hospital.org"
        admin_user = db.query(User).filter(User.email == admin_email).first()
        if not admin_user:
            admin_user = User(
                email=admin_email,
                hashed_password=get_password_hash("Admin123!"),
                full_name="Hospital Administrator",
                role_id=roles_dict["Admin"].role_id,
                is_active=True
            )
            db.add(admin_user)
            db.commit()
            logger.info(f"Created admin account: {admin_email}")

        # 3. Default Staff
        staff_email = "staff@hospital.org"
        staff_user = db.query(User).filter(User.email == staff_email).first()
        if not staff_user:
            staff_user = User(
                email=staff_email,
                hashed_password=get_password_hash("Staff123!"),
                full_name="Pooja Sharma (Staff Nurse)",
                role_id=roles_dict["Staff"].role_id,
                is_active=True
            )
            db.add(staff_user)
            db.commit()
            logger.info(f"Created staff account: {staff_email}")

        logger.info("Seeding initial patient demographics...")
        patients_data = [
            {
                "full_name": "Basavaraj Patil (ಬಸವರಾಜ್ ಪಾಟೀಲ್)",
                "dob": date(1968, 6, 15),
                "gender": "Male",
                "phone": "+919880123456",
                "email": "basavaraj.patil@example.com",
                "address": "#42, Vidyanagar, Hubballi, Karnataka",
                "emergency_contact": "+919880123457 (Son - Suresh)",
                "blood_group": "O+",
                "preferred_language": "Kannada"
            },
            {
                "full_name": "Lakshmi Gowda (ಲಕ್ಷ್ಮಿ ಗೌಡ)",
                "dob": date(1982, 11, 24),
                "gender": "Female",
                "phone": "+919945678901",
                "email": "lakshmi.gowda@example.com",
                "address": "15th Main, Jayanagar 4th Block, Bengaluru, Karnataka",
                "emergency_contact": "+919945678902 (Husband - Ramesh)",
                "blood_group": "B+",
                "preferred_language": "Kannada-English"
            },
            {
                "full_name": "Mohammed Farooq (ಮೊಹಮ್ಮದ್ ಫಾರೂಕ್)",
                "dob": date(1995, 3, 10),
                "gender": "Male",
                "phone": "+919740112233",
                "email": "farooq.m@example.com",
                "address": "Tilakwadi, Belagavi, Karnataka",
                "emergency_contact": "+919740112234 (Father)",
                "blood_group": "A+",
                "preferred_language": "Kannada"
            }
        ]

        saved_patients = []
        for p_data in patients_data:
            existing = db.query(Patient).filter(Patient.phone == p_data["phone"]).first()
            if not existing:
                p = Patient(**p_data)
                db.add(p)
                db.commit()
                db.refresh(p)
                saved_patients.append(p)
                logger.info(f"Created sample patient: {p.full_name}")
            else:
                saved_patients.append(existing)

        # Seed initial sample consultation if not present
        if saved_patients:
            first_p = saved_patients[0]
            existing_consult = db.query(Consultation).filter(Consultation.patient_id == first_p.patient_id).first()
            if not existing_consult:
                initial_consult = Consultation(
                    patient_id=first_p.patient_id,
                    doctor_id=doc_user.user_id,
                    report_id=f"REP-KN-{first_p.patient_id}-2026-8841",
                    input_language="en",
                    original_english_speech="Patient Basavaraj presents for hypertension follow-up. Blood pressure is 150/95. Prescribed Telmisartan 40mg OD.",
                    kannada_transcript="ನಮಸ್ಕಾರ ಬಸವರಾಜ್ ಅವರೇ. ನಿಮ್ಮ ರಕ್ತದೊತ್ತಡ 150/95 ಇದೆ. ಟೆಲ್ಮಿಸಾರ್ಟನ್ 40 ಮಾತ್ರೆ ದಿನಕ್ಕೆ ಒಂದು ಬಾರಿ ಬೆಳಗ್ಗೆ ತೆಗೆದುಕೊಳ್ಳಿ.",
                    symptoms=[
                        {"entity": "ತಲೆನೋವು", "english": "Headache", "duration": "೩ ದಿನಗಳು (3 days)", "confidence": 0.96},
                        {"entity": "ತೀವ್ರ ಆಯಾಸ", "english": "Fatigue", "duration": "೩ ದಿನಗಳು (3 days)", "confidence": 0.93}
                    ],
                    diagnosis=[
                        {"entity": "ಅಧಿಕ ರಕ್ತದೊತ್ತಡ (ಹೈಪರ್‌ಟೆನ್ಷನ್)", "english": "Hypertension", "confidence": 0.95}
                    ],
                    medications=[
                        {"drug_name": "ಟೆಲ್ಮಿಸಾರ್ಟನ್ (Telmisartan)", "dosage": "೪೦ ಮಿ.ಗ್ರಾಂ (40mg)", "frequency": "ದಿನಕ್ಕೆ ಒಮ್ಮೆ ಬೆಳಗ್ಗೆ (OD Morning)", "duration": "೩೦ ದಿನಗಳು (30 Days)"}
                    ],
                    advice=[
                        {"instruction": "ಆಹಾರದಲ್ಲಿ ಉಪ್ಪಿನ ಪ್ರಮಾಣವನ್ನು ಕಡಿಮೆ ಮಾಡಿ."},
                        {"instruction": "ದಿನಕ್ಕೆ ೩೦ ನಿಮಿಷ ವಾಕಿಂಗ್ ಮಾಡಿ."}
                    ],
                    status="APPROVED",
                    signed_by_name=doc_user.full_name,
                    signed_doctor_reg="KMC-84920",
                    audio_filename="PT-0001_Doctor_English_Consultation.mp3",
                    created_at=datetime.now(timezone.utc),
                    signed_at=datetime.now(timezone.utc)
                )
                db.add(initial_consult)
                db.commit()
                logger.info(f"Created initial consultation record for patient {first_p.full_name}")

        logger.info("Database seeding completed successfully.")
    finally:
        if close_session:
            db.close()

if __name__ == "__main__":
    seed_database()
