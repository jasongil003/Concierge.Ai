import asyncio

import pytest

from app.outbound_http import OutboundRequestBroker, OutboundRequestError


class FakeWriter:
    def __init__(self) -> None:
        self.data = b""

    def write(self, data: bytes) -> None:
        self.data += data

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        return None

    async def wait_closed(self) -> None:
        return None


def response_stream(status: int = 200, headers: dict[str, str] | None = None, body: bytes = b"ok") -> asyncio.StreamReader:
    reader = asyncio.StreamReader()
    values = {"Content-Length": str(len(body)), **(headers or {})}
    reader.feed_data(
        f"HTTP/1.1 {status} Status\r\n".encode()
        + b"".join(f"{key}: {value}\r\n".encode() for key, value in values.items())
        + b"\r\n"
        + body
    )
    reader.feed_eof()
    return reader


@pytest.mark.parametrize(
    ("url", "resolved"),
    [
        ("http://127.0.0.1/", ["127.0.0.1"]),
        ("http://localhost/", ["127.0.0.1"]),
        ("http://[::1]/", ["::1"]),
        ("http://10.0.0.1/", ["10.0.0.1"]),
        ("http://172.16.0.1/", ["172.16.0.1"]),
        ("http://192.168.1.1/", ["192.168.1.1"]),
        ("http://169.254.169.254/latest/meta-data/", ["169.254.169.254"]),
        ("http://metadata.google.internal/", ["169.254.169.254"]),
        ("http://2130706433/", ["127.0.0.1"]),
    ],
)
def test_private_and_metadata_destinations_are_blocked(url: str, resolved: list[str]):
    async def resolver(host: str, port: int) -> list[str]:
        del host, port
        return resolved

    with pytest.raises(OutboundRequestError, match="blocked"):
        asyncio.run(OutboundRequestBroker(resolver=resolver).post(url))


@pytest.mark.parametrize("url", ["ftp://example.com/", "file:///etc/passwd", "gopher://example.com/"])
def test_non_http_schemes_are_blocked(url: str):
    with pytest.raises(OutboundRequestError, match="HTTP"):
        asyncio.run(OutboundRequestBroker().post(url))


def test_non_standard_ports_are_blocked():
    with pytest.raises(OutboundRequestError, match="standard"):
        asyncio.run(OutboundRequestBroker().post("https://example.com:8443/hook"))


def test_redirect_from_public_url_to_private_ip_is_blocked():
    connector_calls: list[str] = []

    async def resolver(host: str, port: int) -> list[str]:
        del port
        return ["93.184.216.34"] if host == "public.example" else ["127.0.0.1"]

    async def connector(**kwargs):
        connector_calls.append(kwargs["host"])
        return response_stream(302, {"Location": "http://127.0.0.1/private"}, b""), FakeWriter()

    with pytest.raises(OutboundRequestError, match="blocked"):
        asyncio.run(OutboundRequestBroker(resolver=resolver, connector=connector).post("https://public.example/hook"))
    assert connector_calls == ["93.184.216.34"]


def test_dns_resolution_is_pinned_to_the_validated_connection_ip():
    resolver_calls = 0
    connected_ips: list[str] = []

    async def resolver(host: str, port: int) -> list[str]:
        nonlocal resolver_calls
        del host, port
        resolver_calls += 1
        return ["93.184.216.34"] if resolver_calls == 1 else ["127.0.0.1"]

    async def connector(**kwargs):
        connected_ips.append(kwargs["host"])
        return response_stream(), FakeWriter()

    response = asyncio.run(
        OutboundRequestBroker(resolver=resolver, connector=connector).post("https://public.example/hook", content=b"{}")
    )
    assert response.status_code == 200
    assert resolver_calls == 1
    assert connected_ips == ["93.184.216.34"]


@pytest.mark.parametrize("address", ["100.64.0.1", "198.18.0.1", "fd00::1"])
def test_non_global_special_use_addresses_are_blocked(address: str):
    async def resolver(host: str, port: int) -> list[str]:
        del host, port
        return [address]

    async def unexpected_connector(**kwargs):
        raise AssertionError(f"A non-global address was connected: {kwargs['host']}")

    bracketed = f"[{address}]" if ":" in address else address
    with pytest.raises(OutboundRequestError, match="blocked"):
        asyncio.run(OutboundRequestBroker(resolver=resolver, connector=unexpected_connector).post(f"http://{bracketed}/"))


def test_redirect_to_another_public_origin_is_blocked_before_forwarding_webhook():
    connector_calls: list[str] = []

    async def resolver(host: str, port: int) -> list[str]:
        del port
        return ["93.184.216.34"] if host == "webhook.example" else ["93.184.216.35"]

    async def connector(**kwargs):
        connector_calls.append(kwargs["host"])
        return response_stream(302, {"Location": "https://exfil.example/collect"}, b""), FakeWriter()

    with pytest.raises(OutboundRequestError, match="(?i)cross-origin outbound redirects"):
        asyncio.run(
            OutboundRequestBroker(resolver=resolver, connector=connector).post(
                "https://webhook.example/hook",
                content=b"guest-related payload",
                headers={"X-Concierge-Signature": "sha256=signature"},
            )
        )
    assert connector_calls == ["93.184.216.34"]


def test_same_origin_redirect_remains_supported():
    connector_calls = 0

    async def resolver(host: str, port: int) -> list[str]:
        del host, port
        return ["93.184.216.34"]

    async def connector(**kwargs):
        nonlocal connector_calls
        connector_calls += 1
        if connector_calls == 1:
            return response_stream(302, {"Location": "/next"}, b""), FakeWriter()
        return response_stream(200, body=b"delivered"), FakeWriter()

    response = asyncio.run(
        OutboundRequestBroker(resolver=resolver, connector=connector).post("https://webhook.example/hook")
    )
    assert response.status_code == 200
    assert response.content == b"delivered"
    assert connector_calls == 2


@pytest.mark.parametrize("header_value", ["safe\r\nX-Injected: yes", "bad\x7fvalue"])
def test_outbound_header_controls_are_rejected_before_network_activity(header_value: str):
    resolver_calls = 0
    connector_calls = 0

    async def resolver(host: str, port: int) -> list[str]:
        nonlocal resolver_calls
        resolver_calls += 1
        del host, port
        return ["93.184.216.34"]

    async def connector(**kwargs):
        nonlocal connector_calls
        connector_calls += 1
        return response_stream(), FakeWriter()

    with pytest.raises(OutboundRequestError, match="invalid header"):
        asyncio.run(
            OutboundRequestBroker(resolver=resolver, connector=connector).post(
                "https://webhook.example/hook",
                headers={"X-Test": header_value},
            )
        )
    assert resolver_calls == 0
    assert connector_calls == 0
