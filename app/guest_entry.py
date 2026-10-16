from __future__ import annotations

import hashlib
import hmac
import re
from urllib.parse import urlencode, urlsplit

import qrcode
from qrcode.image.svg import SvgPathImage

from .guardrails import normalize_guest_hostname


def canonical_guest_entry_url(record: object) -> str | None:
    """Return the property's configured HTTPS origin when guest entry is enabled."""
    app_settings = getattr(record, "app_settings", None)
    deployment = app_settings.get("deployment", {}) if isinstance(app_settings, dict) else {}
    if not isinstance(deployment, dict) or deployment.get("guest_access_enabled", True) is False:
        return None
    if deployment.get("https_required", True) is False:
        return None

    raw_domain = str(getattr(record, "domain", "") or "")
    configured_url = str(deployment.get("public_base_url") or (f"https://{raw_domain}" if raw_domain else ""))
    if not configured_url or configured_url != configured_url.strip():
        return None
    try:
        parsed = urlsplit(configured_url)
        port = parsed.port
        hostname = normalize_guest_hostname(parsed.hostname or "")
        expected_domain = normalize_guest_hostname(raw_domain) if raw_domain else ""
    except (TypeError, ValueError):
        return None
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or (expected_domain and hostname != expected_domain)
    ):
        return None
    canonical_origin = f"https://{hostname}"
    return f"{canonical_origin}:{port}" if port and port != 443 else canonical_origin


def guest_entry_qr_svg(url: str) -> str:
    """Build a first-party, print-ready QR code for a configured guest URL."""
    code = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=4,
    )
    code.add_data(url)
    code.make(fit=True)
    image = code.make_image(image_factory=SvgPathImage)
    return image.to_string(encoding="unicode")


def signed_wayfinding_entry_url(
    record: object,
    node_id: str,
    property_secret: str,
) -> str | None:
    """Create a property-scoped QR URL for a published guest-visible node."""
    origin = canonical_guest_entry_url(record)
    property_id = str(getattr(record, "property_id", "") or "")
    if (
        origin is None
        or not property_id
        or len(property_id) > 120
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", str(node_id or ""))
        or not property_secret
    ):
        return None
    signing_key = hmac.new(
        property_secret.encode("utf-8"),
        b"concierge:guest-wayfinding-signing:v1",
        hashlib.sha256,
    ).digest()
    message = f"v1\n{property_id}\n{node_id}".encode("utf-8")
    signature = hmac.new(signing_key, message, hashlib.sha256).hexdigest()
    query = urlencode({
        "property_id": property_id,
        "start_node_id": node_id,
        "start_sig": signature,
    })
    return f"{origin}/?{query}"


def verify_wayfinding_start_signature(
    property_id: str,
    node_id: str,
    signature: str,
    property_secret: str,
) -> bool:
    """Verify a versioned wayfinding QR signature without disclosing key material."""
    if (
        not property_id
        or len(property_id) > 120
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", str(node_id or ""))
        or not re.fullmatch(r"[0-9a-f]{64}", str(signature or ""))
        or not property_secret
    ):
        return False
    signing_key = hmac.new(
        property_secret.encode("utf-8"),
        b"concierge:guest-wayfinding-signing:v1",
        hashlib.sha256,
    ).digest()
    message = f"v1\n{property_id}\n{node_id}".encode("utf-8")
    expected = hmac.new(signing_key, message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
