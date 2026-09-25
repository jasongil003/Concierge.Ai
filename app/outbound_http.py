"""Pinned, policy-controlled HTTP/1.1 transport for untrusted destinations."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import ipaddress
import socket
import ssl
from typing import Any, Awaitable, Callable
from urllib.parse import urljoin, urlsplit, urlunsplit


AuditCallback = Callable[[str, dict[str, Any]], None]
Resolver = Callable[[str, int], Awaitable[list[str]]]
Connector = Callable[..., Awaitable[tuple[asyncio.StreamReader, asyncio.StreamWriter]]]


@dataclass(frozen=True)
class OutboundResponse:
    status_code: int
    headers: dict[str, str]
    content: bytes
    url: str


class OutboundRequestError(RuntimeError):
    pass


class OutboundRequestBroker:
    """Resolve once, validate every address, and connect to the selected validated IP."""

    REDIRECTS = {301, 302, 303, 307, 308}

    def __init__(
        self,
        *,
        timeout_seconds: float = 8.0,
        max_redirects: int = 3,
        max_response_bytes: int = 1_000_000,
        user_agent: str = "Concierge.Ai-Outbound/1.0",
        resolver: Resolver | None = None,
        connector: Connector | None = None,
        audit: AuditCallback | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_redirects = max_redirects
        self.max_response_bytes = max_response_bytes
        self.user_agent = user_agent
        self._resolver = resolver or self._resolve
        self._connector = connector or asyncio.open_connection
        self._audit = audit or (lambda event, metadata: None)

    async def post(self, url: str, *, content: bytes = b"", headers: dict[str, str] | None = None) -> OutboundResponse:
        current = url
        for redirect_count in range(self.max_redirects + 1):
            response = await self._request_once(current, content, headers or {})
            location = response.headers.get("location")
            if response.status_code not in self.REDIRECTS or not location:
                return response
            if redirect_count >= self.max_redirects:
                self._audit("outbound_redirect_blocked", {"host": urlsplit(current).hostname, "reason": "redirect_limit"})
                raise OutboundRequestError("Outbound redirect limit exceeded.")
            current = urljoin(current, location)
            self._audit("outbound_redirect", {"from_host": urlsplit(response.url).hostname, "to_host": urlsplit(current).hostname})
        raise OutboundRequestError("Outbound redirect limit exceeded.")

    @staticmethod
    async def _resolve(hostname: str, port: int) -> list[str]:
        loop = asyncio.get_running_loop()
        records = await loop.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        return list(dict.fromkeys(record[4][0] for record in records))

    @staticmethod
    def _blocked_address(value: str) -> bool:
        address = ipaddress.ip_address(value)
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        return any((
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        ))

    async def _request_once(self, url: str, content: bytes, supplied_headers: dict[str, str]) -> OutboundResponse:
        parsed = urlsplit(str(url).strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise OutboundRequestError("Only credential-free HTTP(S) URLs are allowed.")
        try:
            explicit_port = parsed.port
        except ValueError as exc:
            raise OutboundRequestError("Outbound URL contains an invalid port.") from exc
        port = explicit_port or (443 if parsed.scheme == "https" else 80)
        if port not in {80, 443}:
            raise OutboundRequestError("Only standard HTTP(S) ports are allowed.")
        hostname = parsed.hostname.casefold().rstrip(".")
        if hostname == "localhost" or hostname.endswith(".localhost"):
            self._audit("outbound_request_blocked", {"host": hostname, "reason": "localhost"})
            raise OutboundRequestError("Local and internal destinations are blocked.")
        try:
            addresses = await asyncio.wait_for(self._resolver(hostname, port), timeout=self.timeout_seconds)
        except (OSError, asyncio.TimeoutError) as exc:
            raise OutboundRequestError("Destination host could not be resolved safely.") from exc
        if not addresses:
            raise OutboundRequestError("Destination host did not resolve to an address.")
        try:
            blocked = [value for value in addresses if self._blocked_address(value)]
        except ValueError as exc:
            raise OutboundRequestError("Destination resolved to an invalid address.") from exc
        if blocked:
            self._audit("outbound_request_blocked", {"host": hostname, "reason": "non_public_address"})
            raise OutboundRequestError("Private, local, metadata, and management destinations are blocked.")
        selected_ip = addresses[0]
        ssl_context = ssl.create_default_context() if parsed.scheme == "https" else None
        connect_args: dict[str, Any] = {"host": selected_ip, "port": port, "ssl": ssl_context}
        if ssl_context is not None:
            connect_args["server_hostname"] = hostname
        try:
            reader, writer = await asyncio.wait_for(self._connector(**connect_args), timeout=self.timeout_seconds)
            host_header = hostname
            if explicit_port and explicit_port != (443 if parsed.scheme == "https" else 80):
                host_header = f"{hostname}:{explicit_port}"
            target = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
            headers = {
                "Host": host_header,
                "User-Agent": self.user_agent,
                "Accept": "*/*",
                "Accept-Encoding": "identity",
                "Connection": "close",
                "Content-Length": str(len(content)),
                **{str(key): str(value) for key, value in supplied_headers.items() if key.casefold() not in {"host", "content-length", "connection"}},
            }
            request_bytes = (
                f"POST {target} HTTP/1.1\r\n"
                + "".join(f"{key}: {value}\r\n" for key, value in headers.items())
                + "\r\n"
            ).encode("ascii") + content
            writer.write(request_bytes)
            await asyncio.wait_for(writer.drain(), timeout=self.timeout_seconds)
            response = await asyncio.wait_for(self._read_response(reader, url), timeout=self.timeout_seconds)
            self._audit("outbound_request_completed", {"host": hostname, "status_code": response.status_code})
            return response
        except (OSError, asyncio.TimeoutError, ssl.SSLError, ValueError) as exc:
            raise OutboundRequestError("Outbound request failed safely.") from exc
        finally:
            if "writer" in locals():
                writer.close()
                try:
                    await writer.wait_closed()
                except (OSError, ssl.SSLError):
                    pass

    async def _read_response(self, reader: asyncio.StreamReader, url: str) -> OutboundResponse:
        status_line = await reader.readline()
        if len(status_line) > 8_192 or not status_line.startswith(b"HTTP/"):
            raise OutboundRequestError("Invalid outbound HTTP response.")
        try:
            status_code = int(status_line.split(b" ", 2)[1])
        except (IndexError, ValueError) as exc:
            raise OutboundRequestError("Invalid outbound HTTP status.") from exc
        raw_headers = await reader.readuntil(b"\r\n\r\n")
        if len(raw_headers) > 65_536:
            raise OutboundRequestError("Outbound response headers are too large.")
        headers: dict[str, str] = {}
        for line in raw_headers[:-4].split(b"\r\n"):
            if not line:
                continue
            name, separator, value = line.partition(b":")
            if not separator:
                raise OutboundRequestError("Invalid outbound response header.")
            headers[name.decode("latin-1").strip().casefold()] = value.decode("latin-1").strip()
        length_header = headers.get("content-length")
        if length_header is not None:
            length = int(length_header)
            if length < 0 or length > self.max_response_bytes:
                raise OutboundRequestError("Outbound response exceeds the size limit.")
            body = await reader.readexactly(length)
        else:
            body = await reader.read(self.max_response_bytes + 1)
            if len(body) > self.max_response_bytes:
                raise OutboundRequestError("Outbound response exceeds the size limit.")
        return OutboundResponse(status_code, headers, body, url)
