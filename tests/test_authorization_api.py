import os
from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.core.security import create_access_token
from app.database.session import SessionLocal, get_db
from app.main import app
from app.modules.ip_allocations.models import IPAllocation
from app.modules.subnets.models import Subnet
from app.modules.users.models import User, UserRole
from app.modules.vpcs.models import VPC


@pytest.fixture
def authorization_api(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, dict[str, User], dict[str, dict[str, str]]]]:
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_POSTGRES_INTEGRATION_TESTS=1 to run PostgreSQL integration tests.")
    if make_url(settings.database_url).get_backend_name() != "postgresql":
        pytest.fail("Authorization integration tests require DATABASE_URL to point to PostgreSQL.")

    monkeypatch.setattr(settings, "vpc_provisioning_delay_seconds", 0.01)
    users: dict[str, User] = {}
    with SessionLocal() as db:
        for label, role in (
            ("owner-a", UserRole.USER),
            ("owner-b", UserRole.USER),
            ("admin", UserRole.ADMIN),
        ):
            user = User(
                username=f"authorization-{label}-{os.urandom(6).hex()}",
                email=f"authorization-{label}-{os.urandom(6).hex()}@example.com",
                hashed_password="integration-test-only",
                role=role,
            )
            db.add(user)
            users[label] = user
        db.commit()
        for user in users.values():
            db.refresh(user)

    tokens = {
        label: {
            "Authorization": (
                "Bearer "
                + create_access_token(
                    data={"sub": str(user.id), "role": UserRole(user.role).value}
                )
            )
        }
        for label, user in users.items()
    }

    def override_get_db():
        with SessionLocal() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client, users, tokens
    finally:
        app.dependency_overrides.clear()
        owner_ids = [user.id for user in users.values()]
        with SessionLocal() as db:
            db.execute(
                delete(IPAllocation).where(
                    IPAllocation.subnet_id.in_(
                        select(Subnet.id).where(
                            Subnet.vpc_id.in_(
                                select(VPC.id).where(VPC.owner_id.in_(owner_ids))
                            )
                        )
                    )
                )
            )
            db.execute(
                delete(Subnet).where(
                    Subnet.vpc_id.in_(select(VPC.id).where(VPC.owner_id.in_(owner_ids)))
                )
            )
            db.execute(delete(VPC).where(VPC.owner_id.in_(owner_ids)))
            db.execute(delete(User).where(User.id.in_(owner_ids)))
            db.commit()


def create_vpc(client: TestClient, headers: dict[str, str], **values: object) -> dict:
    payload = {
        "name": "authorization-vpc",
        "cidr_block": "10.110.0.0/16",
        "region": "us-east-1",
        **values,
    }
    response = client.post("/vpcs", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_non_owner_get_patch_and_delete_return_404(
    authorization_api: tuple[TestClient, dict[str, User], dict[str, dict[str, str]]],
) -> None:
    client, _, tokens = authorization_api
    vpc = create_vpc(client, tokens["owner-a"])
    subnet_response = client.post(
        f"/vpcs/{vpc['id']}/subnets",
        json={"name": "private", "type": "PRIVATE"},
        headers=tokens["owner-a"],
    )
    assert subnet_response.status_code == 201, subnet_response.text
    subnet = subnet_response.json()
    allocation_response = client.post(
        f"/subnets/{subnet['id']}/ip-allocations",
        json={},
        headers=tokens["owner-a"],
    )
    assert allocation_response.status_code == 201, allocation_response.text
    allocation_id = allocation_response.json()["id"]

    other = tokens["owner-b"]
    assert all(
        item["id"] != vpc["id"]
        for item in client.get("/vpcs", headers=other).json()
    )
    assert client.get(f"/vpcs/{vpc['id']}", headers=other).status_code == 404
    assert client.patch(
        f"/vpcs/{vpc['id']}", json={"name": "stolen"}, headers=other
    ).status_code == 404
    assert client.delete(f"/vpcs/{vpc['id']}", headers=other).status_code == 404
    assert client.get(f"/vpcs/{vpc['id']}/subnets", headers=other).status_code == 404
    assert client.post(
        f"/vpcs/{vpc['id']}/subnets",
        json={"name": "unauthorized", "type": "PRIVATE"},
        headers=other,
    ).status_code == 404
    assert client.get(f"/subnets/{subnet['id']}", headers=other).status_code == 404
    assert client.patch(
        f"/subnets/{subnet['id']}", json={"name": "stolen"}, headers=other
    ).status_code == 404
    assert client.delete(f"/subnets/{subnet['id']}", headers=other).status_code == 404
    assert client.get(
        f"/subnets/{subnet['id']}/ip-allocations", headers=other
    ).status_code == 404
    assert client.post(
        f"/subnets/{subnet['id']}/ip-allocations", json={}, headers=other
    ).status_code == 404
    assert client.get(f"/ip-allocations/{allocation_id}", headers=other).status_code == 404
    assert client.delete(f"/ip-allocations/{allocation_id}", headers=other).status_code == 404


def test_admin_can_read_and_write_resources_owned_by_other_users(
    authorization_api: tuple[TestClient, dict[str, User], dict[str, dict[str, str]]],
) -> None:
    client, _, tokens = authorization_api
    vpc = create_vpc(client, tokens["owner-a"])
    subnet_response = client.post(
        f"/vpcs/{vpc['id']}/subnets",
        json={"name": "private", "type": "PRIVATE"},
        headers=tokens["owner-a"],
    )
    assert subnet_response.status_code == 201, subnet_response.text
    subnet = subnet_response.json()
    allocation_response = client.post(
        f"/subnets/{subnet['id']}/ip-allocations",
        json={},
        headers=tokens["owner-a"],
    )
    assert allocation_response.status_code == 201, allocation_response.text
    allocation_id = allocation_response.json()["id"]

    admin = tokens["admin"]
    assert any(item["id"] == vpc["id"] for item in client.get("/vpcs", headers=admin).json())
    assert client.get(f"/vpcs/{vpc['id']}", headers=admin).status_code == 200
    assert client.patch(
        f"/vpcs/{vpc['id']}", json={"name": "admin-updated"}, headers=admin
    ).status_code == 200
    assert client.get(f"/vpcs/{vpc['id']}/subnets", headers=admin).status_code == 200
    assert client.get(f"/subnets/{subnet['id']}", headers=admin).status_code == 200
    assert client.patch(
        f"/subnets/{subnet['id']}", json={"name": "admin-subnet"}, headers=admin
    ).status_code == 200
    admin_subnet = client.post(
        f"/vpcs/{vpc['id']}/subnets",
        json={"name": "admin-created-subnet", "type": "PRIVATE"},
        headers=admin,
    )
    assert admin_subnet.status_code == 201, admin_subnet.text
    assert client.get(
        f"/subnets/{subnet['id']}/ip-allocations", headers=admin
    ).status_code == 200
    assert client.get(f"/ip-allocations/{allocation_id}", headers=admin).status_code == 200
    admin_allocation = client.post(
        f"/subnets/{subnet['id']}/ip-allocations",
        json={},
        headers=admin,
    )
    assert admin_allocation.status_code == 201, admin_allocation.text
    assert client.delete(f"/ip-allocations/{allocation_id}", headers=admin).status_code == 200
    assert client.delete(
        f"/ip-allocations/{admin_allocation.json()['id']}",
        headers=admin,
    ).status_code == 200


def test_regular_user_cannot_send_owner_id(
    authorization_api: tuple[TestClient, dict[str, User], dict[str, dict[str, str]]],
) -> None:
    client, users, tokens = authorization_api
    response = client.post(
        "/vpcs",
        json={
            "name": "forbidden-owner",
            "cidr_block": "10.111.0.0/16",
            "region": "us-east-1",
            "owner_id": users["owner-b"].id,
        },
        headers=tokens["owner-a"],
    )
    assert response.status_code == 422


def test_admin_can_create_vpc_for_another_owner(
    authorization_api: tuple[TestClient, dict[str, User], dict[str, dict[str, str]]],
) -> None:
    client, users, tokens = authorization_api
    response = client.post(
        "/vpcs",
        json={
            "name": "admin-created-for-owner",
            "cidr_block": "10.116.0.0/16",
            "region": "us-east-1",
            "owner_id": users["owner-b"].id,
        },
        headers=tokens["admin"],
    )

    assert response.status_code == 201, response.text
    with SessionLocal() as db:
        stored = db.get(VPC, UUID(response.json()["id"]))
        assert stored is not None
        assert stored.owner_id == users["owner-b"].id


def test_admin_vpc_creation_validates_destination_owner(
    authorization_api: tuple[TestClient, dict[str, User], dict[str, dict[str, str]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, users, tokens = authorization_api
    target_vpc = create_vpc(
        client,
        tokens["owner-b"],
        name="destination-name",
        cidr_block="10.112.0.0/16",
    )
    admin = tokens["admin"]

    same_name = client.post(
        "/vpcs",
        json={
            "name": "destination-name",
            "cidr_block": "10.114.0.0/16",
            "region": "us-east-1",
            "owner_id": users["owner-b"].id,
        },
        headers=admin,
    )
    assert same_name.status_code == 409

    overlapping = client.post(
        "/vpcs",
        json={
            "name": "different-name",
            "cidr_block": "10.112.1.0/24",
            "region": "us-east-1",
            "owner_id": users["owner-b"].id,
        },
        headers=admin,
    )
    assert overlapping.status_code == 409

    monkeypatch.setattr(settings, "vpc_limit_per_owner", 1)
    over_quota = client.post(
        "/vpcs",
        json={
            "name": "destination-second",
            "cidr_block": "10.115.0.0/16",
            "region": "us-east-1",
            "owner_id": users["owner-b"].id,
        },
        headers=admin,
    )
    assert over_quota.status_code == 409

    admin_owned = client.post(
        "/vpcs",
        json={
            "name": "destination-name",
            "cidr_block": "10.113.0.0/16",
            "region": "us-east-1",
        },
        headers=admin,
    )
    assert admin_owned.status_code == 201, admin_owned.text
    assert target_vpc["id"]


def test_patch_status_is_rejected_for_subnets_and_vpcs(
    authorization_api: tuple[TestClient, dict[str, User], dict[str, dict[str, str]]],
) -> None:
    client, _, tokens = authorization_api
    vpc = create_vpc(client, tokens["owner-a"])
    subnet_response = client.post(
        f"/vpcs/{vpc['id']}/subnets",
        json={"name": "private", "type": "PRIVATE"},
        headers=tokens["owner-a"],
    )
    assert subnet_response.status_code == 201, subnet_response.text
    subnet_id = subnet_response.json()["id"]

    assert client.patch(
        f"/vpcs/{vpc['id']}",
        json={"status": "ERROR"},
        headers=tokens["owner-a"],
    ).status_code == 422
    assert client.patch(
        f"/subnets/{subnet_id}",
        json={"status": "ERROR"},
        headers=tokens["owner-a"],
    ).status_code == 422
