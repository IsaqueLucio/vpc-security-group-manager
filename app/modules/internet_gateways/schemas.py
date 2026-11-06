from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.enums import ResourceStatus


class InternetGatewayResponse(BaseModel):
    id: UUID
    vpc_id: UUID
    status: ResourceStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
