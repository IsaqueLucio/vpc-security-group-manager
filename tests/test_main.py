def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_root_identifies_foundation(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {
        "api_name": "VPC & Security Group Manager",
        "status": "foundation",
    }


def test_legacy_domain_routes_are_not_registered(client):
    assert client.get("/projects").status_code == 404
    assert client.get("/issues/1").status_code == 404
    assert client.get("/integrations/github/example").status_code == 404