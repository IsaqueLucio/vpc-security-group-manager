"""Pure IPv4 networking validation and allocation helpers."""

import ipaddress
from collections.abc import Iterable
from typing import NamedTuple


class NetworkingDomainError(ValueError):
    """Base class for invalid networking inputs and operations."""


class InvalidCIDRError(NetworkingDomainError):
    """Raised when a value is not a canonical IPv4 CIDR."""


class PrefixLengthError(NetworkingDomainError):
    """Raised when a CIDR prefix is outside the permitted range."""


class AddressSpaceExhaustedError(NetworkingDomainError):
    """Raised when no free network or address remains in a parent network."""


_RESERVED_CIDRS = tuple(
    ipaddress.IPv4Network(cidr)
    for cidr in (
        "0.0.0.0/8",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "224.0.0.0/4",
        "240.0.0.0/4",
    )
)
_RFC1918_CIDRS = tuple(
    ipaddress.IPv4Network(cidr)
    for cidr in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)


def parse_ipv4_cidr(value: str | ipaddress.IPv4Network) -> ipaddress.IPv4Network:
    """Parse a canonical IPv4 CIDR, rejecting host bits and non-IPv4 values."""
    try:
        return ipaddress.IPv4Network(value, strict=True)
    except (TypeError, ValueError) as exc:
        raise InvalidCIDRError(f"CIDR IPv4 inválido ou não canônico: {value!r}") from exc


def _validate_prefix_bounds(min_prefix: int, max_prefix: int) -> None:
    if (
        isinstance(min_prefix, bool)
        or isinstance(max_prefix, bool)
        or not isinstance(min_prefix, int)
        or not isinstance(max_prefix, int)
        or not 0 <= min_prefix <= max_prefix <= 32
    ):
        raise PrefixLengthError("Os limites do prefixo devem satisfazer 0 <= mínimo <= máximo <= 32.")


def validate_prefix_length(
    cidr: str | ipaddress.IPv4Network,
    min_prefix: int,
    max_prefix: int,
) -> ipaddress.IPv4Network:
    """Parse a CIDR and validate its prefix against inclusive limits."""
    network = parse_ipv4_cidr(cidr)
    _validate_prefix_bounds(min_prefix, max_prefix)
    if not min_prefix <= network.prefixlen <= max_prefix:
        raise PrefixLengthError(
            f"O prefixo /{network.prefixlen} deve estar entre /{min_prefix} e /{max_prefix}."
        )
    return network


def is_reserved_cidr(cidr: str | ipaddress.IPv4Network) -> bool:
    """Return whether the entire CIDR is contained by a reserved block."""
    network = parse_ipv4_cidr(cidr)
    return any(network.subnet_of(reserved) for reserved in _RESERVED_CIDRS)


def is_private_cidr(cidr: str | ipaddress.IPv4Network) -> bool:
    """Return whether the entire CIDR is within an RFC 1918 private range."""
    network = parse_ipv4_cidr(cidr)
    return any(network.subnet_of(private) for private in _RFC1918_CIDRS)


def is_subnet_within_vpc(
    subnet_cidr: str | ipaddress.IPv4Network,
    vpc_cidr: str | ipaddress.IPv4Network,
) -> bool:
    """Return whether a subnet CIDR is wholly contained by its VPC CIDR."""
    subnet = parse_ipv4_cidr(subnet_cidr)
    vpc = parse_ipv4_cidr(vpc_cidr)
    return subnet.subnet_of(vpc)


def cidrs_overlap(
    first_cidr: str | ipaddress.IPv4Network,
    second_cidr: str | ipaddress.IPv4Network,
) -> bool:
    """Return whether two IPv4 CIDRs overlap, including full containment."""
    first = parse_ipv4_cidr(first_cidr)
    second = parse_ipv4_cidr(second_cidr)
    return first.overlaps(second)


def overlaps_any(
    cidr: str | ipaddress.IPv4Network,
    existing_cidrs: Iterable[str | ipaddress.IPv4Network],
) -> bool:
    """Return whether a CIDR overlaps any CIDR in an iterable."""
    network = parse_ipv4_cidr(cidr)
    return any(network.overlaps(parse_ipv4_cidr(existing)) for existing in existing_cidrs)


def first_fit_subnet(
    parent_cidr: str | ipaddress.IPv4Network,
    desired_prefix: int,
    occupied_cidrs: Iterable[str | ipaddress.IPv4Network] = (),
) -> ipaddress.IPv4Network:
    """Return the first free child CIDR in ascending network-address order."""
    parent = parse_ipv4_cidr(parent_cidr)
    _validate_prefix_bounds(desired_prefix, desired_prefix)
    if desired_prefix < parent.prefixlen:
        raise PrefixLengthError(
            f"O prefixo /{desired_prefix} não cabe dentro da rede pai /{parent.prefixlen}."
        )

    occupied = tuple(parse_ipv4_cidr(cidr) for cidr in occupied_cidrs)
    for candidate in parent.subnets(new_prefix=desired_prefix):
        if not any(candidate.overlaps(existing) for existing in occupied):
            return candidate

    raise AddressSpaceExhaustedError(
        f"Não há blocos /{desired_prefix} disponíveis dentro de {parent}."
    )


def first_fit_ip(
    subnet_cidr: str | ipaddress.IPv4Network,
    occupied_ips: Iterable[str | ipaddress.IPv4Address] = (),
) -> ipaddress.IPv4Address:
    """Return the first available IPv4 address, reserving four leading and one trailing IP."""
    subnet = validate_prefix_length(subnet_cidr, 16, 28)
    reserved = [
        ipaddress.IPv4Network((int(subnet.network_address) + offset, 32))
        for offset in range(4)
    ]
    reserved.append(ipaddress.IPv4Network((subnet.broadcast_address, 32)))
    occupied = [
        ipaddress.IPv4Network((parse_ipv4_cidr(f"{ip}/32").network_address, 32))
        if isinstance(ip, str)
        else ipaddress.IPv4Network((ip, 32))
        for ip in occupied_ips
    ]
    return first_fit_subnet(subnet, 32, (*reserved, *occupied)).network_address


class SubnetCapacity(NamedTuple):
    total_ips: int
    usable_ips: int


def calculate_subnet_capacity(cidr: str | ipaddress.IPv4Network) -> SubnetCapacity:
    """Calculate total and usable addresses for a supported subnet CIDR."""
    subnet = validate_prefix_length(cidr, 16, 28)
    total_ips = subnet.num_addresses
    return SubnetCapacity(total_ips=total_ips, usable_ips=total_ips - 5)
