from enum import Enum


class SubnetType(str, Enum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
