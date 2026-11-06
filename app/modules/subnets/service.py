import ipaddress
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.database.concurrency import (
    app_exception_for_database_error,
    set_local_lock_timeout,
)
from app.domain.networking import (
    AddressSpaceExhaustedError,
    InvalidCIDRError,
    PrefixLengthError,
    first_fit_subnet,
    is_subnet_within_vpc,
    parse_ipv4_cidr,
    validate_prefix_length,
)
from app.domain.enums import ResourceStatus
from app.modules.ip_allocations.models import IPAllocation
from app.modules.subnets.models import Subnet
from app.modules.subnets.repository import SubnetRepository
from app.modules.subnets.schemas import SubnetCreate, SubnetUpdate

SubnetResponseData = tuple[Subnet, int, int, int]


class SubnetService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.subnets = SubnetRepository(db)

    def create_subnet(
        self,
        vpc_id: UUID,
        owner_id: int | None,
        payload: SubnetCreate,
    ) -> SubnetResponseData:
        try:
            set_local_lock_timeout(self.db)
            vpc = self.subnets.get_vpc_for_update(vpc_id, owner_id)
            if vpc is None:
                self.db.rollback()
                raise AppException(status_code=404, detail="VPC não encontrada.")
            if vpc.status in (ResourceStatus.DELETED, ResourceStatus.ERROR):
                self.db.rollback()
                raise AppException(
                    status_code=409,
                    detail="Não é possível criar uma subnet para uma VPC DELETED ou ERROR.",
                )

            parent_network = parse_ipv4_cidr(vpc.cidr_block)
            if payload.cidr_block is None:
                desired_prefix = payload.prefix_length or 24
                try:
                    validate_prefix_length(
                        f"{parent_network.network_address}/{desired_prefix}",
                        16,
                        28,
                    )
                    if desired_prefix < parent_network.prefixlen:
                        raise PrefixLengthError(
                            f"O prefixo /{desired_prefix} não cabe dentro da rede pai "
                            f"/{parent_network.prefixlen}."
                        )
                    network = first_fit_subnet(
                        parent_network,
                        desired_prefix,
                        self.subnets.list_active_cidrs(vpc_id),
                    )
                except AddressSpaceExhaustedError as exc:
                    self.db.rollback()
                    raise AppException(status_code=409, detail=str(exc)) from exc
                except (InvalidCIDRError, PrefixLengthError) as exc:
                    self.db.rollback()
                    raise AppException(status_code=422, detail=str(exc)) from exc
            else:
                try:
                    network = validate_prefix_length(payload.cidr_block, 16, 28)
                except (InvalidCIDRError, PrefixLengthError) as exc:
                    self.db.rollback()
                    raise AppException(status_code=422, detail=str(exc)) from exc
                if network.prefixlen < parent_network.prefixlen:
                    self.db.rollback()
                    raise AppException(
                        status_code=422,
                        detail="O prefixo da subnet deve ser igual ou maior que o prefixo da VPC.",
                    )
                if not is_subnet_within_vpc(network, parent_network):
                    self.db.rollback()
                    raise AppException(
                        status_code=422,
                        detail="O CIDR da subnet deve estar contido no CIDR da VPC.",
                    )
                try:
                    first_fit_subnet(
                        network,
                        network.prefixlen,
                        self.subnets.list_active_cidrs(vpc_id),
                    )
                except AddressSpaceExhaustedError as exc:
                    self.db.rollback()
                    raise AppException(
                        status_code=409,
                        detail=f"O CIDR {network} se sobrepõe a uma subnet ativa.",
                    ) from exc

            if self.subnets.get_active_by_name(vpc_id, payload.name) is not None:
                self.db.rollback()
                raise AppException(
                    status_code=409,
                    detail="Já existe uma subnet ativa com esse nome nesta VPC.",
                )

            subnet = Subnet(
                vpc_id=vpc_id,
                name=payload.name,
                cidr_block=str(network),
                type=payload.type.value,
                availability_zone=payload.availability_zone,
                status=ResourceStatus.PENDING,
            )
            self.subnets.add(subnet)
            self.subnets.commit()
            self.db.refresh(subnet)
            return self._response_values(subnet)
        except AppException:
            raise
        except DBAPIError as exc:
            self.db.rollback()
            app_error = app_exception_for_database_error(exc)
            if app_error is not None:
                raise app_error from exc
            raise

    def list_subnets(
        self,
        vpc_id: UUID,
        owner_id: int | None,
        skip: int,
        limit: int,
    ) -> list[SubnetResponseData]:
        vpc = self.subnets.get_vpc(vpc_id, owner_id)
        if vpc is None:
            raise AppException(status_code=404, detail="VPC não encontrada.")
        return [
            self._response_values(subnet)
            for subnet in self.subnets.list_active_for_vpc(vpc_id, skip, limit)
        ]

    def get_subnet(self, subnet_id: UUID, owner_id: int | None) -> SubnetResponseData:
        subnet = self.subnets.get_active_by_id(subnet_id, owner_id)
        if subnet is None:
            raise AppException(status_code=404, detail="Subnet não encontrada.")
        return self._response_values(subnet)

    def update_subnet(
        self,
        subnet_id: UUID,
        owner_id: int | None,
        payload: SubnetUpdate,
    ) -> SubnetResponseData:
        subnet = self.subnets.get_active_by_id(subnet_id, owner_id)
        if subnet is None:
            raise AppException(status_code=404, detail="Subnet não encontrada.")
        changes = payload.model_dump(exclude_unset=True)
        if "name" in changes and self.subnets.get_active_by_name(
            subnet.vpc_id,
            changes["name"],
            exclude_id=subnet.id,
        ):
            raise AppException(
                status_code=409,
                detail="Já existe uma subnet ativa com esse nome nesta VPC.",
            )
        for field, value in changes.items():
            setattr(subnet, field, value.value if hasattr(value, "value") else value)
        try:
            self.subnets.commit()
            self.db.refresh(subnet)
        except DBAPIError as exc:
            self.db.rollback()
            app_error = app_exception_for_database_error(exc)
            if app_error is not None:
                raise app_error from exc
            raise
        return self._response_values(subnet)

    def delete_subnet(self, subnet_id: UUID, owner_id: int | None) -> SubnetResponseData:
        try:
            set_local_lock_timeout(self.db)
            subnet = self.subnets.get_owned_by_id_for_update(subnet_id, owner_id)
            if subnet is None or subnet.status == ResourceStatus.DELETED:
                self.db.rollback()
                raise AppException(status_code=404, detail="Subnet não encontrada.")
            self.db.execute(
                update(IPAllocation)
                .where(
                    IPAllocation.subnet_id == subnet_id,
                    IPAllocation.status != ResourceStatus.DELETED,
                )
                .values(status=ResourceStatus.DELETED)
            )
            subnet.status = ResourceStatus.DELETED
            self.subnets.commit()
            self.db.refresh(subnet)
            return self._response_values(subnet)
        except AppException:
            raise
        except DBAPIError as exc:
            self.db.rollback()
            app_error = app_exception_for_database_error(exc)
            if app_error is not None:
                raise app_error from exc
            raise

    def _response_values(self, subnet: Subnet) -> SubnetResponseData:
        network = ipaddress.IPv4Network(str(subnet.cidr_block))
        total_ips = network.num_addresses
        usable_ips = total_ips - 5
        active_allocations = self.subnets.count_active_allocations(subnet.id)
        available_ips = max(0, usable_ips - active_allocations)
        return subnet, total_ips, usable_ips, available_ips
