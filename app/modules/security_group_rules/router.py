from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_resource_owner_id
from app.database.session import get_db
from app.modules.security_group_rules.models import SecurityGroupRule
from app.modules.security_group_rules.schemas import (
    SecurityGroupRuleCreate,
    SecurityGroupRuleResponse,
)
from app.modules.security_group_rules.service import SecurityGroupRuleService

router = APIRouter(tags=["security-group-rules"], dependencies=[Depends(get_current_user)])


@router.post(
    "/security-groups/{group_id}/rules",
    response_model=SecurityGroupRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_security_group_rule(
    group_id: UUID,
    payload: SecurityGroupRuleCreate,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int | None, Depends(get_resource_owner_id)],
) -> SecurityGroupRule:
    return SecurityGroupRuleService(db).create(group_id, owner_id, payload)


@router.get(
    "/security-groups/{group_id}/rules",
    response_model=list[SecurityGroupRuleResponse],
)
def list_security_group_rules(
    group_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int | None, Depends(get_resource_owner_id)],
) -> list[SecurityGroupRule]:
    return SecurityGroupRuleService(db).list_for_group(group_id, owner_id)


@router.delete(
    "/security-group-rules/{rule_id}",
    response_model=SecurityGroupRuleResponse,
)
def delete_security_group_rule(
    rule_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int | None, Depends(get_resource_owner_id)],
) -> SecurityGroupRule:
    return SecurityGroupRuleService(db).delete(rule_id, owner_id)
