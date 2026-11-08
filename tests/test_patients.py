def test_create_patient_success(client, doctor_auth_header):
    payload = {
        "full_name": "Smt. Shailaja Hegde",
        "dob": "1975-08-20",
        "gender": "Female",
        "phone": "+919448123456",
        "email": "shailaja.hegde@example.com",
        "address": "Sirsi, Uttara Kannada, Karnataka",
        "emergency_contact": "+919448123457 (Daughter)",
        "blood_group": "AB+",
        "preferred_language": "Kannada"
    }
    response = client.post("/api/patients", json=payload, headers=doctor_auth_header)
    assert response.status_code == 201
    data = response.json()
    assert data["patient_id"] is not None
    assert data["full_name"] == "Smt. Shailaja Hegde"
    assert data["preferred_language"] == "Kannada"

def test_create_patient_unauthenticated(client):
    payload = {
        "full_name": "Unauthorized Test Patient",
        "gender": "Male",
        "phone": "+919800000000"
    }
    response = client.post("/api/patients", json=payload)
    assert response.status_code == 401

def test_get_patient_by_id_success(client, doctor_auth_header):
    # Retrieve the initial seeded patient (ID 1)
    response = client.get("/api/patients/1", headers=doctor_auth_header)
    assert response.status_code == 200
    data = response.json()
    assert data["patient_id"] == 1
    assert data["full_name"] == "Basavaraj Patil"
    assert data["gender"] == "Male"

def test_get_patient_not_found(client, doctor_auth_header):
    response = client.get("/api/patients/99999", headers=doctor_auth_header)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

def test_list_patients_pagination(client, doctor_auth_header):
    response = client.get("/api/patients?page=1&size=10", headers=doctor_auth_header)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 1
    assert len(data["items"]) >= 1

def test_list_patients_search_filter(client, doctor_auth_header):
    # Search by seeded name
    response = client.get("/api/patients?search=Basavaraj", headers=doctor_auth_header)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["full_name"] == "Basavaraj Patil"

    # Search by non-matching query
    response_empty = client.get("/api/patients?search=NonExistentPersonNameXYZ", headers=doctor_auth_header)
    assert response_empty.status_code == 200
    assert response_empty.json()["total"] == 0

def test_update_patient(client, doctor_auth_header):
    update_payload = {
        "address": "Updated Address - Rajajinagar, Bengaluru",
        "blood_group": "O-"
    }
    response = client.put("/api/patients/1", json=update_payload, headers=doctor_auth_header)
    assert response.status_code == 200
    data = response.json()
    assert data["address"] == "Updated Address - Rajajinagar, Bengaluru"
    assert data["blood_group"] == "O-"

def test_staff_can_create_patient(client, staff_auth_header):
    payload = {
        "full_name": "Girish Bhat",
        "gender": "Male",
        "phone": "+919844001122",
        "preferred_language": "Kannada"
    }
    response = client.post("/api/patients", json=payload, headers=staff_auth_header)
    assert response.status_code == 201
    assert response.json()["full_name"] == "Girish Bhat"
