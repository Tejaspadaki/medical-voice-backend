def test_login_success(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "doctor@hospital.org", "password": "Doctor123!"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "doctor@hospital.org"
    assert data["user"]["role"]["name"] == "Doctor"
    assert data["user"]["doctor_profile"]["registration_no"] == "KMC-84920"

def test_login_invalid_password(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "doctor@hospital.org", "password": "WrongPassword999!"}
    )
    assert response.status_code == 401
    assert "Incorrect email or password" in response.json()["detail"]

def test_login_nonexistent_user(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "notfound@hospital.org", "password": "AnyPassword123!"}
    )
    assert response.status_code == 401

def test_login_inactive_user(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "inactive@hospital.org", "password": "Inactive123!"}
    )
    assert response.status_code == 403
    assert "inactive" in response.json()["detail"].lower()

def test_token_refresh_flow(client):
    login_res = client.post(
        "/api/auth/login",
        json={"email": "doctor@hospital.org", "password": "Doctor123!"}
    )
    assert login_res.status_code == 200
    refresh_token = login_res.json()["refresh_token"]

    refresh_res = client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    assert refresh_res.status_code == 200
    new_data = refresh_res.json()
    assert "access_token" in new_data
    assert new_data["token_type"] == "bearer"

def test_token_refresh_invalid(client):
    response = client.post(
        "/api/auth/refresh",
        json={"refresh_token": "invalid.jwt.token.string"}
    )
    assert response.status_code == 401

def test_logout_and_revocation(client):
    login_res = client.post(
        "/api/auth/login",
        json={"email": "doctor@hospital.org", "password": "Doctor123!"}
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Verify token works before logout
    me_res = client.get("/api/auth/me", headers=headers)
    assert me_res.status_code == 200

    # Perform logout
    logout_res = client.post("/api/auth/logout", headers=headers)
    assert logout_res.status_code == 200
    assert logout_res.json()["success"] is True

    # Verify token is now rejected
    me_after_logout = client.get("/api/auth/me", headers=headers)
    assert me_after_logout.status_code == 401

def test_get_me_authenticated(client, doctor_auth_header):
    response = client.get("/api/auth/me", headers=doctor_auth_header)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "doctor@hospital.org"
    assert data["full_name"] == "Dr. Anand Deshmukh"

def test_get_me_unauthenticated(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401
