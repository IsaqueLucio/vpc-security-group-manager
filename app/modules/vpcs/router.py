from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.modules.vpcs.schemas import VPCCreate, VPCResponse, VPCUpdate
from app.modules.vpcs.service import VPCService, activate_pending_vpc

router = APIRouter(prefix="/vpcs", tags=["vpcs"])


def get_vpc_owner_id() -> int:
    # Temporary mock owner; replace with the authenticated user's ID in the authentication lot.
    return 1


@router.post("", response_model=VPCResponse, status_code=status.HTTP_201_CREATED)
def create_vpc(
    payload: VPCCreate,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int, Depends(get_vpc_owner_id)],
) -> VPCResponse:
    vpc, warnings = VPCService(db).create_vpc(payload, owner_id)
    background_tasks.add_task(activate_pending_vpc, vpc.id)
    return VPCResponse.model_validate(vpc).model_copy(update={"warnings": warnings})


@router.get("", response_model=list[VPCResponse])
def list_vpcs(
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int, Depends(get_vpc_owner_id)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[VPCResponse]:
    return VPCService(db).list_vpcs(owner_id, skip, limit)


@router.get("/{vpc_id}", response_model=VPCResponse)
def get_vpc(
    vpc_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int, Depends(get_vpc_owner_id)],
) -> VPCResponse:
    return VPCService(db).get_vpc(vpc_id, owner_id)


@router.patch("/{vpc_id}", response_model=VPCResponse)
def update_vpc(
    vpc_id: UUID,
    payload: VPCUpdate,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int, Depends(get_vpc_owner_id)],
) -> VPCResponse:
    return VPCService(db).update_vpc(vpc_id, owner_id, payload)


@router.delete("/{vpc_id}", response_model=VPCResponse)
def delete_vpc(
    vpc_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int, Depends(get_vpc_owner_id)],
) -> VPCResponse:
    return VPCService(db).delete_vpc(vpc_id, owner_id)