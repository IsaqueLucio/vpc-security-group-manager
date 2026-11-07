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
from app.modules.security_group_rules.enums import (
    SecurityGroupRuleDirection,
    SecurityGroupRuleProtocol,
)
from app.modules.security_group_rules.models import SecurityGroupRule
from app.modules.security_groups.models import SecurityGroup
from app.modules.users.models import User, UserRole
from app.modules.vpcs.models import VPC


@pytest.fixture
def postgres_security_group_api(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, dict[str, int], dict[str, dict[str, str]]]]:
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_POSTGRES_INTEGRATION_TESTS=1 to run PostgreSQL integration tests.")
    if make_url(settings.database_url).get_backend_name() != "postgresql":
        pytest.fail(
            "Security Group integration tests require DATABASE_URL to point to PostgreSQL."
        )

    monkeypatch.setattr(settings, "vpc_provisioning_delay_seconds", 0.01)
    owner_ids: dict[str, int] = {}
    with SessionLocal() as db:
        for label in ("owner", "other", "admin"):
            user = User(
                username=f"security-group-{label}-{os.urandom(8).hex()}",
                email=f"security-group-{label}-{os.urandom(8).hex()}@example.com",
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
            group_ids = select(SecurityGroup.id).where(SecurityGroup.vpc_id.in_(vpc_ids))
            db.execute(
                delete(SecurityGroupRule).where(
                    SecurityGroupRule.security_group_id.in_(group_ids)
                )
            )
            db.execute(delete(SecurityGroup).where(SecurityGroup.vpc_id.in_(vpc_ids)))
            db.execute(delete(VPC).where(VPC.owner_id.in_(owner_ids.values())))
            db.execute(delete(User).where(User.id.in_(owner_ids.values())))
            db.commit()


def create_vpc(client: TestClient, headers: dict[str, str], cidr: str) -> str:
    response = client.post(
        "/vpcs",
        headers=headers,
        json={
            "name": f"security-group-{cidr.replace('.', '-').replace('/', '-')}",
            "cidr_block": cidr,
            "region": "sa-east-1",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def create_security_group(
    client: TestClient,
    vpc_id: str,
    headers: dict[str, str],
) -> dict:
    response = client.post(
        f"/vpcs/{vpc_id}/security-groups",
        headers=headers,
        json={"name": "web", "description": "web tier"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def rule_payload(
    protocol: str = "TCP",
    port_range_from: int | None = 443,
    port_range_to: int | None = 443,
    cidr_block: str = "10.0.0.0/8",
) -> dict:
    return {
        "direction": "INBOUND",
        "protocol": protocol,
        "port_range_from": port_range_from,
        "port_range_to": port_range_to,
        "cidr_block": cidr_block,
        "description": "web traffic",
    }


def test_security_group_crud_and_tcp_udp_rules(
    postgres_security_group_api: tuple[TestClient, dict[str, int], dict[str, dict[str, str]]],
) -> None:
    client, _, headers = postgres_security_group_api
    vpc_id = create_vpc(client, headers["owner"], "10.150.0.0/16")
    group = create_security_group(client, vpc_id, headers["owner"])
    assert group["status"] == ResourceStatus.ACTIVE.value

    listed_groups = client.get(
        f"/vpcs/{vpc_id}/security-groups",
        headers=headers["owner"],
    )
    assert [item["id"] for item in listed_groups.json()] == [group["id"]]

    tcp = client.post(
        f"/security-groups/{group['id']}/rules",
        headers=headers["owner"],
        json=rule_payload("TCP", 443, 443),
    )
    udp = client.post(
        f"/security-groups/{group['id']}/rules",
        headers=headers["owner"],
        json=rule_payload("UDP", 0, 65535),
    )
    icmp = client.post(
        f"/security-groups/{group['id']}/rules",
        headers=headers["owner"],
        json=rule_payload("ICMP", None, None),
    )
    all_protocols = client.post(
        f"/security-groups/{group['id']}/rules",
        headers=headers["owner"],
        json=rule_payload("ALL", None, None),
    )
    assert (
        tcp.status_code
        == udp.status_code
        == icmp.status_code
        == all_protocols.status_code
        == 201
    )
    assert tcp.json()["protocol"] == SecurityGroupRuleProtocol.TCP.value
    assert tcp.json()["direction"] == SecurityGroupRuleDirection.INBOUND.value
    assert udp.json()["port_range_from"] == 0
    assert udp.json()["port_range_to"] == 65535
    assert icmp.json()["port_range_from"] is None
    assert all_protocols.json()["port_range_to"] is None

    listed_rules = client.get(
        f"/security-groups/{group['id']}/rules",
        headers=headers["owner"],
    )
    assert {item["id"] for item in listed_rules.json()} == {
        tcp.json()["id"],
        udp.json()["id"],
        icmp.json()["id"],
        all_protocols.json()["id"],
    }

    deleted_rule = client.delete(
        f"/security-group-rules/{tcp.json()['id']}",
        headers=headers["owner"],
    )
    assert deleted_rule.status_code == 200
    assert deleted_rule.json()["status"] == ResourceStatus.DELETED.value
    assert len(
        client.get(
            f"/security-groups/{group['id']}/rules",
            headers=headers["owner"],
        ).json()
    ) == 3

    updated = client.patch(
        f"/security-groups/{group['id']}",
        headers=headers["owner"],
        json={"name": "web-updated", "description": None},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "web-updated"
    assert updated.json()["description"] is None
    assert client.patch(
        f"/security-groups/{group['id']}",
        headers=headers["owner"],
        json={"status": "DELETED"},
    ).status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        rule_payload("TCP", None, None),
        rule_payload("UDP", 50, 49),
        rule_payload("ICMP", 8, 0),
        rule_payload("ALL", 0, 0),
        rule_payload("TCP", -1, 10),
        rule_payload("UDP", 0, 65536),
        rule_payload("TCP", 80, 80, "10.1.2.3/24"),
        rule_payload("TCP", 80, 80, "2001:db8::/32"),
    ],
)
def test_security_group_rule_rejects_invalid_ports_protocol_or_cidr(
    postgres_security_group_api: tuple[TestClient, dict[str, int], dict[str, dict[str, str]]],
    payload: dict,
) -> None:
    client, _, headers = postgres_security_group_api
    vpc_id = create_vpc(client, headers["owner"], f"10.{151 + os.urandom(1)[0] % 100}.0.0/16")
    group = create_security_group(client, vpc_id, headers["owner"])
    response = client.post(
        f"/security-groups/{group['id']}/rules",
        headers=headers["owner"],
        json=payload,
    )
    assert response.status_code == 422, response.text


def test_security_group_soft_delete_cascades_rules_and_vpc_delete_cascades_groups(
    postgres_security_group_api: tuple[TestClient, dict[str, int], dict[str, dict[str, str]]],
) -> None:
    client, _, headers = postgres_security_group_api
    vpc_id = create_vpc(client, headers["owner"], "10.152.0.0/16")
    group = create_security_group(client, vpc_id, headers["owner"])
    rule = client.post(
        f"/security-groups/{group['id']}/rules",
        headers=headers["owner"],
        json=rule_payload(),
    )
    assert rule.status_code == 201

    deleted_group = client.delete(
        f"/security-groups/{group['id']}",
        headers=headers["owner"],
    )
    assert deleted_group.status_code == 200
    assert deleted_group.json()["status"] == ResourceStatus.DELETED.value
    with SessionLocal() as db:
        assert db.get(SecurityGroupRule, UUID(rule.json()["id"])).status == ResourceStatus.DELETED

    next_vpc_id = create_vpc(client, headers["owner"], "10.153.0.0/16")
    next_group = create_security_group(client, next_vpc_id, headers["owner"])
    next_rule = client.post(
        f"/security-groups/{next_group['id']}/rules",
        headers=headers["owner"],
        json=rule_payload("UDP", 53, 53),
    )
    assert next_rule.status_code == 201

    deleted_vpc = client.delete(f"/vpcs/{next_vpc_id}", headers=headers["owner"])
    assert deleted_vpc.status_code == 200
    with SessionLocal() as db:
        assert (
            db.get(SecurityGroup, UUID(next_group["id"])).status
            == ResourceStatus.DELETED
        )
        assert (
            db.get(SecurityGroupRule, UUID(next_rule.json()["id"])).status
            == ResourceStatus.DELETED
        )


def test_security_group_ownership_hides_other_tenants_and_admin_can_access(
    postgres_security_group_api: tuple[TestClient, dict[str, int], dict[str, dict[str, str]]],
) -> None:
    client, _, headers = postgres_security_group_api
    vpc_id = create_vpc(client, headers["owner"], "10.154.0.0/16")
    group = create_security_group(client, vpc_id, headers["owner"])
    rule = client.post(
        f"/security-groups/{group['id']}/rules",
        headers=headers["owner"],
        json=rule_payload(),
    )
    assert rule.status_code == 201, rule.text

    hidden = client.get(
        f"/security-groups/{group['id']}",
        headers=headers["other"],
    )
    assert hidden.status_code == 404
    assert client.get(
        f"/security-groups/{group['id']}/rules",
        headers=headers["other"],
    ).status_code == 404
    assert client.delete(
        f"/security-group-rules/{rule.json()['id']}",
        headers=headers["other"],
    ).status_code == 404

    admin_access = client.get(
        f"/security-groups/{group['id']}",
        headers=headers["admin"],
    )
    assert admin_access.status_code == 200
    assert admin_access.json()["id"] == group["id"]
    admin_rules = client.get(
        f"/security-groups/{group['id']}/rules",
        headers=headers["admin"],
    )
    assert admin_rules.status_code == 200
    assert admin_rules.json()[0]["id"] == rule.json()["id"]

    admin_list = client.get(
        f"/vpcs/{vpc_id}/security-groups",
        headers=headers["admin"],
    )
    assert admin_list.status_code == 200
    assert [item["id"] for item in admin_list.json()] == [group["id"]]
