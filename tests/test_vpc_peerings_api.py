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
from app.modules.users.models import User, UserRole
from app.modules.vpc_peerings.enums import VpcPeeringStatus
from app.modules.vpc_peerings.models import VpcPeering
from app.modules.vpcs.models import VPC


@pytest.fixture
def postgres_vpc_peering_api(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, dict[str, int], dict[str, dict[str, str]]]]:
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_POSTGRES_INTEGRATION_TESTS=1 to run PostgreSQL integration tests.")
    if make_url(settings.database_url).get_backend_name() != "postgresql":
        pytest.fail("VPC Peering integration tests require DATABASE_URL to point to PostgreSQL.")

    monkeypatch.setattr(settings, "vpc_provisioning_delay_seconds", 0.01)
    owner_ids: dict[str, int] = {}
    with SessionLocal() as db:
        for label in ("requester", "accepter", "outsider", "admin"):
            user = User(
                username=f"peering-{label}-{os.urandom(8).hex()}",
                email=f"peering-{label}-{os.urandom(8).hex()}@example.com",
                hashed_password="integration-test-only",
                role=UserRole.ADMIN if label == "admin" else UserRole.USER,
            )
            db.add(user)
            db.flush()
            owner_ids[label] = user.id
        db.commit()

    auth_headers = {
        label: {
            "Authorization": "Bearer "
            + create_access_token(
                data={
                    "sub": str(user_id),
                    "role": "admin" if label == "admin" else "user",
                }
            )
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
            db.execute(
                delete(VpcPeering).where(
                    VpcPeering.requester_vpc_id.in_(vpc_ids)
                    | VpcPeering.accepter_vpc_id.in_(vpc_ids)
                )
            )
            db.execute(delete(VPC).where(VPC.owner_id.in_(owner_ids.values())))
            db.execute(delete(User).where(User.id.in_(owner_ids.values())))
            db.commit()


def create_vpc(client: TestClient, headers: dict[str, str], cidr: str) -> str:
    response = client.post(
        "/vpcs",
        headers=headers,
        json={
            "name": f"peering-{cidr.replace('.', '-').replace('/', '-')}",
            "cidr_block": cidr,
            "region": "sa-east-1",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def create_peering(
    client: TestClient,
    requester_id: str,
    accepter_id: str,
    headers: dict[str, str],
):
    return client.post(
        "/vpc-peerings",
        headers=headers,
        json={
            "requester_vpc_id": requester_id,
            "accepter_vpc_id": accepter_id,
        },
    )


def test_create_peering_validates_overlap_and_normalized_duplicate_pair(
    postgres_vpc_peering_api: tuple[TestClient, dict[str, int], dict[str, dict[str, str]]],
) -> None:
    client, _, headers = postgres_vpc_peering_api
    requester_id = create_vpc(client, headers["requester"], "10.140.0.0/16")
    accepter_id = create_vpc(client, headers["accepter"], "10.141.0.0/16")

    created = create_peering(client, requester_id, accepter_id, headers["requester"])
    assert created.status_code == 201, created.text
    assert created.json()["status"] == VpcPeeringStatus.PENDING_ACCEPTANCE.value

    duplicate_reversed = create_peering(
        client,
        accepter_id,
        requester_id,
        headers["accepter"],
    )
    assert duplicate_reversed.status_code == 409, duplicate_reversed.text

    assert [
        peering["id"]
        for peering in client.get(
            "/vpc-peerings",
            headers=headers["requester"],
        ).json()
    ] == [created.json()["id"]]
    assert [
        peering["id"]
        for peering in client.get(
            "/vpc-peerings",
            headers=headers["accepter"],
        ).json()
    ] == [created.json()["id"]]
    assert client.get(
        "/vpc-peerings",
        headers=headers["outsider"],
    ).json() == []


def test_peering_acceptance_requires_accepter_owner_and_admin_can_accept(
    postgres_vpc_peering_api: tuple[TestClient, dict[str, int], dict[str, dict[str, str]]],
) -> None:
    client, _, headers = postgres_vpc_peering_api
    requester_id = create_vpc(client, headers["requester"], "10.142.0.0/16")
    accepter_id = create_vpc(client, headers["accepter"], "10.143.0.0/16")
    created = create_peering(client, requester_id, accepter_id, headers["requester"])
    assert created.status_code == 201, created.text
    peering_id = created.json()["id"]

    requester_accept = client.patch(
        f"/vpc-peerings/{peering_id}",
        headers=headers["requester"],
        json={"status": "ACTIVE"},
    )
    assert requester_accept.status_code == 403

    outsider_accept = client.patch(
        f"/vpc-peerings/{peering_id}",
        headers=headers["outsider"],
        json={"status": "ACTIVE"},
    )
    assert outsider_accept.status_code == 404

    admin_accept = client.patch(
        f"/vpc-peerings/{peering_id}",
        headers=headers["admin"],
        json={"status": "ACTIVE"},
    )
    assert admin_accept.status_code == 200, admin_accept.text
    assert admin_accept.json()["status"] == VpcPeeringStatus.ACTIVE.value


def test_peering_rejection_and_requester_cancellation(
    postgres_vpc_peering_api: tuple[TestClient, dict[str, int], dict[str, dict[str, str]]],
) -> None:
    client, _, headers = postgres_vpc_peering_api
    requester_id = create_vpc(client, headers["requester"], "10.144.0.0/16")
    accepter_id = create_vpc(client, headers["accepter"], "10.145.0.0/16")
    rejected = create_peering(client, requester_id, accepter_id, headers["requester"])
    assert rejected.status_code == 201, rejected.text

    rejection = client.patch(
        f"/vpc-peerings/{rejected.json()['id']}",
        headers=headers["accepter"],
        json={"status": "REJECTED"},
    )
    assert rejection.status_code == 200, rejection.text
    assert rejection.json()["status"] == VpcPeeringStatus.REJECTED.value

    # REJECTED pairs are excluded from the unique active pair constraint.
    retry = create_peering(client, requester_id, accepter_id, headers["requester"])
    assert retry.status_code == 201, retry.text
    cancellation = client.delete(
        f"/vpc-peerings/{retry.json()['id']}",
        headers=headers["requester"],
    )
    assert cancellation.status_code == 200
    assert cancellation.json()["status"] == VpcPeeringStatus.DELETED.value
    assert client.get("/vpc-peerings", headers=headers["requester"]).json() == [
        rejection.json()
    ]
    assert client.delete(
        f"/vpcs/{requester_id}",
        headers=headers["requester"],
    ).status_code == 200
    with SessionLocal() as db:
        assert (
            db.get(VpcPeering, UUID(rejected.json()["id"])).status
            == VpcPeeringStatus.DELETED
        )


def test_peering_rejects_overlapping_cidrs_and_invalid_transitions(
    postgres_vpc_peering_api: tuple[TestClient, dict[str, int], dict[str, dict[str, str]]],
) -> None:
    client, _, headers = postgres_vpc_peering_api
    requester_id = create_vpc(client, headers["requester"], "10.146.0.0/16")
    accepter_id = create_vpc(client, headers["accepter"], "10.146.0.0/17")

    overlap = create_peering(client, requester_id, accepter_id, headers["requester"])
    assert overlap.status_code == 409, overlap.text
    self_peering = create_peering(
        client,
        requester_id,
        requester_id,
        headers["requester"],
    )
    assert self_peering.status_code == 422

    non_overlapping_requester = create_vpc(
        client,
        headers["requester"],
        "10.147.0.0/16",
    )
    pending = create_peering(
        client,
        non_overlapping_requester,
        accepter_id,
        headers["requester"],
    )
    assert pending.status_code == 201, pending.text
    invalid_status = client.patch(
        f"/vpc-peerings/{pending.json()['id']}",
        headers=headers["accepter"],
        json={"status": "DELETED"},
    )
    assert invalid_status.status_code == 422
    canceled_by_accepter = client.delete(
        f"/vpc-peerings/{pending.json()['id']}",
        headers=headers["accepter"],
    )
    assert canceled_by_accepter.status_code == 403

    with SessionLocal() as db:
        assert db.get(VPC, UUID(requester_id)) is not None
