from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.enums import ResourceStatus
from app.domain.networking import InvalidCIDRError, parse_ipv4_cidr
from app.modules.security_group_rules.enums import (
    SecurityGroupRuleDirection,
    SecurityGroupRuleProtocol,
)


class SecurityGroupRuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    direction: SecurityGroupRuleDirection
    protocol: SecurityGroupRuleProtocol
    port_range_from: int | None = Field(default=None, ge=0, le=65535)
    port_range_to: int | None = Field(default=None, ge=0, le=65535)
    cidr_block: str
    description: str | None = None

    @field_validator("cidr_block")
    @classmethod
    def validate_cidr(cls, value: str) -> str:
        try:
            return str(parse_ipv4_cidr(value))
        except InvalidCIDRError as exc:
            raise ValueError(str(exc)) from exc

    @model_validator(mode="after")
    def validate_ports(self) -> "SecurityGroupRuleCreate":
        if self.protocol in (
            SecurityGroupRuleProtocol.TCP,
            SecurityGroupRuleProtocol.UDP,
        ):
            if self.port_range_from is None or self.port_range_to is None:
                raise ValueError("TCP e UDP exigem port_range_from e port_range_to.")
            if self.port_range_from > self.port_range_to:
                raise ValueError("port_range_from deve ser menor ou igual a port_range_to.")
        elif self.port_range_from is not None or self.port_range_to is not None:
            raise ValueError("ICMP e ALL não aceitam intervalos de portas.")
        return self


class SecurityGroupRuleResponse(BaseModel):
    id: UUID
    security_group_id: UUID
    direction: SecurityGroupRuleDirection
    protocol: SecurityGroupRuleProtocol
    port_range_from: int | None
    port_range_to: int | None
    cidr_block: str
    description: str | None
    status: ResourceStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("cidr_block", mode="before")
    @classmethod
    def serialize_cidr(cls, value: object) -> str:
        return str(value)
