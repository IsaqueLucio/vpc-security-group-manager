import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.database.session import SessionLocal, get_db
from app.main import app
from app.modules.users.models import User, UserRole
from app.modules.ip_allocations.models import IPAllocation
from app.modules.subnets.models import Subnet
from app.modules.vpcs.models import VPC
from app.modules.vpcs.router import get_vpc_owner_id
from app.domain.enums import ResourceStatus


@pytest.fixture
def postgres_subnet_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_POSTGRES_INTEGRATION_TESTS=1 to run PostgreSQL integration tests.")
    if make_url(settings.database_url).get_backend_name() != "postgresql":
        pytest.fail("Subnet integration tests require DATABASE_URL to point to PostgreSQL.")

    monkeypatch.setattr(settings, "vpc_provisioning_delay_seconds", 0.01)
    with SessionLocal() as db:
        user = User(
            username=f"subnet-test-{os.urandom(8).hex()}",
            email=f"subnet-test-{os.urandom(8).hex()}@example.com",
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
            db.execute(
                delete(IPAllocation).where(
                    IPAllocation.subnet_id.in_(
                        select(Subnet.id).where(
                            Subnet.vpc_id.in_(select(VPC.id).where(VPC.owner_id == owner_id))
                        )
                    )
                )
            )
            db.execute(
                delete(Subnet).where(
                    Subnet.vpc_id.in_(select(VPC.id).where(VPC.owner_id == owner_id))
                )
            )
            db.execute(delete(VPC).where(VPC.owner_id == owner_id))
            db.execute(delete(User).where(User.id == owner_id))
            db.commit()


def create_vpc(client: TestClient) -> str:
    response = client.post(
        "/vpcs",
        json={
            "name": "subnet-test-vpc",
            "cidr_block": "10.80.0.0/16",
            "region": "us-east-1",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def create_subnet(
    client: TestClient,
    vpc_id: str,
    *,
    name: str = "test-subnet",
    cidr_block: str | None = None,
    prefix_length: int | None = None,
    subnet_type: str = "PRIVATE",
) -> dict:
    payload: dict[str, str | int] = {"name": name, "type": subnet_type}
    if cidr_block is not None:
        payload["cidr_block"] = cidr_block
    if prefix_length is not None:
        payload["prefix_length"] = prefix_length
    response = client.post(f"/vpcs/{vpc_id}/subnets", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_automatic_subnet_defaults_to_first_fit_24(postgres_subnet_client: TestClient) -> None:
    vpc_id = create_vpc(postgres_subnet_client)
    subnet = create_subnet(postgres_subnet_client, vpc_id)
    assert subnet["cidr_block"] == "10.80.0.0/24"
    assert subnet["status"] == "PENDING"


def test_manual_subnet_must_be_contained_by_vpc(postgres_subnet_client: TestClient) -> None:
    vpc_id = create_vpc(postgres_subnet_client)
    response = postgres_subnet_client.post(
        f"/vpcs/{vpc_id}/subnets",
        json={"name": "outside", "type": "PRIVATE", "cidr_block": "10.81.0.0/24"},
    )
    assert response.status_code == 422


def test_subnet_overlap_returns_conflict(postgres_subnet_client: TestClient) -> None:
    vpc_id = create_vpc(postgres_subnet_client)
    create_subnet(postgres_subnet_client, vpc_id, cidr_block="10.80.0.0/24")
    response = postgres_subnet_client.post(
        f"/vpcs/{vpc_id}/subnets",
        json={"name": "overlap", "type": "PUBLIC", "cidr_block": "10.80.0.128/25"},
    )
    assert response.status_code == 409


def test_duplicate_subnet_name_returns_conflict(postgres_subnet_client: TestClient) -> None:
    vpc_id = create_vpc(postgres_subnet_client)
    create_subnet(postgres_subnet_client, vpc_id, name="same-name")
    response = postgres_subnet_client.post(
        f"/vpcs/{vpc_id}/subnets",
        json={"name": "same-name", "type": "PUBLIC", "cidr_block": "10.80.1.0/24"},
    )
    assert response.status_code == 409


def test_invalid_prefix_and_missing_type_are_rejected(postgres_subnet_client: TestClient) -> None:
    vpc_id = create_vpc(postgres_subnet_client)
    prefix_response = postgres_subnet_client.post(
        f"/vpcs/{vpc_id}/subnets",
        json={"name": "bad-prefix", "type": "PRIVATE", "prefix_length": 29},
    )
    assert prefix_response.status_code == 422

    type_response = postgres_subnet_client.post(
        f"/vpcs/{vpc_id}/subnets",
        json={"name": "missing-type", "cidr_block": "10.80.1.0/24"},
    )
    assert type_response.status_code == 422


@pytest.mark.parametrize(
    ("cidr", "total", "usable"),
    [
        ("10.80.0.0/24", 256, 251),
        ("10.80.0.0/28", 16, 11),
    ],
)
def test_subnet_response_includes_ip_capacity_metrics(
    postgres_subnet_client: TestClient,
    cidr: str,
    total: int,
    usable: int,
) -> None:
    vpc_id = create_vpc(postgres_subnet_client)
    subnet = create_subnet(postgres_subnet_client, vpc_id, cidr_block=cidr)
    assert subnet["total_ips"] == total
    assert subnet["usable_ips"] == usable
    assert subnet["available_ips"] == usable


def test_available_ip_metric_subtracts_active_allocations(
    postgres_subnet_client: TestClient,
) -> None:
    vpc_id = create_vpc(postgres_subnet_client)
    subnet = create_subnet(postgres_subnet_client, vpc_id, cidr_block="10.80.0.0/24")
    with SessionLocal() as db:
        db.add(
            IPAllocation(
                subnet_id=UUID(subnet["id"]),
                ip_address="10.80.0.4",
                status=ResourceStatus.ACTIVE,
            )
        )
        db.commit()

    response = postgres_subnet_client.get(f"/subnets/{subnet['id']}")
    assert response.status_code == 200
    assert response.json()["available_ips"] == 250


def test_direct_subnet_get_patch_delete_endpoints(postgres_subnet_client: TestClient) -> None:
    vpc_id = create_vpc(postgres_subnet_client)
    subnet = create_subnet(postgres_subnet_client, vpc_id)
    subnet_id = subnet["id"]

    fetched = postgres_subnet_client.get(f"/subnets/{subnet_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == subnet_id

    updated = postgres_subnet_client.patch(
        f"/subnets/{subnet_id}",
        json={"name": "renamed-subnet", "type": "PUBLIC"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "renamed-subnet"
    assert updated.json()["type"] == "PUBLIC"

    deleted = postgres_subnet_client.delete(f"/subnets/{subnet_id}")
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "DELETED"
    assert postgres_subnet_client.get(f"/subnets/{subnet_id}").status_code == 404


def test_pending_vpc_allows_subnet_creation(postgres_subnet_client: TestClient) -> None:
    vpc_id = create_vpc(postgres_subnet_client)
    with SessionLocal() as db:
        db.execute(
            update(VPC)
            .where(VPC.id == UUID(vpc_id))
            .values(status=ResourceStatus.PENDING)
        )
        db.commit()

    subnet = create_subnet(postgres_subnet_client, vpc_id)
    assert subnet["status"] == "PENDING"


def test_deleted_vpc_rejects_subnet_creation(postgres_subnet_client: TestClient) -> None:
    vpc_id = create_vpc(postgres_subnet_client)
    deleted = postgres_subnet_client.delete(f"/vpcs/{vpc_id}")
    assert deleted.status_code == 200

    response = postgres_subnet_client.post(
        f"/vpcs/{vpc_id}/subnets",
        json={"name": "after-delete", "type": "PRIVATE"},
    )
    assert response.status_code == 409


def test_vpc_delete_soft_deletes_subnets_synchronously(postgres_subnet_client: TestClient) -> None:
    vpc_id = create_vpc(postgres_subnet_client)
    subnet = create_subnet(postgres_subnet_client, vpc_id)

    deleted = postgres_subnet_client.delete(f"/vpcs/{vpc_id}")
    assert deleted.status_code == 200

    with SessionLocal() as db:
        stored_subnet = db.get(Subnet, UUID(subnet["id"]))
        assert stored_subnet is not None
        assert stored_subnet.status == ResourceStatus.DELETED


def test_concurrent_first_fit_requests_get_distinct_subnets(
    postgres_subnet_client: TestClient,
) -> None:
    vpc_id = create_vpc(postgres_subnet_client)

    def create_concurrently(index: int):
        with TestClient(app) as client:
            return client.post(
                f"/vpcs/{vpc_id}/subnets",
                json={"name": f"parallel-{index}", "type": "PRIVATE", "prefix_length": 24},
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(create_concurrently, range(2)))

    assert all(response.status_code == 201 for response in responses), [
        (response.status_code, response.text) for response in responses
    ]
    cidrs = {response.json()["cidr_block"] for response in responses}
    assert cidrs == {"10.80.0.0/24", "10.80.1.0/24"}


def test_parent_lock_timeout_returns_503_and_retry_after(
    postgres_subnet_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vpc_id = create_vpc(postgres_subnet_client)
    monkeypatch.setattr(settings, "database_lock_timeout_ms", 100)

    with SessionLocal() as blocker:
        blocker.execute(select(VPC).where(VPC.id == UUID(vpc_id)).with_for_update())
        response = postgres_subnet_client.post(
            f"/vpcs/{vpc_id}/subnets",
            json={"name": "lock-timeout", "type": "PRIVATE"},
        )

    assert response.status_code == 503
    assert response.headers["retry-after"] == "1"


def test_exclusion_constraint_rejects_overlap_without_parent_lock(
    postgres_subnet_client: TestClient,
) -> None:
    vpc_id = create_vpc(postgres_subnet_client)
    barrier = Barrier(2)

    def insert_without_lock(index: int) -> str:
        with SessionLocal() as db:
            db.add(
                Subnet(
                    vpc_id=UUID(vpc_id),
                    name=f"without-lock-{index}",
                    cidr_block="10.80.10.0/24",
                    type="PRIVATE",
                    status=ResourceStatus.ACTIVE,
                )
            )
            barrier.wait(timeout=10)
            try:
                db.commit()
                return "committed"
            except IntegrityError as exc:
                db.rollback()
                return getattr(exc.orig, "sqlstate", "unknown")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(insert_without_lock, range(2)))

    assert results.count("committed") == 1
    assert results.count("23P01") == 1
    with SessionLocal() as db:
        persisted = db.scalars(
            select(Subnet).where(Subnet.vpc_id == UUID(vpc_id), Subnet.cidr_block == "10.80.10.0/24")
        ).all()
        assert len(persisted) == 1
