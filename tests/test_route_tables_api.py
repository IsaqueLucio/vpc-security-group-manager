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
from app.modules.route_table_associations.models import RouteTableAssociation
from app.modules.route_tables.models import RouteTable
from app.modules.routes.models import Route
from app.modules.subnets.models import Subnet
from app.modules.users.models import User, UserRole
from app.modules.vpcs.models import VPC


@pytest.fixture
def postgres_route_table_api(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, dict[str, int], dict[str, dict[str, str]]]]:
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_POSTGRES_INTEGRATION_TESTS=1 to run PostgreSQL integration tests.")
    if make_url(settings.database_url).get_backend_name() != "postgresql":
        pytest.fail("Route Table integration tests require DATABASE_URL to point to PostgreSQL.")

    monkeypatch.setattr(settings, "vpc_provisioning_delay_seconds", 0.01)
    owner_ids: dict[str, int] = {}
    with SessionLocal() as db:
        for label in ("owner", "other"):
            user = User(
                username=f"route-table-{label}-{os.urandom(8).hex()}",
                email=f"route-table-{label}-{os.urandom(8).hex()}@example.com",
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
            table_ids = select(RouteTable.id).where(RouteTable.vpc_id.in_(vpc_ids))
            db.execute(
                delete(RouteTableAssociation).where(
                    RouteTableAssociation.route_table_id.in_(table_ids)
                )
            )
            db.execute(delete(Route).where(Route.route_table_id.in_(table_ids)))
            db.execute(delete(RouteTable).where(RouteTable.vpc_id.in_(vpc_ids)))
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
            "name": f"routes-{cidr.replace('.', '-').replace('/', '-')}",
            "cidr_block": cidr,
            "region": "sa-east-1",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def create_subnet(client: TestClient, vpc_id: str, headers: dict[str, str]) -> str:
    response = client.post(
        f"/vpcs/{vpc_id}/subnets",
        headers=headers,
        json={"name": "public-subnet", "type": "PUBLIC"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def create_route_table(client: TestClient, vpc_id: str, headers: dict[str, str]) -> dict:
    response = client.post(
        f"/vpcs/{vpc_id}/route-tables",
        headers=headers,
        json={"name": "main"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_route_tables_routes_and_gateway_target_validation(
    postgres_route_table_api: tuple[TestClient, dict[str, int], dict[str, dict[str, str]]],
) -> None:
    client, _, headers = postgres_route_table_api
    vpc_id = create_vpc(client, headers["owner"], "10.130.0.0/16")
    other_vpc_id = create_vpc(client, headers["other"], "10.131.0.0/16")
    table = create_route_table(client, vpc_id, headers["owner"])
    other_igw = client.post(
        f"/vpcs/{other_vpc_id}/internet-gateways",
        headers=headers["other"],
    )
    own_igw = client.post(
        f"/vpcs/{vpc_id}/internet-gateways",
        headers=headers["owner"],
    )
    subnet_id = create_subnet(client, vpc_id, headers["owner"])
    nat = client.post(
        f"/subnets/{subnet_id}/nat-gateways",
        headers=headers["owner"],
    )
    assert other_igw.status_code == own_igw.status_code == nat.status_code == 201

    other_target = client.post(
        f"/route-tables/{table['id']}/routes",
        headers=headers["owner"],
        json={
            "destination_cidr": "0.0.0.0/0",
            "target_type": "INTERNET_GATEWAY",
            "target_id": other_igw.json()["id"],
        },
    )
    assert other_target.status_code == 422, other_target.text

    local_with_target = client.post(
        f"/route-tables/{table['id']}/routes",
        headers=headers["owner"],
        json={
            "destination_cidr": "10.130.0.0/16",
            "target_type": "LOCAL",
            "target_id": own_igw.json()["id"],
        },
    )
    missing_gateway_target = client.post(
        f"/route-tables/{table['id']}/routes",
        headers=headers["owner"],
        json={
            "destination_cidr": "0.0.0.0/0",
            "target_type": "INTERNET_GATEWAY",
        },
    )
    assert local_with_target.status_code == missing_gateway_target.status_code == 422

    invalid_cidr = client.post(
        f"/route-tables/{table['id']}/routes",
        headers=headers["owner"],
        json={"destination_cidr": "10.1.2.3/24", "target_type": "LOCAL"},
    )
    assert invalid_cidr.status_code == 422

    local_route = client.post(
        f"/route-tables/{table['id']}/routes",
        headers=headers["owner"],
        json={"destination_cidr": "10.130.0.0/16", "target_type": "LOCAL"},
    )
    igw_route = client.post(
        f"/route-tables/{table['id']}/routes",
        headers=headers["owner"],
        json={
            "destination_cidr": "0.0.0.0/0",
            "target_type": "INTERNET_GATEWAY",
            "target_id": own_igw.json()["id"],
        },
    )
    nat_route = client.post(
        f"/route-tables/{table['id']}/routes",
        headers=headers["owner"],
        json={
            "destination_cidr": "10.200.0.0/16",
            "target_type": "NAT_GATEWAY",
            "target_id": nat.json()["id"],
        },
    )
    assert local_route.status_code == igw_route.status_code == nat_route.status_code == 201
    assert local_route.json()["target_id"] is None
    assert {route["id"] for route in client.get(
        f"/route-tables/{table['id']}/routes",
        headers=headers["owner"],
    ).json()} == {
        local_route.json()["id"],
        igw_route.json()["id"],
        nat_route.json()["id"],
    }
    assert client.get(
        f"/vpcs/{vpc_id}/route-tables",
        headers=headers["owner"],
    ).json()[0]["id"] == table["id"]


def test_route_table_association_rejects_replacement_and_soft_deletes(
    postgres_route_table_api: tuple[TestClient, dict[str, int], dict[str, dict[str, str]]],
) -> None:
    client, _, headers = postgres_route_table_api
    vpc_id = create_vpc(client, headers["owner"], "10.132.0.0/16")
    other_vpc_id = create_vpc(client, headers["owner"], "10.134.0.0/16")
    subnet_id = create_subnet(client, vpc_id, headers["owner"])
    table = create_route_table(client, vpc_id, headers["owner"])
    second_table = create_route_table(client, vpc_id, headers["owner"])
    foreign_table = create_route_table(client, other_vpc_id, headers["owner"])

    cross_vpc = client.post(
        f"/subnets/{subnet_id}/route-table-association",
        headers=headers["owner"],
        json={"route_table_id": foreign_table["id"]},
    )
    assert cross_vpc.status_code == 422, cross_vpc.text

    created = client.post(
        f"/subnets/{subnet_id}/route-table-association",
        headers=headers["owner"],
        json={"route_table_id": table["id"]},
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == ResourceStatus.ACTIVE.value

    conflict = client.post(
        f"/subnets/{subnet_id}/route-table-association",
        headers=headers["owner"],
        json={"route_table_id": second_table["id"]},
    )
    assert conflict.status_code == 409, conflict.text

    deleted = client.delete(
        f"/subnets/{subnet_id}/route-table-association",
        headers=headers["owner"],
    )
    assert deleted.status_code == 200
    assert deleted.json()["status"] == ResourceStatus.DELETED.value
    recreated = client.post(
        f"/subnets/{subnet_id}/route-table-association",
        headers=headers["owner"],
        json={"route_table_id": second_table["id"]},
    )
    assert recreated.status_code == 201, recreated.text


def test_route_tables_enforce_cross_tenant_ownership_and_cascade(
    postgres_route_table_api: tuple[TestClient, dict[str, int], dict[str, dict[str, str]]],
) -> None:
    client, _, headers = postgres_route_table_api
    vpc_id = create_vpc(client, headers["owner"], "10.133.0.0/16")
    subnet_id = create_subnet(client, vpc_id, headers["owner"])
    table = create_route_table(client, vpc_id, headers["owner"])
    route = client.post(
        f"/route-tables/{table['id']}/routes",
        headers=headers["owner"],
        json={"destination_cidr": "10.133.0.0/16", "target_type": "LOCAL"},
    )
    association = client.post(
        f"/subnets/{subnet_id}/route-table-association",
        headers=headers["owner"],
        json={"route_table_id": table["id"]},
    )
    assert route.status_code == association.status_code == 201

    assert client.get(
        f"/route-tables/{table['id']}",
        headers=headers["other"],
    ).status_code == 404
    assert client.delete(
        f"/route-tables/{table['id']}",
        headers=headers["other"],
    ).status_code == 404
    assert client.delete(
        f"/routes/{route.json()['id']}",
        headers=headers["other"],
    ).status_code == 404

    deleted = client.delete(f"/vpcs/{vpc_id}", headers=headers["owner"])
    assert deleted.status_code == 200
    with SessionLocal() as db:
        assert db.get(RouteTable, UUID(table["id"])).status == ResourceStatus.DELETED
        assert db.get(Route, UUID(route.json()["id"])).status == ResourceStatus.DELETED
        assert (
            db.get(RouteTableAssociation, UUID(association.json()["id"])).status
            == ResourceStatus.DELETED
        )
