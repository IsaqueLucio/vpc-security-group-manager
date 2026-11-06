from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_resource_owner_id
from app.database.session import get_db
from app.modules.internet_gateways.models import InternetGateway
from app.modules.internet_gateways.schemas import InternetGatewayResponse
from app.modules.internet_gateways.service import InternetGatewayService

router = APIRouter(tags=["internet-gateways"], dependencies=[Depends(get_current_user)])


@router.post(
    "/vpcs/{vpc_id}/internet-gateways",
    response_model=InternetGatewayResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_internet_gateway(
    vpc_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int | None, Depends(get_resource_owner_id)],
) -> InternetGateway:
    return InternetGatewayService(db).create(vpc_id, owner_id)


@router.get(
    "/vpcs/{vpc_id}/internet-gateways",
    response_model=list[InternetGatewayResponse],
)
def list_internet_gateways(
    vpc_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int | None, Depends(get_resource_owner_id)],
) -> list[InternetGateway]:
    return InternetGatewayService(db).list_for_vpc(vpc_id, owner_id)


@router.delete(
    "/internet-gateways/{gateway_id}",
    response_model=InternetGatewayResponse,
)
def delete_internet_gateway(
    gateway_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int | None, Depends(get_resource_owner_id)],
) -> InternetGateway:
    return InternetGatewayService(db).delete(gateway_id, owner_id)
