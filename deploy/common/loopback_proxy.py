#!/usr/bin/env python3
"""Small standard-library HTTP reverse proxy, bound exclusively to localhost."""

from __future__ import annotations

import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

UPSTREAM_HOST = "127.0.0.1"
UPSTREAM_PORT = 8081
MAX_BODY_BYTES = 30 * 1024 * 1024
HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def _forwarded_for(value: str, host_header: str, peer: str) -> str:
    supplied = value.strip()
    if supplied:
        return supplied
    try:
        hostname = (urlsplit(f"//{host_header}").hostname or "").casefold()
    except ValueError:
        hostname = ""
    if hostname in {"localhost", "127.0.0.1", "::1"}:
        return peer
    # A host TLS proxy must provide the real client address. Fail closed for
    # management CIDR checks if a public-host request omits that header.
    return "0.0.0.0"


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):  # noqa: N802
        self._forward()

    def do_HEAD(self):  # noqa: N802
        self._forward()

    def do_POST(self):  # noqa: N802
        self._forward()

    def do_PUT(self):  # noqa: N802
        self._forward()

    def do_PATCH(self):  # noqa: N802
        self._forward()

    def do_DELETE(self):  # noqa: N802
        self._forward()

    def do_OPTIONS(self):  # noqa: N802
        self._forward()

    def _forward(self) -> None:
        if self.headers.get("Transfer-Encoding"):
            self.send_error(501, "Chunked request bodies are not supported by this loopback proxy")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400, "Invalid Content-Length")
            return
        if length < 0 or length > MAX_BODY_BYTES:
            self.send_error(413, "Request body too large")
            return
        body = self.rfile.read(length) if length else None
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.casefold() not in HOP_BY_HOP and key.casefold() not in {"host", "x-forwarded-for"}
        }
        headers["Host"] = self.headers.get("Host", "127.0.0.1")
        headers["X-Forwarded-For"] = _forwarded_for(
            self.headers.get("X-Forwarded-For", ""),
            self.headers.get("Host", "127.0.0.1"),
            self.client_address[0],
        )
        headers["X-Forwarded-Proto"] = self.headers.get("X-Forwarded-Proto", "http")
        headers["X-Real-IP"] = self.client_address[0]
        headers["Connection"] = "close"

        try:
            upstream = http.client.HTTPConnection(UPSTREAM_HOST, UPSTREAM_PORT, timeout=90)
            upstream.request(self.command, self.path, body=body, headers=headers)
            response = upstream.getresponse()
        except (OSError, http.client.HTTPException):
            self.send_error(502, "Concierge application is not ready")
            return

        self.send_response(response.status, response.reason)
        for key, value in response.getheaders():
            if key.casefold() not in HOP_BY_HOP:
                self.send_header(key, value)
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            chunk = response.read(64 * 1024)
            while chunk:
                self.wfile.write(chunk)
                chunk = response.read(64 * 1024)
        response.close()
        upstream.close()
        self.close_connection = True

    def log_message(self, fmt: str, *args) -> None:
        # Avoid logging request bodies, query secrets, or hotel data.
        path = urlsplit(self.path).path
        print(f"{self.client_address[0]} {self.command} {path} {fmt % args}", flush=True)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8080), ProxyHandler).serve_forever()
