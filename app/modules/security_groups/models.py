from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, FetchedValue, ForeignKey, Index, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.model_types import RESOURCE_STATUS
from app.domain.enums import ResourceStatus


class SecurityGroup(Base):
    __tablename__ = "security_groups"
    __table_args__ = (
        Index("ix_security_groups_vpc_id", "vpc_id"),
        Index("ix_security_groups_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    vpc_id: Mapped[UUID] = mapped_column(
        ForeignKey("vpcs.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
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
