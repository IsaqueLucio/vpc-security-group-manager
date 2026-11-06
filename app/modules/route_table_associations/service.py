from uuid import UUID

from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.database.concurrency import app_exception_for_database_error
from app.domain.enums import ResourceStatus
from app.modules.route_table_associations.models import RouteTableAssociation
from app.modules.route_table_associations.repository import RouteTableAssociationRepository


class RouteTableAssociationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.associations = RouteTableAssociationRepository(db)

    def create(
        self,
        subnet_id: UUID,
        route_table_id: UUID,
        owner_id: int | None,
    ) -> RouteTableAssociation:
        subnet = self.associations.get_subnet(subnet_id, owner_id)
        if subnet is None:
            raise AppException(status_code=404, detail="Subnet não encontrada.")
        route_table = self.associations.get_route_table(route_table_id, owner_id)
        if route_table is None:
            raise AppException(status_code=404, detail="Route Table não encontrada.")
        if subnet.vpc_id != route_table.vpc_id:
            raise AppException(
                status_code=422,
                detail="A Subnet e a Route Table devem pertencer à mesma VPC.",
            )
        if self.associations.get_active_for_subnet(subnet_id) is not None:
            raise AppException(
                status_code=409,
                detail="A Subnet já possui uma Route Table associada.",
            )

        association = RouteTableAssociation(
            subnet_id=subnet_id,
            route_table_id=route_table_id,
            status=ResourceStatus.ACTIVE,
        )
        try:
            self.associations.add(association)
            self.associations.commit()
            self.db.refresh(association)
            return association
        except DBAPIError as exc:
            self.db.rollback()
            app_error = app_exception_for_database_error(exc)
            if app_error is not None:
                raise app_error from exc
            raise

    def delete(
        self,
        subnet_id: UUID,
        owner_id: int | None,
    ) -> RouteTableAssociation:
        association = self.associations.get_active(subnet_id, owner_id)
        if association is None:
            raise AppException(status_code=404, detail="Associação não encontrada.")
        association.status = ResourceStatus.DELETED
        self.associations.commit()
        self.db.refresh(association)
        return association
