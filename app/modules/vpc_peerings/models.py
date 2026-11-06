from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    FetchedValue,
    ForeignKey,
    Index,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.modules.vpc_peerings.enums import VpcPeeringStatus


class VpcPeering(Base):
    __tablename__ = "vpc_peerings"
    __table_args__ = (
        CheckConstraint(
            "requester_vpc_id <> accepter_vpc_id",
            name="ck_vpc_peerings_distinct_vpcs",
        ),
        Index(
            "uq_vpc_peerings_pair_active",
            text("LEAST(requester_vpc_id, accepter_vpc_id)"),
            text("GREATEST(requester_vpc_id, accepter_vpc_id)"),
            unique=True,
            postgresql_where=text("status NOT IN ('DELETED', 'REJECTED')"),
        ),
        Index("ix_vpc_peerings_requester_vpc_id", "requester_vpc_id"),
        Index("ix_vpc_peerings_accepter_vpc_id", "accepter_vpc_id"),
        Index("ix_vpc_peerings_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    requester_vpc_id: Mapped[UUID] = mapped_column(
        ForeignKey("vpcs.id", ondelete="RESTRICT"), nullable=False
    )
    accepter_vpc_id: Mapped[UUID] = mapped_column(
        ForeignKey("vpcs.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[VpcPeeringStatus] = mapped_column(
        Enum(VpcPeeringStatus, name="vpc_peering_status", native_enum=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        server_onupdate=FetchedValue(),
        nullable=False,
    )
