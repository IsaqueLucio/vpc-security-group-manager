from ipaddress import IPv4Address, IPv4Network
from uuid import UUID

from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.database.concurrency import (
    app_exception_for_database_error,
    set_local_lock_timeout,
)
from app.domain.enums import ResourceStatus
from app.domain.networking import AddressSpaceExhaustedError, first_fit_ip
from app.modules.ip_allocations.models import IPAllocation
from app.modules.ip_allocations.repository import IPAllocationRepository
from app.modules.ip_allocations.schemas import IPAllocationCreate


class IPAllocationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.allocations = IPAllocationRepository(db)

    def create(
        self,
        subnet_id: UUID,
        owner_id: int | None,
        payload: IPAllocationCreate,
    ) -> IPAllocation:
        try:
            set_local_lock_timeout(self.db)
            subnet = self.allocations.get_subnet_for_update(subnet_id, owner_id)
            if subnet is None:
                self.db.rollback()
                raise AppException(status_code=404, detail="Subnet não encontrada.")
            if subnet.status in (ResourceStatus.DELETED, ResourceStatus.ERROR):
                self.db.rollback()
                raise AppException(
                    status_code=409,
                    detail="Não é possível alocar IP em uma subnet DELETED ou ERROR.",
                )

            network = IPv4Network(str(subnet.cidr_block))
            if payload.ip_address is None:
                occupied = [
                    str(allocation.ip_address)
                    for allocation in self.allocations.list_active_for_subnet(subnet_id)
                ]
                try:
                    ip_address = first_fit_ip(network, occupied)
                except AddressSpaceExhaustedError as exc:
                    self.db.rollback()
                    raise AppException(
                        status_code=409,
                        detail=f"Não há endereços IP disponíveis na subnet {network}.",
                    ) from exc
            else:
                ip_address = payload.ip_address
                if not self._is_usable_address(ip_address, network):
                    self.db.rollback()
                    raise AppException(
                        status_code=422,
                        detail="O IP está fora da subnet ou pertence aos cinco endereços reservados.",
                    )
                if self.allocations.get_active_by_ip(subnet_id, str(ip_address)) is not None:
                    self.db.rollback()
                    raise AppException(
                        status_code=409,
                        detail="O IP já está alocado nesta subnet.",
                    )

            allocation = IPAllocation(
                subnet_id=subnet_id,
                ip_address=str(ip_address),
                description=payload.description,
                status=ResourceStatus.ACTIVE,
            )
            self.allocations.add(allocation)
            self.allocations.commit()
            self.db.refresh(allocation)
            return allocation
        except AppException:
            raise
        except DBAPIError as exc:
            self.db.rollback()
            app_error = app_exception_for_database_error(exc)
            if app_error is not None:
                raise app_error from exc
            raise

    def list_for_subnet(
        self,
        subnet_id: UUID,
        owner_id: int | None,
    ) -> list[IPAllocation]:
        subnet = self.allocations.get_owned_subnet(subnet_id, owner_id)
        if subnet is None or subnet.status == ResourceStatus.DELETED:
            raise AppException(status_code=404, detail="Subnet não encontrada.")
        return self.allocations.list_active_for_subnet(subnet_id)

    def get(self, allocation_id: UUID, owner_id: int | None) -> IPAllocation:
        allocation = self.allocations.get_active(allocation_id, owner_id)
        if allocation is None:
            raise AppException(status_code=404, detail="Alocação de IP não encontrada.")
        return allocation

    def delete(self, allocation_id: UUID, owner_id: int | None) -> IPAllocation:
        try:
            allocation = self.allocations.get_active(allocation_id, owner_id)
            if allocation is None:
                raise AppException(status_code=404, detail="Alocação de IP não encontrada.")
            allocation.status = ResourceStatus.DELETED
            self.allocations.commit()
            self.db.refresh(allocation)
            return allocation
        except AppException:
            raise
        except DBAPIError as exc:
            self.db.rollback()
            app_error = app_exception_for_database_error(exc)
            if app_error is not None:
                raise app_error from exc
            raise

    @staticmethod
    def _is_usable_address(address: IPv4Address, network: IPv4Network) -> bool:
        return int(network.network_address) + 4 <= int(address) < int(network.broadcast_address)
