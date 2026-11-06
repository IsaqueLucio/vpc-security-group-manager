from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_resource_owner_id
from app.database.session import get_db
from app.modules.route_table_associations.models import RouteTableAssociation
from app.modules.route_table_associations.schemas import (
    RouteTableAssociationCreate,
    RouteTableAssociationResponse,
)
from app.modules.route_table_associations.service import RouteTableAssociationService

router = APIRouter(
    tags=["route-table-associations"],
    dependencies=[Depends(get_current_user)],
)


@router.post(
    "/subnets/{subnet_id}/route-table-association",
    response_model=RouteTableAssociationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_route_table_association(
    subnet_id: UUID,
    payload: RouteTableAssociationCreate,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int | None, Depends(get_resource_owner_id)],
) -> RouteTableAssociation:
    return RouteTableAssociationService(db).create(
        subnet_id,
        payload.route_table_id,
        owner_id,
    )


@router.delete(
    "/subnets/{subnet_id}/route-table-association",
    response_model=RouteTableAssociationResponse,
)
def delete_route_table_association(
    subnet_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int | None, Depends(get_resource_owner_id)],
) -> RouteTableAssociation:
    return RouteTableAssociationService(db).delete(subnet_id, owner_id)
