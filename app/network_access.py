"""Network access policy helpers for management and guest traffic.

Management policy is installation-wide. Guest policy remains property scoped in
the existing property guardrails configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import socket
import sys
from typing import Any, Iterable


DEFAULT_MANAGEMENT_CIDRS = (
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "fc00::/7",
    "127.0.0.0/8",
    "::1/128",
)


def normalize_cidrs(values: Any, field: str, *, allow_empty: bool = True) -> list[str]:
    if values in (None, ""):
        values = []
    if not isinstance(values, (list, tuple)):
        raise ValueError(f"{field} must be a list of CIDR ranges.")
    if len(values) > 64:
        raise ValueError(f"{field} supports at most 64 ranges.")
    result: list[str] = []
    for value in values:
        try:
            network = ipaddress.ip_network(str(value).strip(), strict=False)
        except ValueError as exc:
            raise ValueError(f"Invalid CIDR in {field}.") from exc
        normalized = str(network)
        if normalized in result:
            raise ValueError(f"Duplicate CIDR in {field}: {normalized}.")
        result.append(normalized)
    if not allow_empty and not result:
        raise ValueError(f"{field} must contain at least one CIDR range.")
    return result


def normalize_management_access(
    config: dict[str, Any] | None,
    *,
    default_allowed_cidrs: Iterable[str] = DEFAULT_MANAGEMENT_CIDRS,
    default_trusted_proxy_ranges: Iterable[str] = (),
) -> dict[str, Any]:
    raw = dict(config or {})
    allowed = raw.get("management_allowed_cidrs", list(default_allowed_cidrs))
    trusted = raw.get("management_trusted_proxy_ranges", list(default_trusted_proxy_ranges))
    return {
        "management_access_enabled": bool(raw.get("management_access_enabled", True)),
        "management_allowed_cidrs": normalize_cidrs(allowed, "management_allowed_cidrs"),
        "management_trusted_proxy_ranges": normalize_cidrs(trusted, "management_trusted_proxy_ranges"),
    }


def find_network_overlaps(left: Iterable[str], right: Iterable[str]) -> list[tuple[str, str]]:
    overlaps: list[tuple[str, str]] = []
    for left_value in left:
        left_network = ipaddress.ip_network(left_value, strict=False)
        for right_value in right:
            right_network = ipaddress.ip_network(right_value, strict=False)
            if left_network.version == right_network.version and left_network.overlaps(right_network):
                overlaps.append((str(left_network), str(right_network)))
    return overlaps


def unsafe_management_networks(values: Iterable[str]) -> list[str]:
    return [
        str(network)
        for value in values
        if (network := ipaddress.ip_network(value, strict=False)).prefixlen == 0 or network.is_global
    ]


@dataclass(frozen=True)
class ManagementAccessDecision:
    allowed: bool
    client_ip: str
    matched_network: str = ""
    trusted_proxy: bool = False


class ManagementAccessGuard:
    """Resolve client addresses only through explicitly trusted proxy ranges."""

    @staticmethod
    def _matching_network(
        address: ipaddress.IPv4Address | ipaddress.IPv6Address,
        ranges: Iterable[str],
    ) -> str:
        for value in ranges:
            network = ipaddress.ip_network(value, strict=False)
            if address.version == network.version and address in network:
                return str(network)
        return ""

    def client_ip(self, direct_ip: str, headers: Any, config: dict[str, Any]) -> tuple[str, bool]:
        if direct_ip == "testclient":
            direct_ip = "127.0.0.1"
        try:
            peer = ipaddress.ip_address(direct_ip)
        except ValueError:
            return "", False

        trusted_ranges = config.get("management_trusted_proxy_ranges", [])
        if not self._matching_network(peer, trusted_ranges):
            # Ignore forwarding headers entirely when the socket peer is not trusted.
            return str(peer), False

        forwarded = str(headers.get("x-forwarded-for", ""))
        if not forwarded:
            return "", True
        chain: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
        for item in forwarded.split(","):
            try:
                chain.append(ipaddress.ip_address(item.strip()))
            except ValueError:
                # A malformed chain is not safe to interpret.
                return "", True
        if not chain:
            return "", True
        for candidate in reversed(chain):
            if not self._matching_network(candidate, trusted_ranges):
                return str(candidate), True
        # The chain contains no identifiable client. Do not treat a proxy as one.
        return "", True

    def evaluate(
        self,
        direct_ip: str,
        headers: Any,
        config: dict[str, Any],
        *,
        excluded_cidrs: Iterable[str] = (),
    ) -> ManagementAccessDecision:
        try:
            policy = normalize_management_access(
                config,
                default_allowed_cidrs=(),
                default_trusted_proxy_ranges=(),
            )
        except (TypeError, ValueError):
            # Corrupt policy must never widen access.
            return ManagementAccessDecision(False, "")
        client_ip, trusted_proxy = self.client_ip(direct_ip, headers, policy)
        try:
            address = ipaddress.ip_address(client_ip)
        except ValueError:
            if not policy["management_access_enabled"]:
                return ManagementAccessDecision(True, client_ip, "restriction_disabled", trusted_proxy)
            return ManagementAccessDecision(False, client_ip, "", trusted_proxy)
        excluded = self._matching_network(address, excluded_cidrs)
        if excluded:
            return ManagementAccessDecision(False, client_ip, "", trusted_proxy)
        if not policy["management_access_enabled"]:
            return ManagementAccessDecision(True, client_ip, "restriction_disabled", trusted_proxy)
        matched = self._matching_network(address, policy["management_allowed_cidrs"])
        return ManagementAccessDecision(bool(matched), client_ip, matched, trusted_proxy)


def detected_server_network() -> dict[str, str]:
    """Detect a private host address without changing host networking."""
    addresses: list[tuple[int, str]] = []
    for family, target in (
        (socket.AF_INET, ("192.0.2.1", 9)),
        (socket.AF_INET6, ("2001:db8::1", 9, 0, 0)),
    ):
        try:
            sock = socket.socket(family=family, type=socket.SOCK_DGRAM)
            try:
                sock.connect(target)
                value = sock.getsockname()[0]
            finally:
                sock.close()
            address = ipaddress.ip_address(value)
            if address.is_private and not address.is_loopback and not address.is_link_local:
                addresses.append((0 if address.version == 4 else 1, str(address)))
        except (OSError, ValueError):
            continue
    if not addresses:
        return {"server_ip": "", "network_interface": ""}

    addresses.sort()
    server_ip = addresses[0][1]
    interface = ""
    try:
        import psutil  # type: ignore[import-not-found]

        for name, entries in psutil.net_if_addrs().items():
            if any(entry.address.split("%", 1)[0] == server_ip for entry in entries):
                interface = name
                break
    except ImportError:
        if sys.platform.startswith(("linux", "darwin")):
            try:
                import fcntl
                import struct

                ioctl_get_interface_address = 0x8915 if sys.platform.startswith("linux") else 0xC0206921
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    for _, name in socket.if_nameindex():
                        request = struct.pack("256s", name.encode("utf-8")[:15])
                        result = fcntl.ioctl(sock.fileno(), ioctl_get_interface_address, request)
                        if socket.inet_ntoa(result[20:24]) == server_ip:
                            interface = name
                            break
            except (OSError, ImportError):
                pass
    return {"server_ip": server_ip, "network_interface": interface}
