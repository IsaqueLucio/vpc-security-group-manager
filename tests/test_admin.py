def test_admin_list_users_requires_admin(client, test_auth_user, test_auth_admin):
    assert client.get("/admin/users", headers=test_auth_user).status_code == 403

    response = client.get("/admin/users", headers=test_auth_admin)
    assert response.status_code == 200
    assert {user["role"] for user in response.json()} == {"user", "admin"}


def test_admin_delete_user(client, test_auth_admin):
    created = client.post(
        "/auth/register",
        json={
            "username": "to-delete",
            "email": "to-delete@example.com",
            "password": "StrongPassword@123",
        },
        headers=test_auth_admin,
    )
    assert created.status_code == 201

    response = client.delete(
        f"/admin/users/{created.json()['id']}",
        headers=test_auth_admin,
    )
    assert response.status_code == 204


def test_admin_cannot_delete_self(client, test_admin, test_auth_admin):
    response = client.delete(
        f"/admin/users/{test_admin.id}",
        headers=test_auth_admin,
    )
    assert response.status_code == 409


def test_non_admin_cannot_delete_users(client, test_auth_user):
    response = client.delete("/admin/users/1", headers=test_auth_user)
    assert response.status_code == 403
