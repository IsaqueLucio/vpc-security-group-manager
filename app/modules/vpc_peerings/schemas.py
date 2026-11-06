from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.modules.vpc_peerings.enums import VpcPeeringStatus


class VpcPeeringCreate(BaseModel):
    requester_vpc_id: UUID
    accepter_vpc_id: UUID


class VpcPeeringUpdate(BaseModel):
    status: VpcPeeringStatus


class VpcPeeringResponse(BaseModel):
    id: UUID
    requester_vpc_id: UUID
    accepter_vpc_id: UUID
    status: VpcPeeringStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
