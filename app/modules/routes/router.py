from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_resource_owner_id
from app.database.session import get_db
from app.modules.routes.models import Route
from app.modules.routes.schemas import RouteCreate, RouteResponse
from app.modules.routes.service import RouteService

router = APIRouter(tags=["routes"], dependencies=[Depends(get_current_user)])


@router.post(
    "/route-tables/{route_table_id}/routes",
    response_model=RouteResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_route(
    route_table_id: UUID,
    payload: RouteCreate,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int | None, Depends(get_resource_owner_id)],
) -> Route:
    return RouteService(db).create(route_table_id, owner_id, payload)


@router.get(
    "/route-tables/{route_table_id}/routes",
    response_model=list[RouteResponse],
)
def list_routes(
    route_table_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int | None, Depends(get_resource_owner_id)],
) -> list[Route]:
    return RouteService(db).list_for_table(route_table_id, owner_id)


@router.delete("/routes/{route_id}", response_model=RouteResponse)
def delete_route(
    route_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int | None, Depends(get_resource_owner_id)],
) -> Route:
    return RouteService(db).delete(route_id, owner_id)
