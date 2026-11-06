from datetime import datetime
from ipaddress import IPv4Address
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import ResourceStatus


class IPAllocationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ip_address: IPv4Address | None = None
    description: str | None = Field(default=None, max_length=500)


class IPAllocationResponse(BaseModel):
    id: UUID
    subnet_id: UUID
    ip_address: IPv4Address
    description: str | None
    status: ResourceStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
