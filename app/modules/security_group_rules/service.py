from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.domain.enums import ResourceStatus
from app.modules.security_group_rules.models import SecurityGroupRule
from app.modules.security_group_rules.repository import SecurityGroupRuleRepository
from app.modules.security_group_rules.schemas import SecurityGroupRuleCreate


class SecurityGroupRuleService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.rules = SecurityGroupRuleRepository(db)

    def create(
        self,
        group_id: UUID,
        owner_id: int | None,
        payload: SecurityGroupRuleCreate,
    ) -> SecurityGroupRule:
        group = self.rules.get_security_group(group_id, owner_id)
        if group is None:
            raise AppException(status_code=404, detail="Security Group não encontrado.")
        rule = SecurityGroupRule(
            security_group_id=group_id,
            direction=payload.direction,
            protocol=payload.protocol,
            port_range_from=payload.port_range_from,
            port_range_to=payload.port_range_to,
            cidr_block=payload.cidr_block,
            description=payload.description,
            status=ResourceStatus.ACTIVE,
        )
        self.rules.add(rule)
        self.rules.commit()
        self.db.refresh(rule)
        return rule

    def list_for_group(
        self,
        group_id: UUID,
        owner_id: int | None,
    ) -> list[SecurityGroupRule]:
        if self.rules.get_security_group(group_id, owner_id) is None:
            raise AppException(status_code=404, detail="Security Group não encontrado.")
        return self.rules.list_active_for_group(group_id)

    def delete(self, rule_id: UUID, owner_id: int | None) -> SecurityGroupRule:
        rule = self.rules.get_active(rule_id, owner_id)
        if rule is None:
            raise AppException(status_code=404, detail="Regra de Security Group não encontrada.")
        rule.status = ResourceStatus.DELETED
        self.rules.commit()
        self.db.refresh(rule)
        return rule
