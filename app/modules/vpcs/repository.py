from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.vpcs.models import VPC
from app.modules.vpcs.vpc_enum import VpcStatus


class VPCRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_active_by_owner(self, owner_id: int, skip: int, limit: int) -> list[VPC]:
        statement = (
            select(VPC)
            .where(VPC.owner_id == owner_id, VPC.status != VpcStatus.DELETED)
            .order_by(VPC.created_at, VPC.id)
            .offset(skip)
            .limit(limit)
        )
        return list(self.db.scalars(statement).all())

    def get_active_by_id(self, vpc_id: UUID, owner_id: int) -> VPC | None:
        statement = select(VPC).where(
            VPC.id == vpc_id,
            VPC.owner_id == owner_id,
            VPC.status != VpcStatus.DELETED,
        )
        return self.db.scalar(statement)

    def get_owned_by_id_for_update(self, vpc_id: UUID, owner_id: int) -> VPC | None:
        statement = (
            select(VPC)
            .where(VPC.id == vpc_id, VPC.owner_id == owner_id)
            .with_for_update()
        )
        return self.db.scalar(statement)

    def get_active_by_name(self, owner_id: int, name: str, exclude_id: UUID | None = None) -> VPC | None:
        statement = select(VPC).where(
            VPC.owner_id == owner_id,
            VPC.name == name,
            VPC.status != VpcStatus.DELETED,
        )
        if exclude_id is not None:
            statement = statement.where(VPC.id != exclude_id)
        return self.db.scalar(statement)

    def get_active_by_cidr(self, owner_id: int, cidr_block: str) -> VPC | None:
        statement = select(VPC).where(
            VPC.owner_id == owner_id,
            VPC.cidr_block == cidr_block,
            VPC.status != VpcStatus.DELETED,
        )
        return self.db.scalar(statement)

    def list_active_cidrs(self, owner_id: int) -> list[str]:
        statement = select(VPC.cidr_block).where(
            VPC.owner_id == owner_id,
            VPC.status != VpcStatus.DELETED,
        )
        return [str(cidr) for cidr in self.db.scalars(statement).all()]

    def count_active_by_owner(self, owner_id: int) -> int:
        statement = select(func.count()).select_from(VPC).where(
            VPC.owner_id == owner_id,
            VPC.status != VpcStatus.DELETED,
        )
        return int(self.db.scalar(statement) or 0)

    def add(self, vpc: VPC) -> VPC:
        self.db.add(vpc)
        self.db.commit()
        self.db.refresh(vpc)
        return vpc

    def commit(self) -> None:
        self.db.commit()