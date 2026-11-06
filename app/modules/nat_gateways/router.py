from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_resource_owner_id
from app.database.session import get_db
from app.modules.nat_gateways.models import NatGateway
from app.modules.nat_gateways.schemas import NatGatewayResponse
from app.modules.nat_gateways.service import NatGatewayService

router = APIRouter(tags=["nat-gateways"], dependencies=[Depends(get_current_user)])


@router.post(
    "/subnets/{subnet_id}/nat-gateways",
    response_model=NatGatewayResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_nat_gateway(
    subnet_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int | None, Depends(get_resource_owner_id)],
) -> NatGateway:
    return NatGatewayService(db).create(subnet_id, owner_id)


@router.get(
    "/subnets/{subnet_id}/nat-gateways",
    response_model=list[NatGatewayResponse],
)
def list_nat_gateways(
    subnet_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int | None, Depends(get_resource_owner_id)],
) -> list[NatGateway]:
    return NatGatewayService(db).list_for_subnet(subnet_id, owner_id)


@router.delete("/nat-gateways/{gateway_id}", response_model=NatGatewayResponse)
def delete_nat_gateway(
    gateway_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int | None, Depends(get_resource_owner_id)],
) -> NatGateway:
    return NatGatewayService(db).delete(gateway_id, owner_id)
