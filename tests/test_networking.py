import ipaddress

import pytest

from app.domain.networking import (
    AddressSpaceExhaustedError,
    InvalidCIDRError,
    PrefixLengthError,
    calculate_subnet_capacity,
    cidrs_overlap,
    first_fit_ip,
    first_fit_subnet,
    is_private_cidr,
    is_reserved_cidr,
    is_subnet_within_vpc,
    overlaps_any,
    parse_ipv4_cidr,
    validate_prefix_length,
)


def test_parse_ipv4_cidr_accepts_canonical_ipv4_network() -> None:
    assert parse_ipv4_cidr("10.0.0.0/16") == ipaddress.IPv4Network("10.0.0.0/16")


@pytest.mark.parametrize("cidr", ["10.0.5.0/16", "2001:db8::/32", "not-a-cidr"])
def test_parse_ipv4_cidr_rejects_noncanonical_or_non_ipv4_values(cidr: str) -> None:
    with pytest.raises(InvalidCIDRError, match="não canônico"):
        parse_ipv4_cidr(cidr)


def test_validate_prefix_length_accepts_inclusive_boundaries() -> None:
    assert validate_prefix_length("10.0.0.0/16", 16, 28).prefixlen == 16
    assert validate_prefix_length("10.0.0.0/28", 16, 28).prefixlen == 28


@pytest.mark.parametrize("cidr", ["10.0.0.0/15", "10.0.0.0/29"])
def test_validate_prefix_length_rejects_values_outside_allowed_range(cidr: str) -> None:
    with pytest.raises(PrefixLengthError):
        validate_prefix_length(cidr, 16, 28)


def test_validate_prefix_length_rejects_invalid_limits() -> None:
    with pytest.raises(PrefixLengthError, match="limites"):
        validate_prefix_length("10.0.0.0/24", 28, 16)


@pytest.mark.parametrize(
    "cidr",
    [
        "0.1.0.0/16",
        "127.0.0.0/16",
        "169.254.1.0/24",
        "224.0.0.0/24",
        "240.0.0.0/24",
    ],
)
def test_is_reserved_cidr_detects_networks_contained_in_reserved_ranges(cidr: str) -> None:
    assert is_reserved_cidr(cidr)


def test_is_reserved_cidr_does_not_match_noncontained_or_public_networks() -> None:
    assert not is_reserved_cidr("0.0.0.0/7")
    assert not is_reserved_cidr("8.8.8.0/24")


@pytest.mark.parametrize("cidr", ["10.0.0.0/16", "172.16.0.0/16", "192.168.1.0/24"])
def test_is_private_cidr_recognizes_rfc1918_ranges(cidr: str) -> None:
    assert is_private_cidr(cidr)


def test_is_private_cidr_recognizes_public_network() -> None:
    assert not is_private_cidr("8.8.8.0/24")


def test_is_subnet_within_vpc_checks_full_containment() -> None:
    assert is_subnet_within_vpc("10.0.1.0/24", "10.0.0.0/16")
    assert not is_subnet_within_vpc("10.1.0.0/24", "10.0.0.0/16")


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        ("10.0.0.0/16", "10.0.0.0/16", True),
        ("10.0.0.0/24", "10.0.0.128/25", True),
        ("10.0.0.0/24", "10.0.1.0/24", False),
    ],
)
def test_cidrs_overlap(first: str, second: str, expected: bool) -> None:
    assert cidrs_overlap(first, second) is expected


def test_overlaps_any_checks_existing_cidr_list() -> None:
    assert overlaps_any("10.0.1.0/24", ["10.0.0.0/24", "10.0.1.128/25"])
    assert not overlaps_any("10.0.2.0/24", ["10.0.0.0/24", "10.0.1.0/24"])


def test_first_fit_subnet_returns_first_gap_in_ascending_order() -> None:
    result = first_fit_subnet(
        "10.0.0.0/16",
        24,
        ["10.0.0.0/24", "10.0.2.0/24"],
    )
    assert result == ipaddress.IPv4Network("10.0.1.0/24")


def test_first_fit_subnet_skips_partial_overlap() -> None:
    result = first_fit_subnet("10.0.0.0/16", 24, ["10.0.0.128/25"])
    assert result == ipaddress.IPv4Network("10.0.1.0/24")


def test_first_fit_subnet_reports_exhaustion_explicitly() -> None:
    with pytest.raises(AddressSpaceExhaustedError, match="Não há blocos"):
        first_fit_subnet(
            "10.0.0.0/24",
            25,
            ["10.0.0.0/25", "10.0.0.128/25"],
        )


def test_first_fit_subnet_rejects_child_prefix_larger_than_parent_network() -> None:
    with pytest.raises(PrefixLengthError, match="não cabe"):
        first_fit_subnet("10.0.0.0/24", 23)


def test_first_fit_ip_skips_five_reserved_subnet_addresses() -> None:
    assert first_fit_ip("10.0.0.0/28") == ipaddress.IPv4Address("10.0.0.4")
    assert first_fit_ip("10.0.0.0/28", ["10.0.0.4", "10.0.0.5"]) == ipaddress.IPv4Address(
        "10.0.0.6"
    )


def test_first_fit_ip_reports_exhaustion_when_all_usable_addresses_are_occupied() -> None:
    occupied_ips = [f"10.0.0.{host}" for host in range(4, 15)]
    with pytest.raises(AddressSpaceExhaustedError):
        first_fit_ip("10.0.0.0/28", occupied_ips)


@pytest.mark.parametrize("cidr", ["10.0.0.0/24", "10.0.0.0/28"])
def test_calculate_subnet_capacity_reserves_five_addresses(cidr: str) -> None:
    capacity = calculate_subnet_capacity(cidr)
    assert capacity.total_ips == ipaddress.IPv4Network(cidr).num_addresses
    assert capacity.usable_ips == capacity.total_ips - 5


def test_smallest_supported_subnet_has_at_least_eleven_usable_ips() -> None:
    assert calculate_subnet_capacity("10.0.0.0/28").usable_ips == 11


def test_calculate_subnet_capacity_rejects_prefix_outside_supported_range() -> None:
    with pytest.raises(PrefixLengthError):
        calculate_subnet_capacity("10.0.0.0/29")
