from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SQLEnum,
    FetchedValue,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import CIDR, ExcludeConstraint, INET
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.modules.vpcs.vpc_enum import VpcStatus


RESOURCE_STATUS = SQLEnum(VpcStatus, name="resource_status", native_enum=True)
ACTIVE_ROW = text("status != 'DELETED'")


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
    status: Mapped[VpcStatus] = mapped_column(RESOURCE_STATUS, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        server_onupdate=FetchedValue(),
        nullable=False,
    )


class Subnet(Base):
    __tablename__ = "subnets"
    __table_args__ = (
        CheckConstraint(
            "masklen(cidr_block) BETWEEN 16 AND 28",
            name="cidr_prefix_length",
        ),
        ExcludeConstraint(
            ("vpc_id", "="),
            ("cidr_block", "&&"),
            where=ACTIVE_ROW,
            ops={"cidr_block": "inet_ops"},
            name="ex_subnets_vpc_cidr_active",
        ),
        Index(
            "uq_subnets_vpc_name_active",
            "vpc_id",
            "name",
            unique=True,
            postgresql_where=ACTIVE_ROW,
        ),
        Index("ix_subnets_vpc_id", "vpc_id"),
        Index("ix_subnets_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    vpc_id: Mapped[UUID] = mapped_column(
        ForeignKey("vpcs.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    cidr_block: Mapped[str] = mapped_column(CIDR, nullable=False)
    type: Mapped[str] = mapped_column(String(7), nullable=False)
    availability_zone: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[VpcStatus] = mapped_column(RESOURCE_STATUS, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        server_onupdate=FetchedValue(),
        nullable=False,
    )


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
    status: Mapped[VpcStatus] = mapped_column(RESOURCE_STATUS, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        server_onupdate=FetchedValue(),
        nullable=False,
    )
