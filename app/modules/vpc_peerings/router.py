from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.session import get_db
from app.modules.users.models import User
from app.modules.vpc_peerings.models import VpcPeering
from app.modules.vpc_peerings.schemas import (
    VpcPeeringCreate,
    VpcPeeringResponse,
    VpcPeeringUpdate,
)
from app.modules.vpc_peerings.service import VpcPeeringService

router = APIRouter(
    prefix="/vpc-peerings",
    tags=["vpc-peerings"],
    dependencies=[Depends(get_current_user)],
)


@router.post("", response_model=VpcPeeringResponse, status_code=status.HTTP_201_CREATED)
def create_vpc_peering(
    payload: VpcPeeringCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> VpcPeering:
    return VpcPeeringService(db).create(
        payload.requester_vpc_id,
        payload.accepter_vpc_id,
        current_user,
    )


@router.get("", response_model=list[VpcPeeringResponse])
def list_vpc_peerings(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[VpcPeering]:
    return VpcPeeringService(db).list_for_user(current_user)


@router.patch("/{peering_id}", response_model=VpcPeeringResponse)
def update_vpc_peering(
    peering_id: UUID,
    payload: VpcPeeringUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> VpcPeering:
    return VpcPeeringService(db).update_status(
        peering_id,
        payload.status,
        current_user,
    )


@router.delete("/{peering_id}", response_model=VpcPeeringResponse)
def delete_vpc_peering(
    peering_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> VpcPeering:
    return VpcPeeringService(db).delete(peering_id, current_user)
