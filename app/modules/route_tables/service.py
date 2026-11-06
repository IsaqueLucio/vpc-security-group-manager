from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.domain.enums import ResourceStatus
from app.modules.route_table_associations.models import RouteTableAssociation
from app.modules.route_tables.models import RouteTable
from app.modules.route_tables.repository import RouteTableRepository
from app.modules.routes.models import Route


class RouteTableService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.route_tables = RouteTableRepository(db)

    def create(self, vpc_id: UUID, owner_id: int | None, name: str) -> RouteTable:
        vpc = self.route_tables.get_vpc(vpc_id, owner_id)
        if vpc is None:
            raise AppException(status_code=404, detail="VPC não encontrada.")
        if vpc.status == ResourceStatus.ERROR:
            raise AppException(status_code=409, detail="Não é possível adicionar route table à VPC em ERROR.")
        route_table = RouteTable(
            vpc_id=vpc_id,
            name=name,
            status=ResourceStatus.ACTIVE,
        )
        self.route_tables.add(route_table)
        self.route_tables.commit()
        self.db.refresh(route_table)
        return route_table

    def list_for_vpc(self, vpc_id: UUID, owner_id: int | None) -> list[RouteTable]:
        if self.route_tables.get_vpc(vpc_id, owner_id) is None:
            raise AppException(status_code=404, detail="VPC não encontrada.")
        return self.route_tables.list_active_for_vpc(vpc_id)

    def get(self, route_table_id: UUID, owner_id: int | None) -> RouteTable:
        route_table = self.route_tables.get_active(route_table_id, owner_id)
        if route_table is None:
            raise AppException(status_code=404, detail="Route Table não encontrada.")
        return route_table

    def delete(self, route_table_id: UUID, owner_id: int | None) -> RouteTable:
        route_table = self.get(route_table_id, owner_id)
        self.db.execute(
            update(Route)
            .where(
                Route.route_table_id == route_table_id,
                Route.status != ResourceStatus.DELETED,
            )
            .values(status=ResourceStatus.DELETED)
        )
        self.db.execute(
            update(RouteTableAssociation)
            .where(
                RouteTableAssociation.route_table_id == route_table_id,
                RouteTableAssociation.status != ResourceStatus.DELETED,
            )
            .values(status=ResourceStatus.DELETED)
        )
        route_table.status = ResourceStatus.DELETED
        self.route_tables.commit()
        self.db.refresh(route_table)
        return route_table
