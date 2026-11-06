from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, FetchedValue, ForeignKey, Index, Text, Uuid, text
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.model_types import ACTIVE_ROW, RESOURCE_STATUS
from app.domain.enums import ResourceStatus


class IPAllocation(Base):
    __tablename__ = "ip_allocations"
    __table_args__ = (
        Index(
            "uq_ip_allocations_subnet_ip_active",
            "subnet_id",
            "ip_address",
            unique=True,
            postgresql_where=ACTIVE_ROW,
        ),
        Index("ix_ip_allocations_subnet_id", "subnet_id"),
        Index("ix_ip_allocations_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    subnet_id: Mapped[UUID] = mapped_column(
        ForeignKey("subnets.id", ondelete="RESTRICT"), nullable=False
    )
    ip_address: Mapped[str] = mapped_column(INET, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
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