from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.modules.ip_allocations.models import IPAllocation
from app.modules.ip_allocations.schemas import IPAllocationCreate, IPAllocationResponse
from app.modules.ip_allocations.service import IPAllocationService
from app.modules.vpcs.router import get_vpc_owner_id

router = APIRouter(tags=["ip-allocations"])


@router.post(
    "/subnets/{subnet_id}/ip-allocations",
    response_model=IPAllocationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_ip_allocation(
    subnet_id: UUID,
    payload: IPAllocationCreate,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int, Depends(get_vpc_owner_id)],
) -> IPAllocation:
    return IPAllocationService(db).create(subnet_id, owner_id, payload)


@router.get(
    "/subnets/{subnet_id}/ip-allocations",
    response_model=list[IPAllocationResponse],
)
def list_ip_allocations(
    subnet_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int, Depends(get_vpc_owner_id)],
) -> list[IPAllocation]:
    return IPAllocationService(db).list_for_subnet(subnet_id, owner_id)


@router.get("/ip-allocations/{allocation_id}", response_model=IPAllocationResponse)
def get_ip_allocation(
    allocation_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int, Depends(get_vpc_owner_id)],
) -> IPAllocation:
    return IPAllocationService(db).get(allocation_id, owner_id)


@router.delete("/ip-allocations/{allocation_id}", response_model=IPAllocationResponse)
def delete_ip_allocation(
    allocation_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int, Depends(get_vpc_owner_id)],
) -> IPAllocation:
    return IPAllocationService(db).delete(allocation_id, owner_id)
