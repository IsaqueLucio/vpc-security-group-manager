from collections.abc import Mapping


AVAILABILITY_ZONES: Mapping[str, tuple[str, ...]] = {
    "sa-east-1": ("sa-east-1a", "sa-east-1b", "sa-east-1c"),
    "us-east-1": ("us-east-1a", "us-east-1b", "us-east-1c"),
    "us-west-2": ("us-west-2a", "us-west-2b", "us-west-2c"),
    "eu-west-1": ("eu-west-1a", "eu-west-1b", "eu-west-1c"),
}


class UnknownRegionError(ValueError):
    """Raised when a region has no availability-zone catalog."""


class InvalidAvailabilityZoneError(ValueError):
    """Raised when a zone does not belong to its VPC's region."""


def validate_availability_zone(region: str, availability_zone: str) -> None:
    zones = AVAILABILITY_ZONES.get(region)
    if zones is None:
        raise UnknownRegionError(f"A região {region!r} não possui zonas catalogadas.")
    if availability_zone not in zones:
        raise InvalidAvailabilityZoneError(
            f"A zona {availability_zone!r} não pertence à região {region!r}."
        )
