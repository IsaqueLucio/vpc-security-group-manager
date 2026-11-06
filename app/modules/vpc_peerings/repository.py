from typing import NamedTuple
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, aliased

from app.domain.enums import ResourceStatus
from app.modules.vpc_peerings.enums import VpcPeeringStatus
from app.modules.vpc_peerings.models import VpcPeering
from app.modules.vpcs.models import VPC


class PeeringWithOwners(NamedTuple):
    peering: VpcPeering
    requester_owner_id: int
    accepter_owner_id: int


class VpcPeeringRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_vpc(self, vpc_id: UUID) -> VPC | None:
        return self.db.scalar(
            select(VPC).where(
                VPC.id == vpc_id,
                VPC.status != ResourceStatus.DELETED,
            )
        )

    def get_active_pair(
        self,
        requester_vpc_id: UUID,
        accepter_vpc_id: UUID,
    ) -> VpcPeering | None:
        return self.db.scalar(
            select(VpcPeering).where(
                or_(
                    (
                        VpcPeering.requester_vpc_id == requester_vpc_id
                    )
                    & (VpcPeering.accepter_vpc_id == accepter_vpc_id),
                    (
                        VpcPeering.requester_vpc_id == accepter_vpc_id
                    )
                    & (VpcPeering.accepter_vpc_id == requester_vpc_id),
                ),
                VpcPeering.status.not_in(
                    (VpcPeeringStatus.DELETED, VpcPeeringStatus.REJECTED)
                ),
            )
        )

    def get_active_with_owners(self, peering_id: UUID) -> PeeringWithOwners | None:
        requester = aliased(VPC)
        accepter = aliased(VPC)
        row = self.db.execute(
            select(VpcPeering, requester.owner_id, accepter.owner_id)
            .join(requester, requester.id == VpcPeering.requester_vpc_id)
            .join(accepter, accepter.id == VpcPeering.accepter_vpc_id)
            .where(
                VpcPeering.id == peering_id,
                VpcPeering.status != VpcPeeringStatus.DELETED,
                requester.status != ResourceStatus.DELETED,
                accepter.status != ResourceStatus.DELETED,
            )
        ).one_or_none()
        if row is None:
            return None
        return PeeringWithOwners(*row)

    def list_for_owner(self, owner_id: int | None) -> list[VpcPeering]:
        requester = aliased(VPC)
        accepter = aliased(VPC)
        statement = (
            select(VpcPeering)
            .join(requester, requester.id == VpcPeering.requester_vpc_id)
            .join(accepter, accepter.id == VpcPeering.accepter_vpc_id)
            .where(
                VpcPeering.status != VpcPeeringStatus.DELETED,
                requester.status != ResourceStatus.DELETED,
                accepter.status != ResourceStatus.DELETED,
            )
            .order_by(VpcPeering.created_at, VpcPeering.id)
        )
        if owner_id is not None:
            statement = statement.where(
                or_(requester.owner_id == owner_id, accepter.owner_id == owner_id)
            )
        return list(self.db.scalars(statement).all())

    def add(self, peering: VpcPeering) -> VpcPeering:
        self.db.add(peering)
        self.db.flush()
        return peering

    def commit(self) -> None:
        self.db.commit()
