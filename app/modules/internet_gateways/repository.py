from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import ResourceStatus
from app.modules.internet_gateways.models import InternetGateway
from app.modules.vpcs.models import VPC


class InternetGatewayRepository:
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

    def list_active_for_vpc(self, vpc_id: UUID) -> list[InternetGateway]:
        statement = (
            select(InternetGateway)
            .where(
                InternetGateway.vpc_id == vpc_id,
                InternetGateway.status != ResourceStatus.DELETED,
            )
            .order_by(InternetGateway.created_at, InternetGateway.id)
        )
        return list(self.db.scalars(statement).all())

    def get_active(self, gateway_id: UUID, owner_id: int | None) -> InternetGateway | None:
        statement = (
            select(InternetGateway)
            .join(VPC, VPC.id == InternetGateway.vpc_id)
            .where(
                InternetGateway.id == gateway_id,
                InternetGateway.status != ResourceStatus.DELETED,
                VPC.status != ResourceStatus.DELETED,
            )
        )
        if owner_id is not None:
            statement = statement.where(VPC.owner_id == owner_id)
        return self.db.scalar(statement)

    def add(self, gateway: InternetGateway) -> InternetGateway:
        self.db.add(gateway)
        self.db.flush()
        return gateway

    def commit(self) -> None:
        self.db.commit()
