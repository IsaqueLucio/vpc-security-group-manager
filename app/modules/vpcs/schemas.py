from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.vpcs.vpc_enum import AWSRegion, SubnetType, VpcStatus


class VPCCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=3, max_length=100, examples=["production-vpc"])
    cidr_block: str = Field(examples=["10.0.0.0/16"])
    description: str | None = Field(
        default=None,
        examples=["Main VPC for production workloads"],
    )
    region: AWSRegion


class VPCUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(
        default=None,
        min_length=3,
        max_length=100,
        examples=["updated-vpc-name"],
    )
    description: str | None = Field(default=None, examples=["Updated description"])

    @model_validator(mode="after")
    def validate_changes(self) -> "VPCUpdate":
        if not self.model_fields_set:
            raise ValueError("Informe ao menos um campo para atualizar.")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("O nome não pode ser nulo.")
        return self


class VPCResponse(BaseModel):
    id: UUID
    name: str
    cidr_block: str
    description: str | None
    region: AWSRegion
    status: VpcStatus
    created_at: datetime
    updated_at: datetime
    warnings: list[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

    @field_validator("cidr_block", mode="before")
    @classmethod
    def serialize_cidr(cls, value: object) -> str:
        return str(value)


class SubnetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    type: SubnetType
    cidr_block: str | None = None
    prefix_length: int | None = Field(default=None, ge=16, le=28)
    availability_zone: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_allocation_mode(self) -> "SubnetCreate":
        if self.cidr_block is not None and self.prefix_length is not None:
            raise ValueError("Informe cidr_block ou prefix_length, não ambos.")
        return self


class SubnetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    type: SubnetType | None = None

    @model_validator(mode="after")
    def validate_changes(self) -> "SubnetUpdate":
        if not self.model_fields_set:
            raise ValueError("Informe ao menos um campo para atualizar.")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("O nome não pode ser nulo.")
        if "type" in self.model_fields_set and self.type is None:
            raise ValueError("O tipo não pode ser nulo.")
        return self


class SubnetResponse(BaseModel):
    id: UUID
    vpc_id: UUID
    name: str
    cidr_block: str
    type: SubnetType
    availability_zone: str | None
    status: VpcStatus
    created_at: datetime
    updated_at: datetime
    total_ips: int
    usable_ips: int
    available_ips: int

    model_config = ConfigDict(from_attributes=True)

    @field_validator("cidr_block", mode="before")
    @classmethod
    def serialize_cidr(cls, value: object) -> str:
        return str(value)