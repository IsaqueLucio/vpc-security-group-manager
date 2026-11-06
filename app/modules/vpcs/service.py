from time import sleep
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppException
from app.database.concurrency import (
    app_exception_for_database_error,
    set_local_lock_timeout,
)
from app.database.session import SessionLocal
from app.domain.enums import ResourceStatus
from app.domain.networking import (
    InvalidCIDRError,
    PrefixLengthError,
    cidrs_overlap,
    is_private_cidr,
    is_reserved_cidr,
    parse_ipv4_cidr,
    validate_prefix_length,
)
from app.modules.subnets.models import Subnet
from app.modules.ip_allocations.models import IPAllocation
from app.modules.internet_gateways.models import InternetGateway
from app.modules.nat_gateways.models import NatGateway
from app.modules.vpcs.models import VPC
from app.modules.vpcs.repository import VPCRepository
from app.modules.vpcs.schemas import VPCCreate, VPCUpdate
from app.modules.users.repository import UserRepository

PUBLIC_CIDR_WARNING = "O CIDR informado é público; verifique se a exposição é intencional."


class VPCService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.vpcs = VPCRepository(db)

    def list_vpcs(self, owner_id: int | None, skip: int, limit: int) -> list[VPC]:
        return self.vpcs.list_active_by_owner(owner_id, skip, limit)

    def get_vpc(self, vpc_id: UUID, owner_id: int | None) -> VPC:
        vpc = self.vpcs.get_active_by_id(vpc_id, owner_id)
        if vpc is None:
            raise AppException(status_code=404, detail="VPC não encontrada.")
        return vpc

    def create_vpc(
        self,
        payload: VPCCreate,
        owner_id: int,
        authenticated_user_id: int | None = None,
    ) -> tuple[VPC, list[str]]:
        if (
            owner_id != authenticated_user_id
            and UserRepository(self.db).get_by_id(owner_id) is None
        ):
            raise AppException(status_code=404, detail="Usuário proprietário não encontrado.")
        try:
            network = validate_prefix_length(payload.cidr_block, 16, 28)
        except (InvalidCIDRError, PrefixLengthError) as exc:
            raise AppException(status_code=422, detail=str(exc)) from exc

        if is_reserved_cidr(network):
            raise AppException(
                status_code=422,
                detail=f"O CIDR {network} pertence a uma faixa reservada.",
            )
        if self.vpcs.count_active_by_owner(owner_id) >= settings.vpc_limit_per_owner:
            raise AppException(
                status_code=409,
                detail=f"O limite de {settings.vpc_limit_per_owner} VPCs por usuário foi excedido.",
            )
        if self.vpcs.get_active_by_name(owner_id, payload.name) is not None:
            raise AppException(status_code=409, detail="Já existe uma VPC ativa com esse nome.")
        if self.vpcs.get_active_by_cidr(owner_id, str(network)) is not None:
            raise AppException(status_code=409, detail="Já existe uma VPC ativa com esse CIDR.")

        for existing_cidr in self.vpcs.list_active_cidrs(owner_id):
            if cidrs_overlap(network, existing_cidr):
                raise AppException(
                    status_code=409,
                    detail=f"O CIDR {network} se sobrepõe a uma VPC ativa ({existing_cidr}).",
                )

        vpc = VPC(
            owner_id=owner_id,
            name=payload.name,
            cidr_block=str(network),
            description=payload.description,
            region=payload.region.value,
            status=ResourceStatus.PENDING,
        )
        try:
            self.vpcs.add(vpc)
        except IntegrityError as exc:
            self.db.rollback()
            app_error = app_exception_for_database_error(exc)
            if app_error is not None:
                raise app_error from exc
            raise

        warnings = [] if is_private_cidr(network) else [PUBLIC_CIDR_WARNING]
        return vpc, warnings

    def update_vpc(self, vpc_id: UUID, owner_id: int | None, payload: VPCUpdate) -> VPC:
        vpc = self.get_vpc(vpc_id, owner_id)
        changes = payload.model_dump(exclude_unset=True)
        if "name" in changes and self.vpcs.get_active_by_name(
            vpc.owner_id, changes["name"], exclude_id=vpc.id
        ):
            raise AppException(status_code=409, detail="Já existe uma VPC ativa com esse nome.")

        for field, value in changes.items():
            setattr(vpc, field, value)
        try:
            self.vpcs.commit()
            self.db.refresh(vpc)
        except IntegrityError as exc:
            self.db.rollback()
            constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            if constraint_name == "uq_vpcs_owner_name_active":
                raise AppException(
                    status_code=409,
                    detail="Já existe uma VPC ativa com esse nome.",
                ) from exc
            raise
        return vpc

    def delete_vpc(self, vpc_id: UUID, owner_id: int | None) -> VPC:
        try:
            set_local_lock_timeout(self.db)
            vpc = self.vpcs.get_owned_by_id_for_update(vpc_id, owner_id)
            if vpc is None or vpc.status == ResourceStatus.DELETED:
                self.db.rollback()
                raise AppException(status_code=404, detail="VPC não encontrada.")

            self.db.execute(
                update(Subnet)
                .where(Subnet.vpc_id == vpc_id, Subnet.status != ResourceStatus.DELETED)
                .values(status=ResourceStatus.DELETED)
            )
            self.db.execute(
                update(IPAllocation)
                .where(
                    IPAllocation.subnet_id.in_(
                        select(Subnet.id).where(Subnet.vpc_id == vpc_id)
                    ),
                    IPAllocation.status != ResourceStatus.DELETED,
                )
                .values(status=ResourceStatus.DELETED)
            )
            self.db.execute(
                update(InternetGateway)
                .where(
                    InternetGateway.vpc_id == vpc_id,
                    InternetGateway.status != ResourceStatus.DELETED,
                )
                .values(status=ResourceStatus.DELETED)
            )
            self.db.execute(
                update(NatGateway)
                .where(
                    NatGateway.subnet_id.in_(
                        select(Subnet.id).where(Subnet.vpc_id == vpc_id)
                    ),
                    NatGateway.status != ResourceStatus.DELETED,
                )
                .values(status=ResourceStatus.DELETED)
            )
            vpc.status = ResourceStatus.DELETED
            self.db.commit()
            self.db.refresh(vpc)
            return vpc
        except AppException:
            raise
        except DBAPIError as exc:
            self.db.rollback()
            app_error = app_exception_for_database_error(exc)
            if app_error is not None:
                raise app_error from exc
            raise


def activate_pending_vpc(vpc_id: UUID) -> None:
    """Activate a pending VPC after the configured delay in this process."""
    sleep(settings.vpc_provisioning_delay_seconds)
    with SessionLocal() as db:
        db.execute(
            update(VPC)
            .where(VPC.id == vpc_id, VPC.status == ResourceStatus.PENDING)
            .values(status=ResourceStatus.ACTIVE)
        )
        db.commit()