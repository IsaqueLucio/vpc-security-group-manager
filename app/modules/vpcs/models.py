from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    FetchedValue,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import CIDR, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.model_types import ACTIVE_ROW, RESOURCE_STATUS
from app.domain.enums import ResourceStatus


class VPC(Base):
    __tablename__ = "vpcs"
    __table_args__ = (
        CheckConstraint(
            "masklen(cidr_block) BETWEEN 16 AND 28",
            name="cidr_prefix_length",
        ),
        ExcludeConstraint(
            ("owner_id", "="),
            ("cidr_block", "&&"),
            where=ACTIVE_ROW,
            ops={"cidr_block": "inet_ops"},
            name="ex_vpcs_owner_cidr_active",
        ),
        Index(
            "uq_vpcs_owner_name_active",
            "owner_id",
            "name",
            unique=True,
            postgresql_where=ACTIVE_ROW,
        ),
        Index("ix_vpcs_owner_id", "owner_id"),
        Index("ix_vpcs_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    cidr_block: Mapped[str] = mapped_column(CIDR, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    region: Mapped[str] = mapped_column(String(32), nullable=False)
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
