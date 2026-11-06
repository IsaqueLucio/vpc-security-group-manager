from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.vpcs.models import IPAllocation, Subnet, VPC
from app.modules.vpcs.vpc_enum import VpcStatus


class SubnetRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_vpc_for_update(self, vpc_id: UUID, owner_id: int) -> VPC | None:
        statement = (
            select(VPC)
            .where(VPC.id == vpc_id, VPC.owner_id == owner_id)
            .with_for_update()
        )
        return self.db.scalar(statement)

    def get_vpc(self, vpc_id: UUID, owner_id: int) -> VPC | None:
        statement = select(VPC).where(
            VPC.id == vpc_id,
            VPC.owner_id == owner_id,
            VPC.status != VpcStatus.DELETED,
        )
        return self.db.scalar(statement)

    def list_active_for_vpc(self, vpc_id: UUID, skip: int, limit: int) -> list[Subnet]:
        statement = (
            select(Subnet)
            .where(Subnet.vpc_id == vpc_id, Subnet.status != VpcStatus.DELETED)
            .order_by(Subnet.created_at, Subnet.id)
            .offset(skip)
            .limit(limit)
        )
        return list(self.db.scalars(statement).all())

    def get_active_by_id(self, subnet_id: UUID, owner_id: int) -> Subnet | None:
        statement = (
            select(Subnet)
            .join(VPC, VPC.id == Subnet.vpc_id)
            .where(
                Subnet.id == subnet_id,
                VPC.owner_id == owner_id,
                Subnet.status != VpcStatus.DELETED,
            )
        )
        return self.db.scalar(statement)

    def get_active_by_name(
        self,
        vpc_id: UUID,
        name: str,
        exclude_id: UUID | None = None,
    ) -> Subnet | None:
        statement = select(Subnet).where(
            Subnet.vpc_id == vpc_id,
            Subnet.name == name,
            Subnet.status != VpcStatus.DELETED,
        )
        if exclude_id is not None:
            statement = statement.where(Subnet.id != exclude_id)
        return self.db.scalar(statement)

    def list_active_cidrs(self, vpc_id: UUID) -> list[str]:
        statement = select(Subnet.cidr_block).where(
            Subnet.vpc_id == vpc_id,
            Subnet.status != VpcStatus.DELETED,
        )
        return [str(cidr) for cidr in self.db.scalars(statement).all()]

    def count_active_allocations(self, subnet_id: UUID) -> int:
        statement = select(func.count()).select_from(IPAllocation).where(
            IPAllocation.subnet_id == subnet_id,
            IPAllocation.status != VpcStatus.DELETED,
        )
        return int(self.db.scalar(statement) or 0)

    def add(self, subnet: Subnet) -> Subnet:
        self.db.add(subnet)
        self.db.flush()
        return subnet

    def commit(self) -> None:
        self.db.commit()
