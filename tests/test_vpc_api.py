import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.database.session import SessionLocal, get_db
from app.main import app
from app.modules.users.models import User, UserRole
from app.modules.vpcs.models import Subnet, VPC
from app.modules.vpcs.router import get_vpc_owner_id


@pytest.fixture
def postgres_vpc_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_POSTGRES_INTEGRATION_TESTS=1 to run PostgreSQL integration tests.")
    if make_url(settings.database_url).get_backend_name() != "postgresql":
        pytest.fail("VPC API integration tests require DATABASE_URL to point to PostgreSQL.")

    monkeypatch.setattr(settings, "vpc_provisioning_delay_seconds", 0.01)
    with SessionLocal() as db:
        user = User(
            username=f"vpc-test-{os.urandom(8).hex()}",
            email=f"vpc-test-{os.urandom(8).hex()}@example.com",
            hashed_password="integration-test-only",
            role=UserRole.USER,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        owner_id = user.id

    def override_get_db():
        with SessionLocal() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_vpc_owner_id] = lambda: owner_id
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        with SessionLocal() as db:
            db.execute(delete(Subnet).where(Subnet.vpc_id.in_(
                db.query(VPC.id).where(VPC.owner_id == owner_id)
            )))
            db.execute(delete(VPC).where(VPC.owner_id == owner_id))
            db.execute(delete(User).where(User.id == owner_id))
            db.commit()


def vpc_payload(
    name: str = "test-vpc",
    cidr_block: str = "10.40.0.0/16",
) -> dict[str, str]:
    return {
        "name": name,
        "cidr_block": cidr_block,
        "region": "us-east-1",
    }


def create_vpc(client: TestClient, **payload_values: str) -> dict:
    response = client.post("/vpcs", json=vpc_payload(**payload_values))
    assert response.status_code == 201, response.text
    return response.json()


def test_create_vpc_returns_pending_status(postgres_vpc_client: TestClient) -> None:
    response = postgres_vpc_client.post("/vpcs", json=vpc_payload())
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "PENDING"
    assert response.json()["cidr_block"] == "10.40.0.0/16"


def test_duplicate_vpc_name_returns_conflict(postgres_vpc_client: TestClient) -> None:
    create_vpc(postgres_vpc_client)
    response = postgres_vpc_client.post(
        "/vpcs",
        json=vpc_payload(name="test-vpc", cidr_block="10.41.0.0/16"),
    )
    assert response.status_code == 409


def test_duplicate_vpc_cidr_returns_conflict(postgres_vpc_client: TestClient) -> None:
    create_vpc(postgres_vpc_client)
    response = postgres_vpc_client.post(
        "/vpcs",
        json=vpc_payload(name="another-vpc", cidr_block="10.40.0.0/16"),
    )
    assert response.status_code == 409
    assert "CIDR" in response.json()["detail"]


def test_overlapping_vpc_cidr_returns_conflict(postgres_vpc_client: TestClient) -> None:
    create_vpc(postgres_vpc_client)
    response = postgres_vpc_client.post(
        "/vpcs",
        json=vpc_payload(name="overlapping-vpc", cidr_block="10.40.1.0/24"),
    )
    assert response.status_code == 409
    assert "sobrepõe" in response.json()["detail"]


def test_reserved_vpc_cidr_returns_unprocessable_entity(postgres_vpc_client: TestClient) -> None:
    response = postgres_vpc_client.post(
        "/vpcs",
        json=vpc_payload(cidr_block="169.254.0.0/16"),
    )
    assert response.status_code == 422


@pytest.mark.parametrize("cidr_block", ["10.40.0.0/15", "10.40.1.0/16"])
def test_out_of_range_or_noncanonical_cidr_returns_422(
    postgres_vpc_client: TestClient,
    cidr_block: str,
) -> None:
    response = postgres_vpc_client.post(
        "/vpcs",
        json=vpc_payload(cidr_block=cidr_block),
    )
    assert response.status_code == 422


def test_vpc_quota_returns_conflict(
    postgres_vpc_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "vpc_limit_per_owner", 1)
    create_vpc(postgres_vpc_client)
    response = postgres_vpc_client.post(
        "/vpcs",
        json=vpc_payload(name="second-vpc", cidr_block="10.41.0.0/16"),
    )
    assert response.status_code == 409
    assert "limite" in response.json()["detail"]


def test_public_cidr_returns_nonblocking_warning(postgres_vpc_client: TestClient) -> None:
    response = postgres_vpc_client.post(
        "/vpcs",
        json=vpc_payload(cidr_block="8.8.8.0/24"),
    )
    assert response.status_code == 201, response.text
    assert response.json()["warnings"]


def test_patch_changes_name_and_rejects_status_field(postgres_vpc_client: TestClient) -> None:
    created = create_vpc(postgres_vpc_client)
    vpc_id = created["id"]

    patch_response = postgres_vpc_client.patch(
        f"/vpcs/{vpc_id}",
        json={"name": "renamed-vpc"},
    )
    assert patch_response.status_code == 200, patch_response.text
    assert patch_response.json()["name"] == "renamed-vpc"

    status_response = postgres_vpc_client.patch(
        f"/vpcs/{vpc_id}",
        json={"status": "ERROR"},
    )
    assert status_response.status_code == 422


def test_delete_soft_deletes_vpc_and_second_delete_is_not_found(
    postgres_vpc_client: TestClient,
) -> None:
    created = create_vpc(postgres_vpc_client)
    vpc_id = created["id"]

    deleted = postgres_vpc_client.delete(f"/vpcs/{vpc_id}")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["status"] == "DELETED"

    second_delete = postgres_vpc_client.delete(f"/vpcs/{vpc_id}")
    assert second_delete.status_code == 404


def test_vpc_transitions_from_pending_to_active(postgres_vpc_client: TestClient) -> None:
    created = create_vpc(postgres_vpc_client)
    assert created["status"] == "PENDING"

    current = postgres_vpc_client.get(f"/vpcs/{created['id']}")
    assert current.status_code == 200, current.text
    assert current.json()["status"] == "ACTIVE"


def test_list_and_get_only_expose_active_owned_vpcs(postgres_vpc_client: TestClient) -> None:
    created = create_vpc(postgres_vpc_client)

    listed = postgres_vpc_client.get("/vpcs")
    assert listed.status_code == 200
    assert [vpc["id"] for vpc in listed.json()] == [created["id"]]

    fetched = postgres_vpc_client.get(f"/vpcs/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == created["id"]
