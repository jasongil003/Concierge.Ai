from __future__ import annotations

import importlib.util
from pathlib import Path


PROXY_PATH = Path(__file__).resolve().parents[1] / "deploy" / "common" / "loopback_proxy.py"


def _load_proxy_module():
    spec = importlib.util.spec_from_file_location("concierge_loopback_proxy", PROXY_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_loopback_proxy_keeps_localhost_admin_reachable():
    proxy = _load_proxy_module()
    assert proxy._forwarded_for("", "127.0.0.1:8080", "127.0.0.1") == "127.0.0.1"
    assert proxy._forwarded_for("", "[::1]:8080", "::1") == "::1"


def test_loopback_proxy_fails_closed_for_public_host_without_client_ip():
    proxy = _load_proxy_module()
    assert proxy._forwarded_for("", "concierge.hotel.example", "127.0.0.1") == "0.0.0.0"
    assert proxy._forwarded_for("198.51.100.42", "concierge.hotel.example", "127.0.0.1") == "198.51.100.42"
