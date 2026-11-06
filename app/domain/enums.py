from enum import Enum


class ResourceStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    ERROR = "ERROR"
    DELETED = "DELETED"
