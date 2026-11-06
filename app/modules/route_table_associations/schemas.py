from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.enums import ResourceStatus


class RouteTableAssociationCreate(BaseModel):
    route_table_id: UUID


class RouteTableAssociationResponse(BaseModel):
    id: UUID
    subnet_id: UUID
    route_table_id: UUID
    status: ResourceStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
