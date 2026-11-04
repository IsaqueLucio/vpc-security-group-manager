def test_register_user_does_not_expose_password_or_hash(client):
    response = client.post(
        "/auth/register",
        json={
            "username": "new-user",
            "email": "new-user@example.com",
            "password": "StrongPassword@123",
        },
    )

    assert response.status_code == 201
    assert response.json()["role"] == "user"
    assert "password" not in response.json()
    assert "hashed_password" not in response.json()


def test_register_rejects_duplicate_username_and_email(client):
    payload = {
        "username": "new-user",
        "email": "new-user@example.com",
        "password": "StrongPassword@123",
    }
    assert client.post("/auth/register", json=payload).status_code == 201

    duplicate_username = {
        **payload,
        "email": "another@example.com",
    }
    duplicate_email = {
        **payload,
        "username": "another-user",
    }
    assert client.post("/auth/register", json=duplicate_username).status_code == 409
    assert client.post("/auth/register", json=duplicate_email).status_code == 409


def test_register_validates_password(client):
    response = client.post(
        "/auth/register",
        json={
            "username": "new-user",
            "email": "new-user@example.com",
            "password": "weak",
        },
    )

    assert response.status_code == 422


def test_login_and_reject_invalid_credentials(client):
    client.post(
        "/auth/register",
        json={
            "username": "login-user",
            "email": "login-user@example.com",
            "password": "StrongPassword@123",
        },
    )

    response = client.post(
        "/auth/login",
        data={
            "username": "login-user@example.com",
            "password": "StrongPassword@123",
        },
    )
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["access_token"]

    invalid_credentials = client.post(
        "/auth/login",
        data={
            "username": "login-user@example.com",
            "password": "incorrect",
        },
    )
    assert invalid_credentials.status_code == 401
