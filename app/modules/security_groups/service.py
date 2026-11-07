from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.domain.enums import ResourceStatus
from app.modules.security_group_rules.models import SecurityGroupRule
from app.modules.security_groups.models import SecurityGroup
from app.modules.security_groups.repository import SecurityGroupRepository


class SecurityGroupService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.groups = SecurityGroupRepository(db)

    def create(
        self,
        vpc_id: UUID,
        owner_id: int | None,
        name: str,
        description: str | None,
    ) -> SecurityGroup:
        vpc = self.groups.get_vpc(vpc_id, owner_id)
        if vpc is None:
            raise AppException(status_code=404, detail="VPC não encontrada.")
        if vpc.status == ResourceStatus.ERROR:
            raise AppException(
                status_code=409,
                detail="Não é possível adicionar Security Group à VPC em ERROR.",
            )
        group = SecurityGroup(
            vpc_id=vpc_id,
            name=name,
            description=description,
            status=ResourceStatus.ACTIVE,
        )
        self.groups.add(group)
        self.groups.commit()
        self.db.refresh(group)
        return group

    def list_for_vpc(
        self,
        vpc_id: UUID,
        owner_id: int | None,
    ) -> list[SecurityGroup]:
        if self.groups.get_vpc(vpc_id, owner_id) is None:
            raise AppException(status_code=404, detail="VPC não encontrada.")
        return self.groups.list_active_for_vpc(vpc_id)

    def get(self, group_id: UUID, owner_id: int | None) -> SecurityGroup:
        group = self.groups.get_active(group_id, owner_id)
        if group is None:
            raise AppException(status_code=404, detail="Security Group não encontrado.")
        return group

    def update(
        self,
        group_id: UUID,
        owner_id: int | None,
        changes: dict[str, str | None],
    ) -> SecurityGroup:
        group = self.get(group_id, owner_id)
        for field, value in changes.items():
            setattr(group, field, value)
        self.groups.commit()
        self.db.refresh(group)
        return group

    def delete(self, group_id: UUID, owner_id: int | None) -> SecurityGroup:
        group = self.get(group_id, owner_id)
        self.db.execute(
            update(SecurityGroupRule)
            .where(
                SecurityGroupRule.security_group_id == group_id,
                SecurityGroupRule.status != ResourceStatus.DELETED,
            )
            .values(status=ResourceStatus.DELETED)
        )
        group.status = ResourceStatus.DELETED
        self.groups.commit()
        self.db.refresh(group)
        return group
