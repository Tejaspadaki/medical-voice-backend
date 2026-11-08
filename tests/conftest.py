import pytest
from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.session import Base, get_db
from app.models.role import Role
from app.models.user import User
from app.models.doctor import Doctor
from app.models.patient import Patient
from app.core.security import get_password_hash, create_access_token

# Test in-memory SQLite database
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()

    # Seed roles
    roles = {
        "Admin": Role(name="Admin", permissions=["all"]),
        "Doctor": Role(name="Doctor", permissions=["read:patients", "write:patients", "record:consultation", "approve:report"]),
        "Staff": Role(name="Staff", permissions=["read:patients", "write:patients"])
    }
    for r in roles.values():
        session.add(r)
    session.commit()

    # Seed Doctor user
    doctor_user = User(
        email="doctor@hospital.org",
        hashed_password=get_password_hash("Doctor123!"),
        full_name="Dr. Anand Deshmukh",
        role_id=roles["Doctor"].role_id,
        is_active=True
    )
    session.add(doctor_user)
    session.commit()
    session.refresh(doctor_user)

    doctor_profile = Doctor(
        user_id=doctor_user.user_id,
        specialization="General Medicine",
        registration_no="KMC-84920",
        department="OPD"
    )
    session.add(doctor_profile)

    # Seed Admin user
    admin_user = User(
        email="admin@hospital.org",
        hashed_password=get_password_hash("Admin123!"),
        full_name="Hospital Admin",
        role_id=roles["Admin"].role_id,
        is_active=True
    )
    session.add(admin_user)

    # Seed Staff user
    staff_user = User(
        email="staff@hospital.org",
        hashed_password=get_password_hash("Staff123!"),
        full_name="Intake Staff",
        role_id=roles["Staff"].role_id,
        is_active=True
    )
    session.add(staff_user)

    # Seed Inactive user
    inactive_user = User(
        email="inactive@hospital.org",
        hashed_password=get_password_hash("Inactive123!"),
        full_name="Inactive Doctor",
        role_id=roles["Doctor"].role_id,
        is_active=False
    )
    session.add(inactive_user)

    # Seed initial test patient
    test_patient = Patient(
        full_name="Basavaraj Patil",
        dob=date(1968, 6, 15),
        gender="Male",
        phone="+919880123456",
        email="basavaraj@example.com",
        address="Hubballi, Karnataka",
        blood_group="O+",
        preferred_language="Kannada"
    )
    session.add(test_patient)
    session.commit()

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

@pytest.fixture(scope="function")
def doctor_auth_header(db_session):
    doctor = db_session.query(User).filter(User.email == "doctor@hospital.org").first()
    token = create_access_token(subject=doctor.user_id, extra_claims={"role": "Doctor", "email": doctor.email})
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture(scope="function")
def admin_auth_header(db_session):
    admin = db_session.query(User).filter(User.email == "admin@hospital.org").first()
    token = create_access_token(subject=admin.user_id, extra_claims={"role": "Admin", "email": admin.email})
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture(scope="function")
def staff_auth_header(db_session):
    staff = db_session.query(User).filter(User.email == "staff@hospital.org").first()
    token = create_access_token(subject=staff.user_id, extra_claims={"role": "Staff", "email": staff.email})
    return {"Authorization": f"Bearer {token}"}
