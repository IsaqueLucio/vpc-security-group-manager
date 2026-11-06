from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import ResourceStatus
from app.modules.nat_gateways.models import NatGateway
from app.modules.subnets.models import Subnet
from app.modules.vpcs.models import VPC


class NatGatewayRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_subnet(self, subnet_id: UUID, owner_id: int | None) -> Subnet | None:
        statement = (
            select(Subnet)
            .join(VPC, VPC.id == Subnet.vpc_id)
            .where(
                Subnet.id == subnet_id,
                Subnet.status != ResourceStatus.DELETED,
                VPC.status != ResourceStatus.DELETED,
            )
        )
        if owner_id is not None:
            statement = statement.where(VPC.owner_id == owner_id)
        return self.db.scalar(statement)

    def list_active_for_subnet(self, subnet_id: UUID) -> list[NatGateway]:
        statement = (
            select(NatGateway)
            .where(
                NatGateway.subnet_id == subnet_id,
                NatGateway.status != ResourceStatus.DELETED,
            )
            .order_by(NatGateway.created_at, NatGateway.id)
        )
        return list(self.db.scalars(statement).all())

    def get_active(self, gateway_id: UUID, owner_id: int | None) -> NatGateway | None:
        statement = (
            select(NatGateway)
            .join(Subnet, Subnet.id == NatGateway.subnet_id)
            .join(VPC, VPC.id == Subnet.vpc_id)
            .where(
                NatGateway.id == gateway_id,
                NatGateway.status != ResourceStatus.DELETED,
                Subnet.status != ResourceStatus.DELETED,
                VPC.status != ResourceStatus.DELETED,
            )
        )
        if owner_id is not None:
            statement = statement.where(VPC.owner_id == owner_id)
        return self.db.scalar(statement)

    def add(self, gateway: NatGateway) -> NatGateway:
        self.db.add(gateway)
        self.db.flush()
        return gateway

    def commit(self) -> None:
        self.db.commit()
