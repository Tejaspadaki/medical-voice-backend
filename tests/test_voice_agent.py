import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.patient import Patient
from app.models.consultation import Consultation
from app.models.voice_agent import VoiceChatSession, PendingClinicalAction

def test_start_voice_session(client: TestClient, doctor_auth_header: dict, sample_patient: Patient):
    response = client.post(
        "/api/v1/voice-agent/session/start",
        json={"patient_id": sample_patient.patient_id, "language": "kn"},
        headers=doctor_auth_header
    )
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert data["patient_id"] == sample_patient.patient_id
    assert data["status"] == "active"

def test_voice_turn_patient_switch(client: TestClient, doctor_auth_header: dict, sample_patient: Patient):
    # Start session without patient
    start_res = client.post(
        "/api/v1/voice-agent/session/start",
        json={"language": "kn"},
        headers=doctor_auth_header
    )
    session_id = start_res.json()["session_id"]

    # Doctor says: "ರೋಗಿ ಬಸವರಾಜ್ ಅವರ ಪ್ರೊಫೈಲ್ ತೆರೆಯಿರಿ" (or uses patient's first name)
    first_name = sample_patient.full_name.split()[0]
    turn_res = client.post(
        "/api/v1/voice-agent/turn/text",
        json={
            "session_id": session_id,
            "text_input": f"Open patient {first_name}",
            "language": "kn"
        },
        headers=doctor_auth_header
    )
    assert turn_res.status_code == 200
    data = turn_res.json()
    assert data["intent_detected"] == "SWITCH_PATIENT"
    assert data["patient"]["patient_id"] == sample_patient.patient_id

def test_two_phase_confirmation_staging_and_commit(
    client: TestClient,
    doctor_auth_header: dict,
    sample_patient: Patient,
    db_session: Session
):
    # 1. Start session
    start_res = client.post(
        "/api/v1/voice-agent/session/start",
        json={"patient_id": sample_patient.patient_id, "language": "kn"},
        headers=doctor_auth_header
    )
    session_id = start_res.json()["session_id"]

    # 2. Stage clinical prescription
    stage_res = client.post(
        "/api/v1/voice-agent/turn/text",
        json={
            "session_id": session_id,
            "text_input": "Patient has severe headache. BP 150/95. Prescribe Telmisartan 40mg once daily in the morning and Metformin 500mg.",
            "language": "kn"
        },
        headers=doctor_auth_header
    )
    assert stage_res.status_code == 200
    data = stage_res.json()
    assert data["intent_detected"] == "STAGE_PRESCRIPTION"
    assert data["requires_confirmation"] is True
    assert data["pending_action"] is not None

    action_id = data["pending_action"]["action_id"]
    assert "Telmisartan" in str(data["pending_action"]["payload"]["medications"])
    assert "ದಾಖಲಿಸಿದ್ದೇನೆ" in data["assistant_tts_prompt"]

    # 3. Verbal confirmation ("ಹೌದು" / "Yes")
    confirm_turn_res = client.post(
        "/api/v1/voice-agent/turn/text",
        json={
            "session_id": session_id,
            "text_input": "ಹೌದು, ಖಚಿತಪಡಿಸಿ",
            "language": "kn"
        },
        headers=doctor_auth_header
    )
    assert confirm_turn_res.status_code == 200
    confirm_data = confirm_turn_res.json()
    assert confirm_data["intent_detected"] == "CONFIRM_ACTION"
    assert "ಖಚಿತಗೊಂಡಿದೆ" in confirm_data["assistant_reply_text"]

    # Verify consultation was committed to DB
    consultations = db_session.query(Consultation).filter(Consultation.patient_id == sample_patient.patient_id).all()
    assert len(consultations) >= 1
    latest_c = consultations[-1]
    assert latest_c.status == "APPROVED"
    assert "REP-KN-" in latest_c.report_id

def test_two_phase_confirmation_verbal_rejection(
    client: TestClient,
    doctor_auth_header: dict,
    sample_patient: Patient,
    db_session: Session
):
    start_res = client.post(
        "/api/v1/voice-agent/session/start",
        json={"patient_id": sample_patient.patient_id, "language": "kn"},
        headers=doctor_auth_header
    )
    session_id = start_res.json()["session_id"]

    # Stage prescription
    client.post(
        "/api/v1/voice-agent/turn/text",
        json={
            "session_id": session_id,
            "text_input": "Prescribe Paracetamol 650mg TDS for 3 days.",
            "language": "kn"
        },
        headers=doctor_auth_header
    )

    # Doctor says: "ಬೇಡ, ರದ್ದು ಮಾಡಿ" (No, cancel)
    reject_res = client.post(
        "/api/v1/voice-agent/turn/text",
        json={
            "session_id": session_id,
            "text_input": "ಬೇಡ ರದ್ದು ಮಾಡಿ",
            "language": "kn"
        },
        headers=doctor_auth_header
    )
    assert reject_res.status_code == 200
    data = reject_res.json()
    assert data["intent_detected"] == "REJECT_ACTION"
    assert "ರದ್ದುಗೊಳಿಸಲಾಗಿದೆ" in data["assistant_reply_text"]

    # Verify pending action is rejected in DB
    pending = db_session.query(PendingClinicalAction).filter(PendingClinicalAction.session_id == session_id).first()
    assert pending.status == "rejected"

def test_two_phase_patient_creation_and_prescription_flow(
    client: TestClient,
    doctor_auth_header: dict,
    db_session: Session
):
    # 1. Start a session
    start_res = client.post(
        "/api/v1/voice-agent/session/start",
        json={"language": "kn"},
        headers=doctor_auth_header
    )
    assert start_res.status_code == 200
    session_id = start_res.json()["session_id"]

    # 2. Doctor says: "Create patient Tejas Padaki, 28 years male"
    turn1_res = client.post(
        "/api/v1/voice-agent/turn/text",
        json={
            "session_id": session_id,
            "text_input": "Create patient Tejas Padaki, 28 years male, phone 9876543210",
            "language": "kn"
        },
        headers=doctor_auth_header
    )
    assert turn1_res.status_code == 200
    turn1 = turn1_res.json()
    assert turn1["intent_detected"] == "STAGE_PATIENT_CREATION"
    assert turn1["requires_confirmation"] is True
    assert turn1["pending_action"]["action_type"] == "CREATE_PATIENT"
    assert turn1["pending_action"]["payload"]["name"] == "Tejas Padaki"
    assert turn1["pending_action"]["payload"]["age"] == 28
    assert turn1["pending_action"]["payload"]["gender"] == "M"

    # 3. Doctor verbally confirms: "ಹೌದು ಖಚಿತಪಡಿಸಿ" (Yes, confirm)
    confirm_res = client.post(
        "/api/v1/voice-agent/turn/text",
        json={
            "session_id": session_id,
            "text_input": "ಹೌದು ಖಚಿತಪಡಿಸಿ",
            "language": "kn"
        },
        headers=doctor_auth_header
    )
    assert confirm_res.status_code == 200
    confirm_data = confirm_res.json()
    assert confirm_data["intent_detected"] == "CONFIRM_ACTION"
    assert confirm_data["patient"] is not None
    assert confirm_data["patient"]["name"] == "Tejas Padaki"

    # Verify patient was actually created in database
    created_patient = db_session.query(Patient).filter(Patient.full_name == "Tejas Padaki").first()
    assert created_patient is not None
    assert created_patient.gender == "M"

    # 4. Doctor proceeds to prescribe medications for Tejas Padaki:
    prescribe_res = client.post(
        "/api/v1/voice-agent/turn/text",
        json={
            "session_id": session_id,
            "text_input": "He has high fever and body ache. Prescribe Paracetamol 650mg TDS and Cetirizine 10mg OD.",
            "language": "kn"
        },
        headers=doctor_auth_header
    )
    assert prescribe_res.status_code == 200
    prescribe_data = prescribe_res.json()
    assert prescribe_data["intent_detected"] == "STAGE_PRESCRIPTION"
    assert prescribe_data["requires_confirmation"] is True
    assert prescribe_data["pending_action"]["action_type"] == "CREATE_PRESCRIPTION"
    assert "Paracetamol" in str(prescribe_data["pending_action"]["payload"]["medications"])

    # 5. Doctor verbally confirms prescription
    confirm_prescribe_res = client.post(
        "/api/v1/voice-agent/turn/text",
        json={
            "session_id": session_id,
            "text_input": "ಸರಿ, ಸೇವ್ ಮಾಡಿ",
            "language": "kn"
        },
        headers=doctor_auth_header
    )
    assert confirm_prescribe_res.status_code == 200
    assert confirm_prescribe_res.json()["intent_detected"] == "CONFIRM_ACTION"

    # Verify Consultation committed in DB for Tejas Padaki
    consultation = db_session.query(Consultation).filter(Consultation.patient_id == created_patient.patient_id).first()
    assert consultation is not None
    assert consultation.status == "APPROVED"


