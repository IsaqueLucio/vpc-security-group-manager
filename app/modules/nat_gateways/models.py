from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, FetchedValue, ForeignKey, Index, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.model_types import RESOURCE_STATUS
from app.domain.enums import ResourceStatus


class NatGateway(Base):
    __tablename__ = "nat_gateways"
    __table_args__ = (
        Index("ix_nat_gateways_subnet_id", "subnet_id"),
        Index("ix_nat_gateways_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    subnet_id: Mapped[UUID] = mapped_column(
        ForeignKey("subnets.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[ResourceStatus] = mapped_column(RESOURCE_STATUS, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        server_onupdate=FetchedValue(),
        nullable=False,
    )
