from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_resource_owner_id
from app.database.session import get_db
from app.modules.security_groups.models import SecurityGroup
from app.modules.security_groups.schemas import (
    SecurityGroupCreate,
    SecurityGroupResponse,
    SecurityGroupUpdate,
)
from app.modules.security_groups.service import SecurityGroupService

router = APIRouter(tags=["security-groups"], dependencies=[Depends(get_current_user)])


@router.post(
    "/vpcs/{vpc_id}/security-groups",
    response_model=SecurityGroupResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_security_group(
    vpc_id: UUID,
    payload: SecurityGroupCreate,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int | None, Depends(get_resource_owner_id)],
) -> SecurityGroup:
    return SecurityGroupService(db).create(
        vpc_id,
        owner_id,
        payload.name,
        payload.description,
    )


@router.get(
    "/vpcs/{vpc_id}/security-groups",
    response_model=list[SecurityGroupResponse],
)
def list_security_groups(
    vpc_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int | None, Depends(get_resource_owner_id)],
) -> list[SecurityGroup]:
    return SecurityGroupService(db).list_for_vpc(vpc_id, owner_id)


@router.get("/security-groups/{group_id}", response_model=SecurityGroupResponse)
def get_security_group(
    group_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int | None, Depends(get_resource_owner_id)],
) -> SecurityGroup:
    return SecurityGroupService(db).get(group_id, owner_id)


@router.patch("/security-groups/{group_id}", response_model=SecurityGroupResponse)
def update_security_group(
    group_id: UUID,
    payload: SecurityGroupUpdate,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int | None, Depends(get_resource_owner_id)],
) -> SecurityGroup:
    return SecurityGroupService(db).update(
        group_id,
        owner_id,
        payload.model_dump(exclude_unset=True),
    )


@router.delete("/security-groups/{group_id}", response_model=SecurityGroupResponse)
def delete_security_group(
    group_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int | None, Depends(get_resource_owner_id)],
) -> SecurityGroup:
    return SecurityGroupService(db).delete(group_id, owner_id)
