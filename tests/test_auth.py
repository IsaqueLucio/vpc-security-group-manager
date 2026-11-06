def test_register_user_does_not_expose_password_or_hash(client, test_auth_user):
    response = client.post(
        "/auth/register",
        json={
            "username": "new-user",
            "email": "new-user@example.com",
            "password": "StrongPassword@123",
        },
        headers=test_auth_user,
    )

    assert response.status_code == 201
    assert response.json()["role"] == "user"
    assert "password" not in response.json()
    assert "hashed_password" not in response.json()


def test_register_rejects_duplicate_username_and_email(client, test_auth_user):
    payload = {
        "username": "new-user",
        "email": "new-user@example.com",
        "password": "StrongPassword@123",
    }
    assert client.post("/auth/register", json=payload, headers=test_auth_user).status_code == 201

    duplicate_username = {
        **payload,
        "email": "another@example.com",
    }
    duplicate_email = {
        **payload,
        "username": "another-user",
    }
    assert client.post(
        "/auth/register", json=duplicate_username, headers=test_auth_user
    ).status_code == 409
    assert client.post(
        "/auth/register", json=duplicate_email, headers=test_auth_user
    ).status_code == 409


def test_register_validates_password(client, test_auth_user):
    response = client.post(
        "/auth/register",
        json={
            "username": "new-user",
            "email": "new-user@example.com",
            "password": "weak",
        },
        headers=test_auth_user,
    )

    assert response.status_code == 422


def test_login_and_reject_invalid_credentials(client, test_db):
    from app.core.security import decode_access_token, hash_password
    from app.modules.users.models import UserRole
    from app.modules.users.models import User

    user = User(
        username="login-user",
        email="login-user@example.com",
        hashed_password=hash_password("StrongPassword@123"),
        role=UserRole.USER,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)

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
    claims = decode_access_token(response.json()["access_token"])
    assert claims is not None
    assert claims["sub"] == str(user.id)
    assert claims["role"] == "user"

    invalid_credentials = client.post(
        "/auth/login",
        data={
            "username": "login-user@example.com",
            "password": "incorrect",
        },
    )
    assert invalid_credentials.status_code == 401


def test_all_endpoints_except_login_require_authentication(client):
    assert client.get("/health").status_code == 401
    assert client.get("/").status_code == 401
    assert client.get("/vpcs").status_code == 401
    assert client.get("/subnets/00000000-0000-0000-0000-000000000001").status_code == 401
    assert client.get(
        "/ip-allocations/00000000-0000-0000-0000-000000000001"
    ).status_code == 401
    assert client.post("/auth/register", json={}).status_code == 401
    assert (
        client.post(
            "/auth/login",
            data={"username": "nobody", "password": "invalid"},
        ).status_code
        == 401
    )
