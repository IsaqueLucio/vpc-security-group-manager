from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import ResourceStatus


class RouteTableCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class RouteTableResponse(BaseModel):
    id: UUID
    vpc_id: UUID
    name: str
    status: ResourceStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
