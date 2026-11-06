def test_health(client, test_auth_user):
    response = client.get("/health", headers=test_auth_user)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_root_identifies_foundation(client, test_auth_user):
    response = client.get("/", headers=test_auth_user)
    assert response.status_code == 200
    assert response.json() == {
        "api_name": "VPC & Security Group Manager",
        "status": "foundation",
    }


def test_legacy_domain_routes_are_not_registered(client, test_auth_user):
    assert client.get("/projects", headers=test_auth_user).status_code == 404
    assert client.get("/issues/1", headers=test_auth_user).status_code == 404
    assert client.get("/integrations/github/example", headers=test_auth_user).status_code == 404