from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, FetchedValue, ForeignKey, Index, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.model_types import ACTIVE_ROW, RESOURCE_STATUS
from app.domain.enums import ResourceStatus


class InternetGateway(Base):
    __tablename__ = "internet_gateways"
    __table_args__ = (
        Index(
            "uq_internet_gateways_vpc_active",
            "vpc_id",
            unique=True,
            postgresql_where=ACTIVE_ROW,
        ),
        Index("ix_internet_gateways_vpc_id", "vpc_id"),
        Index("ix_internet_gateways_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    vpc_id: Mapped[UUID] = mapped_column(
        ForeignKey("vpcs.id", ondelete="RESTRICT"), nullable=False
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
