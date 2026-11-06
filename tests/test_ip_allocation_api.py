import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from ipaddress import IPv4Address
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.database.session import SessionLocal, get_db
from app.domain.enums import ResourceStatus
from app.main import app
from app.modules.ip_allocations.models import IPAllocation
from app.modules.subnets.models import Subnet
from app.modules.users.models import User, UserRole
from app.modules.vpcs.models import VPC
from app.modules.vpcs.router import get_vpc_owner_id


@pytest.fixture
def postgres_ip_allocation_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_POSTGRES_INTEGRATION_TESTS=1 to run PostgreSQL integration tests.")
    if make_url(settings.database_url).get_backend_name() != "postgresql":
        pytest.fail("IP allocation integration tests require DATABASE_URL to point to PostgreSQL.")

    monkeypatch.setattr(settings, "vpc_provisioning_delay_seconds", 0.01)
    with SessionLocal() as db:
        user = User(
            username=f"ip-allocation-test-{os.urandom(8).hex()}",
            email=f"ip-allocation-test-{os.urandom(8).hex()}@example.com",
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
            "name": "ip-allocation-test-vpc",
            "cidr_block": "10.90.0.0/16",
            "region": "us-east-1",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def create_subnet(
    client: TestClient,
    vpc_id: str,
    *,
    cidr_block: str = "10.90.0.0/24",
) -> dict:
    response = client.post(
        f"/vpcs/{vpc_id}/subnets",
        json={"name": "ip-allocation-test-subnet", "type": "PRIVATE", "cidr_block": cidr_block},
    )
    assert response.status_code == 201, response.text
    return response.json()


def allocate(client: TestClient, subnet_id: str, payload: dict | None = None):
    return client.post(
        f"/subnets/{subnet_id}/ip-allocations",
        json=payload or {},
    )


def test_manual_and_automatic_ip_allocation(postgres_ip_allocation_client: TestClient) -> None:
    vpc_id = create_vpc(postgres_ip_allocation_client)
    subnet = create_subnet(postgres_ip_allocation_client, vpc_id)

    manual = allocate(postgres_ip_allocation_client, subnet["id"], {"ip_address": "10.90.0.10"})
    assert manual.status_code == 201, manual.text
    assert manual.json()["ip_address"] == "10.90.0.10"

    automatic = allocate(postgres_ip_allocation_client, subnet["id"])
    assert automatic.status_code == 201, automatic.text
    assert automatic.json()["ip_address"] == "10.90.0.4"

    listed = postgres_ip_allocation_client.get(
        f"/subnets/{subnet['id']}/ip-allocations"
    )
    assert listed.status_code == 200
    assert {item["ip_address"] for item in listed.json()} == {"10.90.0.4", "10.90.0.10"}


@pytest.mark.parametrize(
    "ip_address",
    ["10.90.0.0", "10.90.0.1", "10.90.0.2", "10.90.0.3", "10.90.0.255"],
)
def test_reserved_addresses_are_rejected(
    postgres_ip_allocation_client: TestClient,
    ip_address: str,
) -> None:
    vpc_id = create_vpc(postgres_ip_allocation_client)
    subnet = create_subnet(postgres_ip_allocation_client, vpc_id)

    response = allocate(postgres_ip_allocation_client, subnet["id"], {"ip_address": ip_address})

    assert response.status_code == 422


def test_error_subnet_rejects_ip_allocation(
    postgres_ip_allocation_client: TestClient,
) -> None:
    vpc_id = create_vpc(postgres_ip_allocation_client)
    subnet = create_subnet(postgres_ip_allocation_client, vpc_id)
    with SessionLocal() as db:
        stored_subnet = db.get(Subnet, UUID(subnet["id"]))
        assert stored_subnet is not None
        stored_subnet.status = ResourceStatus.ERROR
        db.commit()

    response = allocate(postgres_ip_allocation_client, subnet["id"])
    assert response.status_code == 409


def test_address_outside_subnet_and_duplicate_active_address_are_rejected(
    postgres_ip_allocation_client: TestClient,
) -> None:
    vpc_id = create_vpc(postgres_ip_allocation_client)
    subnet = create_subnet(postgres_ip_allocation_client, vpc_id)
    first = allocate(
        postgres_ip_allocation_client,
        subnet["id"],
        {"ip_address": "10.90.0.20"},
    )
    assert first.status_code == 201, first.text

    duplicate = allocate(
        postgres_ip_allocation_client,
        subnet["id"],
        {"ip_address": "10.90.0.20"},
    )
    outside = allocate(
        postgres_ip_allocation_client,
        subnet["id"],
        {"ip_address": "10.90.1.20"},
    )

    assert duplicate.status_code == 409, duplicate.text
    assert outside.status_code == 422, outside.text


def test_delete_releases_address_for_reuse(postgres_ip_allocation_client: TestClient) -> None:
    vpc_id = create_vpc(postgres_ip_allocation_client)
    subnet = create_subnet(postgres_ip_allocation_client, vpc_id)
    allocated = allocate(
        postgres_ip_allocation_client,
        subnet["id"],
        {"ip_address": "10.90.0.20"},
    )
    allocation_id = allocated.json()["id"]

    fetched = postgres_ip_allocation_client.get(f"/ip-allocations/{allocation_id}")
    assert fetched.status_code == 200
    deleted = postgres_ip_allocation_client.delete(f"/ip-allocations/{allocation_id}")
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "DELETED"
    assert postgres_ip_allocation_client.get(f"/ip-allocations/{allocation_id}").status_code == 404

    reused = allocate(
        postgres_ip_allocation_client,
        subnet["id"],
        {"ip_address": "10.90.0.20"},
    )
    assert reused.status_code == 201, reused.text
    assert reused.json()["id"] != allocation_id


def test_ip_space_exhaustion_returns_conflict(postgres_ip_allocation_client: TestClient) -> None:
    vpc_id = create_vpc(postgres_ip_allocation_client)
    subnet = create_subnet(
        postgres_ip_allocation_client,
        vpc_id,
        cidr_block="10.90.0.0/28",
    )

    results = [
        allocate(postgres_ip_allocation_client, subnet["id"])
        for _ in range(11)
    ]
    exhausted = allocate(postgres_ip_allocation_client, subnet["id"])

    assert all(response.status_code == 201 for response in results)
    assert {response.json()["ip_address"] for response in results} == {
        f"10.90.0.{host}" for host in range(4, 15)
    }
    assert exhausted.status_code == 409
    assert "disponíveis" in exhausted.json()["detail"]


def test_concurrent_allocations_get_distinct_addresses(
    postgres_ip_allocation_client: TestClient,
) -> None:
    vpc_id = create_vpc(postgres_ip_allocation_client)
    subnet = create_subnet(postgres_ip_allocation_client, vpc_id)

    def allocate_concurrently(_: int):
        with TestClient(app) as client:
            return allocate(client, subnet["id"])

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(allocate_concurrently, range(2)))

    assert all(response.status_code == 201 for response in responses), [
        (response.status_code, response.text) for response in responses
    ]
    addresses = {response.json()["ip_address"] for response in responses}
    assert addresses == {"10.90.0.4", "10.90.0.5"}
    with SessionLocal() as db:
        persisted = db.scalars(
            select(IPAllocation).where(
                IPAllocation.subnet_id == UUID(subnet["id"]),
                IPAllocation.status != ResourceStatus.DELETED,
            )
        ).all()
    assert len(persisted) == 2
    assert len({IPv4Address(str(allocation.ip_address)) for allocation in persisted}) == 2


def test_subnet_lock_timeout_returns_503_and_retry_after(
    postgres_ip_allocation_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vpc_id = create_vpc(postgres_ip_allocation_client)
    subnet = create_subnet(postgres_ip_allocation_client, vpc_id)
    monkeypatch.setattr(settings, "database_lock_timeout_ms", 100)

    with SessionLocal() as blocker:
        blocker.execute(
            select(Subnet).where(Subnet.id == UUID(subnet["id"])).with_for_update()
        )
        response = allocate(postgres_ip_allocation_client, subnet["id"])

    assert response.status_code == 503
    assert response.headers["retry-after"] == "1"


def test_subnet_and_vpc_deletions_cascade_to_allocations(
    postgres_ip_allocation_client: TestClient,
) -> None:
    vpc_id = create_vpc(postgres_ip_allocation_client)
    first_subnet = create_subnet(postgres_ip_allocation_client, vpc_id)
    first_allocation = allocate(postgres_ip_allocation_client, first_subnet["id"])
    second_subnet_response = postgres_ip_allocation_client.post(
        f"/vpcs/{vpc_id}/subnets",
        json={
            "name": "second-ip-allocation-subnet",
            "type": "PRIVATE",
            "cidr_block": "10.90.1.0/24",
        },
    )
    assert second_subnet_response.status_code == 201, second_subnet_response.text
    second_subnet = second_subnet_response.json()
    second_allocation = allocate(postgres_ip_allocation_client, second_subnet["id"])
    assert first_allocation.status_code == second_allocation.status_code == 201

    deleted_subnet = postgres_ip_allocation_client.delete(f"/subnets/{first_subnet['id']}")
    assert deleted_subnet.status_code == 200
    rejected = allocate(postgres_ip_allocation_client, first_subnet["id"])
    assert rejected.status_code == 409
    with SessionLocal() as db:
        first_status = db.get(IPAllocation, UUID(first_allocation.json()["id"])).status
    assert first_status == ResourceStatus.DELETED

    deleted_vpc = postgres_ip_allocation_client.delete(f"/vpcs/{vpc_id}")
    assert deleted_vpc.status_code == 200
    with SessionLocal() as db:
        second_status = db.get(IPAllocation, UUID(second_allocation.json()["id"])).status
        subnet_status = db.get(Subnet, UUID(second_subnet["id"])).status
    assert second_status == ResourceStatus.DELETED
    assert subnet_status == ResourceStatus.DELETED
