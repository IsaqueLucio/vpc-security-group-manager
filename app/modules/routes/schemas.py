from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.domain.enums import ResourceStatus
from app.modules.routes.enums import RouteTargetType


class RouteCreate(BaseModel):
    destination_cidr: str
    target_type: RouteTargetType
    target_id: UUID | None = None


class RouteResponse(BaseModel):
    id: UUID
    route_table_id: UUID
    destination_cidr: str
    target_type: RouteTargetType
    target_id: UUID | None
    status: ResourceStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("destination_cidr", mode="before")
    @classmethod
    def serialize_cidr(cls, value: object) -> str:
        return str(value)
