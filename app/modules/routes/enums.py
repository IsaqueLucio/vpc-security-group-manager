from enum import Enum


class RouteTargetType(str, Enum):
    LOCAL = "LOCAL"
    INTERNET_GATEWAY = "INTERNET_GATEWAY"
    NAT_GATEWAY = "NAT_GATEWAY"
