from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.domain.enums import ResourceStatus
from app.modules.nat_gateways.models import NatGateway
from app.modules.nat_gateways.repository import NatGatewayRepository
from app.modules.subnets.enums import SubnetType


class NatGatewayService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.gateways = NatGatewayRepository(db)

    def create(self, subnet_id: UUID, owner_id: int | None) -> NatGateway:
        subnet = self.gateways.get_subnet(subnet_id, owner_id)
        if subnet is None:
            raise AppException(status_code=404, detail="Subnet não encontrada.")
        if subnet.type != SubnetType.PUBLIC.value:
            raise AppException(
                status_code=422,
                detail="NAT Gateway só pode ser associado a uma subnet PUBLIC.",
            )

        gateway = NatGateway(subnet_id=subnet_id, status=ResourceStatus.ACTIVE)
        self.gateways.add(gateway)
        self.gateways.commit()
        self.db.refresh(gateway)
        return gateway

    def list_for_subnet(self, subnet_id: UUID, owner_id: int | None) -> list[NatGateway]:
        if self.gateways.get_subnet(subnet_id, owner_id) is None:
            raise AppException(status_code=404, detail="Subnet não encontrada.")
        return self.gateways.list_active_for_subnet(subnet_id)

    def delete(self, gateway_id: UUID, owner_id: int | None) -> NatGateway:
        gateway = self.gateways.get_active(gateway_id, owner_id)
        if gateway is None:
            raise AppException(status_code=404, detail="NAT Gateway não encontrado.")
        gateway.status = ResourceStatus.DELETED
        self.gateways.commit()
        self.db.refresh(gateway)
        return gateway
