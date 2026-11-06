from uuid import UUID

from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.database.concurrency import app_exception_for_database_error
from app.domain.enums import ResourceStatus
from app.modules.internet_gateways.models import InternetGateway
from app.modules.internet_gateways.repository import InternetGatewayRepository


class InternetGatewayService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.gateways = InternetGatewayRepository(db)

    def create(self, vpc_id: UUID, owner_id: int | None) -> InternetGateway:
        vpc = self.gateways.get_vpc(vpc_id, owner_id)
        if vpc is None:
            raise AppException(status_code=404, detail="VPC não encontrada.")
        if vpc.status == ResourceStatus.ERROR:
            raise AppException(status_code=409, detail="Não é possível adicionar gateway à VPC em ERROR.")

        gateway = InternetGateway(vpc_id=vpc_id, status=ResourceStatus.ACTIVE)
        try:
            self.gateways.add(gateway)
            self.gateways.commit()
            self.db.refresh(gateway)
            return gateway
        except DBAPIError as exc:
            self.db.rollback()
            app_error = app_exception_for_database_error(exc)
            if app_error is not None:
                raise app_error from exc
            raise

    def list_for_vpc(self, vpc_id: UUID, owner_id: int | None) -> list[InternetGateway]:
        if self.gateways.get_vpc(vpc_id, owner_id) is None:
            raise AppException(status_code=404, detail="VPC não encontrada.")
        return self.gateways.list_active_for_vpc(vpc_id)

    def delete(self, gateway_id: UUID, owner_id: int | None) -> InternetGateway:
        gateway = self.gateways.get_active(gateway_id, owner_id)
        if gateway is None:
            raise AppException(status_code=404, detail="Internet Gateway não encontrado.")
        gateway.status = ResourceStatus.DELETED
        self.gateways.commit()
        self.db.refresh(gateway)
        return gateway
