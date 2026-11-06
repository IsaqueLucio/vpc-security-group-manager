from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_resource_owner_id
from app.core.exceptions import AppException
from app.database.session import get_db
from app.modules.users.models import User, UserRole
from app.modules.vpcs.schemas import VPCAdminCreate, VPCCreate, VPCResponse, VPCUpdate
from app.modules.vpcs.service import VPCService, activate_pending_vpc

router = APIRouter(
    prefix="/vpcs",
    tags=["vpcs"],
    dependencies=[Depends(get_current_user)],
)


@router.post("", response_model=VPCResponse, status_code=status.HTTP_201_CREATED)
def create_vpc(
    payload: VPCCreate | VPCAdminCreate,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> VPCResponse:
    if current_user.role == UserRole.ADMIN:
        admin_payload = VPCAdminCreate.model_validate(payload.model_dump())
        owner_id = admin_payload.owner_id or current_user.id
        create_payload = admin_payload
    else:
        if isinstance(payload, VPCAdminCreate):
            raise AppException(
                status_code=422,
                detail="Usuários comuns não podem informar owner_id.",
            )
        create_payload = VPCCreate.model_validate(payload.model_dump())
        owner_id = current_user.id

    vpc, warnings = VPCService(db).create_vpc(
        create_payload,
        owner_id,
        authenticated_user_id=current_user.id,
    )
    background_tasks.add_task(activate_pending_vpc, vpc.id)
    return VPCResponse.model_validate(vpc).model_copy(update={"warnings": warnings})


@router.get("", response_model=list[VPCResponse])
def list_vpcs(
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int | None, Depends(get_resource_owner_id)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[VPCResponse]:
    return VPCService(db).list_vpcs(owner_id, skip, limit)


@router.get("/{vpc_id}", response_model=VPCResponse)
def get_vpc(
    vpc_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int | None, Depends(get_resource_owner_id)],
) -> VPCResponse:
    return VPCService(db).get_vpc(vpc_id, owner_id)


@router.patch("/{vpc_id}", response_model=VPCResponse)
def update_vpc(
    vpc_id: UUID,
    payload: VPCUpdate,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int | None, Depends(get_resource_owner_id)],
) -> VPCResponse:
    return VPCService(db).update_vpc(vpc_id, owner_id, payload)


@router.delete("/{vpc_id}", response_model=VPCResponse)
def delete_vpc(
    vpc_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    owner_id: Annotated[int | None, Depends(get_resource_owner_id)],
) -> VPCResponse:
    return VPCService(db).delete_vpc(vpc_id, owner_id)