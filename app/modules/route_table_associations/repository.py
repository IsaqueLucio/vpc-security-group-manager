from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import ResourceStatus
from app.modules.route_table_associations.models import RouteTableAssociation
from app.modules.route_tables.models import RouteTable
from app.modules.subnets.models import Subnet
from app.modules.vpcs.models import VPC


class RouteTableAssociationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_subnet(self, subnet_id: UUID, owner_id: int | None) -> Subnet | None:
        statement = (
            select(Subnet)
            .join(VPC, VPC.id == Subnet.vpc_id)
            .where(
                Subnet.id == subnet_id,
                Subnet.status != ResourceStatus.DELETED,
                VPC.status != ResourceStatus.DELETED,
            )
        )
        if owner_id is not None:
            statement = statement.where(VPC.owner_id == owner_id)
        return self.db.scalar(statement)

    def get_route_table(
        self,
        route_table_id: UUID,
        owner_id: int | None,
    ) -> RouteTable | None:
        statement = (
            select(RouteTable)
            .join(VPC, VPC.id == RouteTable.vpc_id)
            .where(
                RouteTable.id == route_table_id,
                RouteTable.status != ResourceStatus.DELETED,
                VPC.status != ResourceStatus.DELETED,
            )
        )
        if owner_id is not None:
            statement = statement.where(VPC.owner_id == owner_id)
        return self.db.scalar(statement)

    def get_active_for_subnet(self, subnet_id: UUID) -> RouteTableAssociation | None:
        return self.db.scalar(
            select(RouteTableAssociation).where(
                RouteTableAssociation.subnet_id == subnet_id,
                RouteTableAssociation.status != ResourceStatus.DELETED,
            )
        )

    def get_active(self, subnet_id: UUID, owner_id: int | None) -> RouteTableAssociation | None:
        statement = (
            select(RouteTableAssociation)
            .join(Subnet, Subnet.id == RouteTableAssociation.subnet_id)
            .join(VPC, VPC.id == Subnet.vpc_id)
            .where(
                RouteTableAssociation.subnet_id == subnet_id,
                RouteTableAssociation.status != ResourceStatus.DELETED,
                Subnet.status != ResourceStatus.DELETED,
                VPC.status != ResourceStatus.DELETED,
            )
        )
        if owner_id is not None:
            statement = statement.where(VPC.owner_id == owner_id)
        return self.db.scalar(statement)

    def add(self, association: RouteTableAssociation) -> RouteTableAssociation:
        self.db.add(association)
        self.db.flush()
        return association

    def commit(self) -> None:
        self.db.commit()
