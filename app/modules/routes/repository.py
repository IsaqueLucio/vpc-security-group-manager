from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import ResourceStatus
from app.modules.internet_gateways.models import InternetGateway
from app.modules.nat_gateways.models import NatGateway
from app.modules.routes.models import Route
from app.modules.route_tables.models import RouteTable
from app.modules.subnets.models import Subnet
from app.modules.vpcs.models import VPC


class RouteRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_route_table(self, route_table_id: UUID, owner_id: int | None) -> RouteTable | None:
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

    def get_gateway(self, target_id: UUID, vpc_id: UUID) -> InternetGateway | None:
        statement = select(InternetGateway).where(
            InternetGateway.id == target_id,
            InternetGateway.vpc_id == vpc_id,
            InternetGateway.status == ResourceStatus.ACTIVE,
        )
        return self.db.scalar(statement)

    def get_nat_gateway(self, target_id: UUID, vpc_id: UUID) -> NatGateway | None:
        statement = (
            select(NatGateway)
            .join(Subnet, Subnet.id == NatGateway.subnet_id)
            .where(
                NatGateway.id == target_id,
                NatGateway.status == ResourceStatus.ACTIVE,
                Subnet.vpc_id == vpc_id,
                Subnet.status != ResourceStatus.DELETED,
                Subnet.type == "PUBLIC",
            )
        )
        return self.db.scalar(statement)

    def list_active_for_table(self, route_table_id: UUID) -> list[Route]:
        statement = (
            select(Route)
            .where(
                Route.route_table_id == route_table_id,
                Route.status != ResourceStatus.DELETED,
            )
            .order_by(Route.created_at, Route.id)
        )
        return list(self.db.scalars(statement).all())

    def get_active(self, route_id: UUID, owner_id: int | None) -> Route | None:
        statement = (
            select(Route)
            .join(RouteTable, RouteTable.id == Route.route_table_id)
            .join(VPC, VPC.id == RouteTable.vpc_id)
            .where(
                Route.id == route_id,
                Route.status != ResourceStatus.DELETED,
                RouteTable.status != ResourceStatus.DELETED,
                VPC.status != ResourceStatus.DELETED,
            )
        )
        if owner_id is not None:
            statement = statement.where(VPC.owner_id == owner_id)
        return self.db.scalar(statement)

    def add(self, route: Route) -> Route:
        self.db.add(route)
        self.db.flush()
        return route

    def commit(self) -> None:
        self.db.commit()
