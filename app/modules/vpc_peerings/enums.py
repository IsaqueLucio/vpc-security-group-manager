from enum import Enum


class VpcPeeringStatus(str, Enum):
    PENDING_ACCEPTANCE = "PENDING_ACCEPTANCE"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    DELETED = "DELETED"
