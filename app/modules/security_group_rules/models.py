from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Enum,
    FetchedValue,
    ForeignKey,
    Index,
    Integer,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import CIDR
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.model_types import RESOURCE_STATUS
from app.domain.enums import ResourceStatus
from app.modules.security_group_rules.enums import (
    SecurityGroupRuleDirection,
    SecurityGroupRuleProtocol,
)


class SecurityGroupRule(Base):
    __tablename__ = "security_group_rules"
    __table_args__ = (
        Index("ix_security_group_rules_security_group_id", "security_group_id"),
        Index("ix_security_group_rules_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    security_group_id: Mapped[UUID] = mapped_column(
        ForeignKey("security_groups.id", ondelete="RESTRICT"), nullable=False
    )
    direction: Mapped[SecurityGroupRuleDirection] = mapped_column(
        Enum(
            SecurityGroupRuleDirection,
            name="security_group_rule_direction",
            native_enum=True,
        ),
        nullable=False,
    )
    protocol: Mapped[SecurityGroupRuleProtocol] = mapped_column(
        Enum(
            SecurityGroupRuleProtocol,
            name="security_group_rule_protocol",
            native_enum=True,
        ),
        nullable=False,
    )
    port_range_from: Mapped[int | None] = mapped_column(Integer)
    port_range_to: Mapped[int | None] = mapped_column(Integer)
    cidr_block: Mapped[str] = mapped_column(CIDR, nullable=False)
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
