from uuid import UUID

from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.database.concurrency import app_exception_for_database_error
from app.domain.enums import ResourceStatus
from app.domain.networking import InvalidCIDRError, parse_ipv4_cidr
from app.modules.routes.enums import RouteTargetType
from app.modules.routes.models import Route
from app.modules.routes.repository import RouteRepository
from app.modules.routes.schemas import RouteCreate


class RouteService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.routes = RouteRepository(db)

    def create(
        self,
        route_table_id: UUID,
        owner_id: int | None,
        payload: RouteCreate,
    ) -> Route:
        route_table = self.routes.get_route_table(route_table_id, owner_id)
        if route_table is None:
            raise AppException(status_code=404, detail="Route Table não encontrada.")
        try:
            destination = parse_ipv4_cidr(payload.destination_cidr)
        except InvalidCIDRError as exc:
            raise AppException(status_code=422, detail=str(exc)) from exc

        if payload.target_type == RouteTargetType.LOCAL:
            if payload.target_id is not None:
                raise AppException(
                    status_code=422,
                    detail="Rotas LOCAL não devem informar target_id.",
                )
        elif payload.target_id is None:
            raise AppException(
                status_code=422,
                detail="target_id é obrigatório para destinos INTERNET_GATEWAY e NAT_GATEWAY.",
            )
        elif payload.target_type == RouteTargetType.INTERNET_GATEWAY:
            if self.routes.get_gateway(payload.target_id, route_table.vpc_id) is None:
                raise AppException(
                    status_code=422,
                    detail="O Internet Gateway deve estar ativo e pertencer à VPC da Route Table.",
                )
        elif self.routes.get_nat_gateway(payload.target_id, route_table.vpc_id) is None:
            raise AppException(
                status_code=422,
                detail="O NAT Gateway deve estar ativo e pertencer à VPC da Route Table.",
            )

        route = Route(
            route_table_id=route_table_id,
            destination_cidr=str(destination),
            target_type=payload.target_type,
            target_id=payload.target_id,
            status=ResourceStatus.ACTIVE,
        )
        try:
            self.routes.add(route)
            self.routes.commit()
            self.db.refresh(route)
            return route
        except DBAPIError as exc:
            self.db.rollback()
            app_error = app_exception_for_database_error(exc)
            if app_error is not None:
                raise app_error from exc
            raise

    def list_for_table(
        self,
        route_table_id: UUID,
        owner_id: int | None,
    ) -> list[Route]:
        if self.routes.get_route_table(route_table_id, owner_id) is None:
            raise AppException(status_code=404, detail="Route Table não encontrada.")
        return self.routes.list_active_for_table(route_table_id)

    def delete(self, route_id: UUID, owner_id: int | None) -> Route:
        route = self.routes.get_active(route_id, owner_id)
        if route is None:
            raise AppException(status_code=404, detail="Rota não encontrada.")
        route.status = ResourceStatus.DELETED
        self.routes.commit()
        self.db.refresh(route)
        return route
