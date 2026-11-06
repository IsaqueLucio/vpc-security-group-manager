from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_resource_owner_id
from app.database.session import get_db
from app.modules.route_tables.models import RouteTable
from app.modules.route_tables.schemas import RouteTableCreate, RouteTableResponse
from app.modules.route_tables.service import RouteTableService

router = APIRouter(tags=["route-tables"], dependencies=[Depends(get_current_user)])


@router.post(
    "/vpcs/{vpc_id}/route-tables",
    response_model=RouteTableResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_route_table(
    vpc_id: UUID,
    payload: RouteTableCreate,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int | None, Depends(get_resource_owner_id)],
) -> RouteTable:
    return RouteTableService(db).create(vpc_id, owner_id, payload.name)


@router.get(
    "/vpcs/{vpc_id}/route-tables",
    response_model=list[RouteTableResponse],
)
def list_route_tables(
    vpc_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int | None, Depends(get_resource_owner_id)],
) -> list[RouteTable]:
    return RouteTableService(db).list_for_vpc(vpc_id, owner_id)


@router.get("/route-tables/{route_table_id}", response_model=RouteTableResponse)
def get_route_table(
    route_table_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int | None, Depends(get_resource_owner_id)],
) -> RouteTable:
    return RouteTableService(db).get(route_table_id, owner_id)


@router.delete("/route-tables/{route_table_id}", response_model=RouteTableResponse)
def delete_route_table(
    route_table_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int | None, Depends(get_resource_owner_id)],
) -> RouteTable:
    return RouteTableService(db).delete(route_table_id, owner_id)
