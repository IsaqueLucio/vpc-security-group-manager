from uuid import UUID

from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.database.concurrency import app_exception_for_database_error
from app.domain.networking import cidrs_overlap
from app.modules.users.models import User, UserRole
from app.modules.vpc_peerings.enums import VpcPeeringStatus
from app.modules.vpc_peerings.models import VpcPeering
from app.modules.vpc_peerings.repository import (
    PeeringWithOwners,
    VpcPeeringRepository,
)
from app.modules.vpcs.models import VPC


class VpcPeeringService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.peerings = VpcPeeringRepository(db)

    def create(
        self,
        requester_vpc_id: UUID,
        accepter_vpc_id: UUID,
        current_user: User,
    ) -> VpcPeering:
        if requester_vpc_id == accepter_vpc_id:
            raise AppException(status_code=422, detail="Uma VPC não pode estabelecer peering consigo mesma.")

        requester = self._get_vpc(requester_vpc_id)
        accepter = self._get_vpc(accepter_vpc_id)
        if (
            current_user.role != UserRole.ADMIN
            and requester.owner_id != current_user.id
        ):
            raise AppException(status_code=404, detail="VPC requester não encontrada.")

        if cidrs_overlap(requester.cidr_block, accepter.cidr_block):
            raise AppException(
                status_code=409,
                detail="Os CIDRs das VPCs se sobrepõem; o peering não pode ser criado.",
            )
        if self.peerings.get_active_pair(requester_vpc_id, accepter_vpc_id) is not None:
            raise AppException(
                status_code=409,
                detail="Já existe um peering pendente ou ativo para esse par de VPCs.",
            )

        peering = VpcPeering(
            requester_vpc_id=requester_vpc_id,
            accepter_vpc_id=accepter_vpc_id,
            status=VpcPeeringStatus.PENDING_ACCEPTANCE,
        )
        try:
            self.peerings.add(peering)
            self.peerings.commit()
            self.db.refresh(peering)
            return peering
        except DBAPIError as exc:
            self.db.rollback()
            app_error = app_exception_for_database_error(exc)
            if app_error is not None:
                raise app_error from exc
            raise

    def list_for_user(self, current_user: User) -> list[VpcPeering]:
        owner_id = None if current_user.role == UserRole.ADMIN else current_user.id
        return self.peerings.list_for_owner(owner_id)

    def update_status(
        self,
        peering_id: UUID,
        status: VpcPeeringStatus,
        current_user: User,
    ) -> VpcPeering:
        peering = self._get_authorized_peering(peering_id, current_user)
        if (
            current_user.role != UserRole.ADMIN
            and peering.accepter_owner_id != current_user.id
        ):
            raise AppException(
                status_code=403,
                detail="Somente o proprietário da VPC accepter pode aceitar ou rejeitar o peering.",
            )
        if status not in (VpcPeeringStatus.ACTIVE, VpcPeeringStatus.REJECTED):
            raise AppException(
                status_code=422,
                detail="O status deve ser ACTIVE ou REJECTED.",
            )
        if peering.peering.status != VpcPeeringStatus.PENDING_ACCEPTANCE:
            raise AppException(
                status_code=409,
                detail="Somente peerings pendentes podem ser aceitos ou rejeitados.",
            )
        peering.peering.status = status
        self.peerings.commit()
        self.db.refresh(peering.peering)
        return peering.peering

    def delete(self, peering_id: UUID, current_user: User) -> VpcPeering:
        peering = self._get_authorized_peering(peering_id, current_user)
        if current_user.role != UserRole.ADMIN and (
            peering.requester_owner_id != current_user.id
        ):
            raise AppException(
                status_code=403,
                detail="Somente o proprietário da VPC requester pode cancelar o peering.",
            )
        if peering.peering.status != VpcPeeringStatus.PENDING_ACCEPTANCE:
            raise AppException(
                status_code=409,
                detail="Somente peerings pendentes podem ser cancelados.",
            )
        peering.peering.status = VpcPeeringStatus.DELETED
        self.peerings.commit()
        self.db.refresh(peering.peering)
        return peering.peering

    def _get_authorized_peering(
        self,
        peering_id: UUID,
        current_user: User,
    ) -> PeeringWithOwners:
        peering = self.peerings.get_active_with_owners(peering_id)
        if peering is None:
            raise AppException(status_code=404, detail="Peering não encontrado.")
        if current_user.role == UserRole.ADMIN or current_user.id in (
            peering.requester_owner_id,
            peering.accepter_owner_id,
        ):
            return peering
        raise AppException(status_code=404, detail="Peering não encontrado.")

    def _get_vpc(self, vpc_id: UUID) -> VPC:
        vpc = self.peerings.get_vpc(vpc_id)
        if vpc is None:
            raise AppException(status_code=404, detail="VPC não encontrada.")
        return vpc
