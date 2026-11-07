from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import ResourceStatus
from app.modules.security_groups.models import SecurityGroup
from app.modules.vpcs.models import VPC


class SecurityGroupRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_vpc(self, vpc_id: UUID, owner_id: int | None) -> VPC | None:
        statement = select(VPC).where(
            VPC.id == vpc_id,
            VPC.status != ResourceStatus.DELETED,
        )
        if owner_id is not None:
            statement = statement.where(VPC.owner_id == owner_id)
        return self.db.scalar(statement)

    def list_active_for_vpc(self, vpc_id: UUID) -> list[SecurityGroup]:
        statement = (
            select(SecurityGroup)
            .where(
                SecurityGroup.vpc_id == vpc_id,
                SecurityGroup.status != ResourceStatus.DELETED,
            )
            .order_by(SecurityGroup.created_at, SecurityGroup.id)
        )
        return list(self.db.scalars(statement).all())

    def get_active(self, group_id: UUID, owner_id: int | None) -> SecurityGroup | None:
        statement = (
            select(SecurityGroup)
            .join(VPC, VPC.id == SecurityGroup.vpc_id)
            .where(
                SecurityGroup.id == group_id,
                SecurityGroup.status != ResourceStatus.DELETED,
                VPC.status != ResourceStatus.DELETED,
            )
        )
        if owner_id is not None:
            statement = statement.where(VPC.owner_id == owner_id)
        return self.db.scalar(statement)

    def add(self, group: SecurityGroup) -> SecurityGroup:
        self.db.add(group)
        self.db.flush()
        return group

    def commit(self) -> None:
        self.db.commit()
