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
from app.domain.enums import ResourceStatus
from app.main import app
from app.modules.internet_gateways.models import InternetGateway
from app.modules.nat_gateways.models import NatGateway
from app.modules.subnets.models import Subnet
from app.modules.users.models import User, UserRole
from app.modules.vpcs.models import VPC


@pytest.fixture
def postgres_gateway_api(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, dict[str, int], dict[str, dict[str, str]]]]:
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_POSTGRES_INTEGRATION_TESTS=1 to run PostgreSQL integration tests.")
    if make_url(settings.database_url).get_backend_name() != "postgresql":
        pytest.fail("Gateway API integration tests require DATABASE_URL to point to PostgreSQL.")

    monkeypatch.setattr(settings, "vpc_provisioning_delay_seconds", 0.01)
    owner_ids: dict[str, int] = {}
    with SessionLocal() as db:
        for label in ("owner", "other"):
            user = User(
                username=f"gateway-{label}-{os.urandom(8).hex()}",
                email=f"gateway-{label}-{os.urandom(8).hex()}@example.com",
                hashed_password="integration-test-only",
                role=UserRole.USER,
            )
            db.add(user)
            db.flush()
            owner_ids[label] = user.id
        db.commit()

    auth_headers = {
        label: {
            "Authorization": "Bearer "
            + create_access_token(data={"sub": str(user_id), "role": "user"})
        }
        for label, user_id in owner_ids.items()
    }

    def override_get_db():
        with SessionLocal() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client, owner_ids, auth_headers
    finally:
        app.dependency_overrides.clear()
        with SessionLocal() as db:
            vpc_ids = select(VPC.id).where(VPC.owner_id.in_(owner_ids.values()))
            subnet_ids = select(Subnet.id).where(Subnet.vpc_id.in_(vpc_ids))
            db.execute(delete(NatGateway).where(NatGateway.subnet_id.in_(subnet_ids)))
            db.execute(delete(InternetGateway).where(InternetGateway.vpc_id.in_(vpc_ids)))
            db.execute(delete(Subnet).where(Subnet.vpc_id.in_(vpc_ids)))
            db.execute(delete(VPC).where(VPC.owner_id.in_(owner_ids.values())))
            db.execute(delete(User).where(User.id.in_(owner_ids.values())))
            db.commit()


def create_vpc(client: TestClient, headers: dict[str, str], cidr: str) -> str:
    response = client.post(
        "/vpcs",
        headers=headers,
        json={
            "name": f"gateway-{cidr.replace('.', '-').replace('/', '-')}",
            "cidr_block": cidr,
            "region": "sa-east-1",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def create_subnet(
    client: TestClient,
    vpc_id: str,
    headers: dict[str, str],
    subnet_type: str,
) -> str:
    response = client.post(
        f"/vpcs/{vpc_id}/subnets",
        headers=headers,
        json={"name": f"{subnet_type.lower()}-subnet", "type": subnet_type},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_internet_gateway_unique_active_and_soft_delete(
    postgres_gateway_api: tuple[TestClient, dict[str, int], dict[str, dict[str, str]]],
) -> None:
    client, _, headers = postgres_gateway_api
    vpc_id = create_vpc(client, headers["owner"], "10.120.0.0/16")

    created = client.post(f"/vpcs/{vpc_id}/internet-gateways", headers=headers["owner"])
    assert created.status_code == 201, created.text
    gateway_id = created.json()["id"]
    assert created.json()["status"] == ResourceStatus.ACTIVE.value

    listed = client.get(f"/vpcs/{vpc_id}/internet-gateways", headers=headers["owner"])
    assert listed.status_code == 200
    assert [gateway["id"] for gateway in listed.json()] == [gateway_id]

    duplicate = client.post(
        f"/vpcs/{vpc_id}/internet-gateways",
        headers=headers["owner"],
    )
    assert duplicate.status_code == 409, duplicate.text

    deleted = client.delete(f"/internet-gateways/{gateway_id}", headers=headers["owner"])
    assert deleted.status_code == 200
    assert deleted.json()["status"] == ResourceStatus.DELETED.value
    assert client.get(
        f"/vpcs/{vpc_id}/internet-gateways",
        headers=headers["owner"],
    ).json() == []

    recreated = client.post(
        f"/vpcs/{vpc_id}/internet-gateways",
        headers=headers["owner"],
    )
    assert recreated.status_code == 201, recreated.text


def test_nat_gateway_requires_public_subnet_and_can_be_soft_deleted(
    postgres_gateway_api: tuple[TestClient, dict[str, int], dict[str, dict[str, str]]],
) -> None:
    client, _, headers = postgres_gateway_api
    vpc_id = create_vpc(client, headers["owner"], "10.121.0.0/16")
    public_subnet_id = create_subnet(client, vpc_id, headers["owner"], "PUBLIC")
    private_subnet_id = create_subnet(client, vpc_id, headers["owner"], "PRIVATE")

    created = client.post(
        f"/subnets/{public_subnet_id}/nat-gateways",
        headers=headers["owner"],
    )
    assert created.status_code == 201, created.text
    assert created.json()["subnet_id"] == public_subnet_id

    listed = client.get(
        f"/subnets/{public_subnet_id}/nat-gateways",
        headers=headers["owner"],
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    private_rejected = client.post(
        f"/subnets/{private_subnet_id}/nat-gateways",
        headers=headers["owner"],
    )
    assert private_rejected.status_code == 422

    deleted = client.delete(
        f"/nat-gateways/{created.json()['id']}",
        headers=headers["owner"],
    )
    assert deleted.status_code == 200
    assert deleted.json()["status"] == ResourceStatus.DELETED.value
    assert client.get(
        f"/subnets/{public_subnet_id}/nat-gateways",
        headers=headers["owner"],
    ).json() == []


def test_gateways_hide_resources_from_other_tenants(
    postgres_gateway_api: tuple[TestClient, dict[str, int], dict[str, dict[str, str]]],
) -> None:
    client, _, headers = postgres_gateway_api
    vpc_id = create_vpc(client, headers["owner"], "10.122.0.0/16")
    subnet_id = create_subnet(client, vpc_id, headers["owner"], "PUBLIC")
    igw = client.post(
        f"/vpcs/{vpc_id}/internet-gateways",
        headers=headers["owner"],
    )
    nat = client.post(
        f"/subnets/{subnet_id}/nat-gateways",
        headers=headers["owner"],
    )
    assert igw.status_code == nat.status_code == 201

    other_vpc_list = client.get(
        f"/vpcs/{vpc_id}/internet-gateways",
        headers=headers["other"],
    )
    other_igw_create = client.post(
        f"/vpcs/{vpc_id}/internet-gateways",
        headers=headers["other"],
    )
    other_igw_delete = client.delete(
        f"/internet-gateways/{igw.json()['id']}",
        headers=headers["other"],
    )
    assert other_vpc_list.status_code == 404
    assert other_igw_create.status_code == 404
    assert other_igw_delete.status_code == 404

    other_nat_list = client.get(
        f"/subnets/{subnet_id}/nat-gateways",
        headers=headers["other"],
    )
    other_nat_create = client.post(
        f"/subnets/{subnet_id}/nat-gateways",
        headers=headers["other"],
    )
    other_nat_delete = client.delete(
        f"/nat-gateways/{nat.json()['id']}",
        headers=headers["other"],
    )
    assert other_nat_list.status_code == 404
    assert other_nat_create.status_code == 404
    assert other_nat_delete.status_code == 404


def test_vpc_and_subnet_soft_delete_cascade_to_gateway_resources(
    postgres_gateway_api: tuple[TestClient, dict[str, int], dict[str, dict[str, str]]],
) -> None:
    client, _, headers = postgres_gateway_api
    vpc_id = create_vpc(client, headers["owner"], "10.123.0.0/16")
    subnet_id = create_subnet(client, vpc_id, headers["owner"], "PUBLIC")
    igw = client.post(
        f"/vpcs/{vpc_id}/internet-gateways",
        headers=headers["owner"],
    )
    nat = client.post(
        f"/subnets/{subnet_id}/nat-gateways",
        headers=headers["owner"],
    )
    assert igw.status_code == nat.status_code == 201

    deleted_subnet = client.delete(f"/subnets/{subnet_id}", headers=headers["owner"])
    assert deleted_subnet.status_code == 200
    with SessionLocal() as db:
        stored_nat = db.get(NatGateway, UUID(nat.json()["id"]))
        assert stored_nat is not None
        assert stored_nat.status == ResourceStatus.DELETED

    deleted_vpc = client.delete(f"/vpcs/{vpc_id}", headers=headers["owner"])
    assert deleted_vpc.status_code == 200
    with SessionLocal() as db:
        stored_igw = db.get(InternetGateway, UUID(igw.json()["id"]))
        assert stored_igw is not None
        assert stored_igw.status == ResourceStatus.DELETED
