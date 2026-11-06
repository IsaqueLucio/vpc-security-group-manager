from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.modules.vpcs.models import Subnet
from app.modules.vpcs.router import get_vpc_owner_id
from app.modules.vpcs.schemas import SubnetCreate, SubnetResponse, SubnetUpdate
from app.modules.vpcs.subnet_service import SubnetResponseData, SubnetService

subnet_router = APIRouter(tags=["subnets"])


def _subnet_response(values: SubnetResponseData) -> SubnetResponse:
    subnet, total_ips, usable_ips, available_ips = values
    return SubnetResponse(
        id=subnet.id,
        vpc_id=subnet.vpc_id,
        name=subnet.name,
        cidr_block=str(subnet.cidr_block),
        type=subnet.type,
        availability_zone=subnet.availability_zone,
        status=subnet.status,
        created_at=subnet.created_at,
        updated_at=subnet.updated_at,
        total_ips=total_ips,
        usable_ips=usable_ips,
        available_ips=available_ips,
    )


@subnet_router.post(
    "/vpcs/{vpc_id}/subnets",
    response_model=SubnetResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_subnet(
    vpc_id: UUID,
    payload: SubnetCreate,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int, Depends(get_vpc_owner_id)],
) -> SubnetResponse:
    return _subnet_response(SubnetService(db).create_subnet(vpc_id, owner_id, payload))


@subnet_router.get("/vpcs/{vpc_id}/subnets", response_model=list[SubnetResponse])
def list_subnets(
    vpc_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int, Depends(get_vpc_owner_id)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[SubnetResponse]:
    values = SubnetService(db).list_subnets(vpc_id, owner_id, skip, limit)
    return [_subnet_response(value) for value in values]


@subnet_router.get("/subnets/{subnet_id}", response_model=SubnetResponse)
def get_subnet(
    subnet_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int, Depends(get_vpc_owner_id)],
) -> SubnetResponse:
    return _subnet_response(SubnetService(db).get_subnet(subnet_id, owner_id))


@subnet_router.patch("/subnets/{subnet_id}", response_model=SubnetResponse)
def update_subnet(
    subnet_id: UUID,
    payload: SubnetUpdate,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int, Depends(get_vpc_owner_id)],
) -> SubnetResponse:
    return _subnet_response(SubnetService(db).update_subnet(subnet_id, owner_id, payload))


@subnet_router.delete("/subnets/{subnet_id}", response_model=SubnetResponse)
def delete_subnet(
    subnet_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int, Depends(get_vpc_owner_id)],
) -> SubnetResponse:
    return _subnet_response(SubnetService(db).delete_subnet(subnet_id, owner_id))
