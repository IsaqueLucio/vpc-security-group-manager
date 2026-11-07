from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import ResourceStatus


class SecurityGroupCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    description: str | None = None


class SecurityGroupUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None

    @model_validator(mode="after")
    def validate_changes(self) -> "SecurityGroupUpdate":
        if not self.model_fields_set:
            raise ValueError("Informe ao menos um campo para atualizar.")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("O nome não pode ser nulo.")
        return self


class SecurityGroupResponse(BaseModel):
    id: UUID
    vpc_id: UUID
    name: str
    description: str | None
    status: ResourceStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
