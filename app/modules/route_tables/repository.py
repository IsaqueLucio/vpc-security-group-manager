from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import ResourceStatus
from app.modules.route_tables.models import RouteTable
from app.modules.vpcs.models import VPC


class RouteTableRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_vpc(self, vpc_id: UUID, owner_id: int | None) -> VPC | None:
        statement = select(VPC).where(
            VPC.id == vpc_id,
            VPC.status != ResourceStatus.DELETED,
        )
        if owner_id is not None:
            statement = statement.where(VPC.owner_id == owner_id)
        return self.db.scalar(statement)

    def list_active_for_vpc(self, vpc_id: UUID) -> list[RouteTable]:
        statement = (
            select(RouteTable)
            .where(
                RouteTable.vpc_id == vpc_id,
                RouteTable.status != ResourceStatus.DELETED,
            )
            .order_by(RouteTable.created_at, RouteTable.id)
        )
        return list(self.db.scalars(statement).all())

    def get_active(self, route_table_id: UUID, owner_id: int | None) -> RouteTable | None:
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

    def add(self, route_table: RouteTable) -> RouteTable:
        self.db.add(route_table)
        self.db.flush()
        return route_table

    def commit(self) -> None:
        self.db.commit()
