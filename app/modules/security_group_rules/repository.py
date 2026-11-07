from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import ResourceStatus
from app.modules.security_group_rules.models import SecurityGroupRule
from app.modules.security_groups.models import SecurityGroup
from app.modules.vpcs.models import VPC


class SecurityGroupRuleRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_security_group(
        self,
        group_id: UUID,
        owner_id: int | None,
    ) -> SecurityGroup | None:
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

    def list_active_for_group(self, group_id: UUID) -> list[SecurityGroupRule]:
        statement = (
            select(SecurityGroupRule)
            .where(
                SecurityGroupRule.security_group_id == group_id,
                SecurityGroupRule.status != ResourceStatus.DELETED,
            )
            .order_by(SecurityGroupRule.created_at, SecurityGroupRule.id)
        )
        return list(self.db.scalars(statement).all())

    def get_active(self, rule_id: UUID, owner_id: int | None) -> SecurityGroupRule | None:
        statement = (
            select(SecurityGroupRule)
            .join(
                SecurityGroup,
                SecurityGroup.id == SecurityGroupRule.security_group_id,
            )
            .join(VPC, VPC.id == SecurityGroup.vpc_id)
            .where(
                SecurityGroupRule.id == rule_id,
                SecurityGroupRule.status != ResourceStatus.DELETED,
                SecurityGroup.status != ResourceStatus.DELETED,
                VPC.status != ResourceStatus.DELETED,
            )
        )
        if owner_id is not None:
            statement = statement.where(VPC.owner_id == owner_id)
        return self.db.scalar(statement)

    def add(self, rule: SecurityGroupRule) -> SecurityGroupRule:
        self.db.add(rule)
        self.db.flush()
        return rule

    def commit(self) -> None:
        self.db.commit()
