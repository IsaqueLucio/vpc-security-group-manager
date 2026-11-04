def test_user_me_requires_authentication(client, test_auth_user):
    assert client.get("/users/me").status_code == 401

    response = client.get("/users/me", headers=test_auth_user)
    assert response.status_code == 200
    assert response.json()["username"] == "Tester01"
    assert response.json()["role"] == "user"


def test_user_me_rejects_invalid_token(client):
    response = client.get(
        "/users/me",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 401
