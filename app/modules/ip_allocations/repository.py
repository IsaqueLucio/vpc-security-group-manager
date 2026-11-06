from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import ResourceStatus
from app.modules.ip_allocations.models import IPAllocation
from app.modules.subnets.models import Subnet
from app.modules.vpcs.models import VPC


class IPAllocationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_subnet_for_update(self, subnet_id: UUID, owner_id: int) -> Subnet | None:
        statement = (
            select(Subnet)
            .join(VPC, VPC.id == Subnet.vpc_id)
            .where(
                Subnet.id == subnet_id,
                VPC.owner_id == owner_id,
                VPC.status != ResourceStatus.DELETED,
            )
            .with_for_update(of=Subnet)
        )
        return self.db.scalar(statement)

    def get_owned_subnet(self, subnet_id: UUID, owner_id: int) -> Subnet | None:
        statement = (
            select(Subnet)
            .join(VPC, VPC.id == Subnet.vpc_id)
            .where(
                Subnet.id == subnet_id,
                VPC.owner_id == owner_id,
                VPC.status != ResourceStatus.DELETED,
            )
        )
        return self.db.scalar(statement)

    def get_active(self, allocation_id: UUID, owner_id: int) -> IPAllocation | None:
        statement = (
            select(IPAllocation)
            .join(Subnet, Subnet.id == IPAllocation.subnet_id)
            .join(VPC, VPC.id == Subnet.vpc_id)
            .where(
                IPAllocation.id == allocation_id,
                IPAllocation.status != ResourceStatus.DELETED,
                Subnet.status != ResourceStatus.DELETED,
                VPC.status != ResourceStatus.DELETED,
                VPC.owner_id == owner_id,
            )
        )
        return self.db.scalar(statement)

    def list_active_for_subnet(self, subnet_id: UUID) -> list[IPAllocation]:
        statement = (
            select(IPAllocation)
            .where(
                IPAllocation.subnet_id == subnet_id,
                IPAllocation.status != ResourceStatus.DELETED,
            )
            .order_by(IPAllocation.created_at, IPAllocation.id)
        )
        return list(self.db.scalars(statement).all())

    def get_active_by_ip(self, subnet_id: UUID, ip_address: str) -> IPAllocation | None:
        statement = select(IPAllocation).where(
            IPAllocation.subnet_id == subnet_id,
            IPAllocation.ip_address == ip_address,
            IPAllocation.status != ResourceStatus.DELETED,
        )
        return self.db.scalar(statement)

    def add(self, allocation: IPAllocation) -> IPAllocation:
        self.db.add(allocation)
        self.db.flush()
        return allocation

    def commit(self) -> None:
        self.db.commit()
