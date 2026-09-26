from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass
import hashlib
import hmac
import ipaddress
import json
import re
import socket
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

from redis.asyncio import Redis
from redis.backoff import NoBackoff
from redis.exceptions import RedisError
from redis.retry import Retry

from .database import connect_database
from . import metrics


DEFAULT_GUARDRAILS: dict[str, Any] = {
    "guest_network_only": True,
    "allowed_cidrs": ["127.0.0.0/8", "::1/128"],
    "trusted_proxy_ranges": [],
    "session_network_revalidation": "suspend",
    "guest_session_timeout": 30,
    "antlabs_gateway_enabled": False,
    "antlabs_gateway_ranges": [],
    "antlabs_signature_secret": "",
    "internet_search_enabled": True,
    "directions_enabled": True,
    "restaurant_search_enabled": True,
    "attractions_enabled": True,
    "weather_enabled": True,
    "service_requests_enabled": True,
    "reservations_enabled": False,
    "financial_actions_enabled": False,
    "human_escalation_enabled": True,
    "location_access_enabled": False,
    "audit_logging_enabled": True,
}

SECRET_KEYS = {
    "password", "secret", "token", "api_key", "apikey", "authorization",
    "cookie", "credential", "private_key", "cvv", "pin", "otp",
}


def _cidr_list(values: Any, field: str) -> list[str]:
    if values in (None, ""):
        return []
    if not isinstance(values, list):
        raise ValueError(f"{field} must be a list of CIDR ranges.")
    if len(values) > 64:
        raise ValueError(f"{field} supports at most 64 ranges.")
    result: list[str] = []
    for value in values:
        try:
            network = ipaddress.ip_network(str(value).strip(), strict=False)
        except ValueError as exc:
            raise ValueError(f"Invalid CIDR in {field}: {value}") from exc
        normalized = str(network)
        if normalized not in result:
            result.append(normalized)
    return result


def normalize_guardrails(config: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(config or {})
    raw.pop("antlabs_signature_configured", None)
    normalized = {**DEFAULT_GUARDRAILS, **raw}
    normalized["allowed_cidrs"] = _cidr_list(normalized.get("allowed_cidrs"), "allowed_cidrs")
    normalized["trusted_proxy_ranges"] = _cidr_list(normalized.get("trusted_proxy_ranges"), "trusted_proxy_ranges")
    normalized["antlabs_gateway_ranges"] = _cidr_list(normalized.get("antlabs_gateway_ranges"), "antlabs_gateway_ranges")
    policy = str(normalized.get("session_network_revalidation", "suspend")).lower()
    if policy not in {"suspend", "expire"}:
        raise ValueError("session_network_revalidation must be 'suspend' or 'expire'.")
    normalized["session_network_revalidation"] = policy
    timeout = int(normalized.get("guest_session_timeout", 30))
    if timeout < 5 or timeout > 1440:
        raise ValueError("guest_session_timeout must be between 5 and 1440 minutes.")
    normalized["guest_session_timeout"] = timeout
    for key, default in DEFAULT_GUARDRAILS.items():
        if isinstance(default, bool):
            normalized[key] = bool(normalized.get(key, default))
    secret = str(normalized.get("antlabs_signature_secret") or "")
    normalized["antlabs_signature_secret"] = secret[:512]
    return normalized


def public_guardrails(config: dict[str, Any] | None) -> dict[str, Any]:
    result = normalize_guardrails(config)
    result["antlabs_signature_configured"] = bool(result.pop("antlabs_signature_secret", ""))
    return result


@dataclass(frozen=True)
class GuardrailDecision:
    allowed: bool
    reason: str
    policy: str
    property_id: str | None
    action_level: int
    confirmation_required: bool
    escalation_required: bool
    request_id: str
    client_ip: str = ""
    matched_network: str = ""
    trusted_proxy: bool = False

    def payload(self, guest_safe: bool = True) -> dict[str, Any]:
        data = asdict(self)
        data["propertyId"] = data.pop("property_id")
        data["actionLevel"] = data.pop("action_level")
        data["confirmationRequired"] = data.pop("confirmation_required")
        data["escalationRequired"] = data.pop("escalation_required")
        data["requestId"] = data.pop("request_id")
        if guest_safe:
            data.pop("client_ip", None)
            data.pop("matched_network", None)
            data.pop("trusted_proxy", None)
        return data


class GuardrailDenied(Exception):
    def __init__(self, decision: GuardrailDecision, status_code: int = 403) -> None:
        super().__init__(decision.reason)
        self.decision = decision
        self.status_code = status_code


class NetworkGuard:
    @staticmethod
    def _contains(address: ipaddress.IPv4Address | ipaddress.IPv6Address, ranges: Iterable[str]) -> str:
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
            return direct_ip, False
        trusted_ranges = config.get("trusted_proxy_ranges", [])
        if not self._contains(peer, trusted_ranges):
            return str(peer), False
        forwarded = str(headers.get("x-forwarded-for", ""))
        chain: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
        for item in forwarded.split(","):
            try:
                chain.append(ipaddress.ip_address(item.strip()))
            except ValueError:
                return str(peer), True
        if not chain:
            return str(peer), True
        for candidate in reversed(chain):
            if not self._contains(candidate, trusted_ranges):
                return str(candidate), True
        return str(chain[0]), True

    def evaluate(
        self,
        property_id: str,
        config: dict[str, Any] | None,
        direct_ip: str,
        headers: Any,
        request_id: str,
        action_level: int = 1,
    ) -> GuardrailDecision:
        policy = normalize_guardrails(config)
        client_ip, trusted_proxy = self.client_ip(direct_ip, headers, policy)
        if not policy["guest_network_only"]:
            return GuardrailDecision(True, "network_policy_disabled", "network_access", property_id, action_level, False, False, request_id, client_ip, "disabled", trusted_proxy)
        try:
            address = ipaddress.ip_address(client_ip)
        except ValueError:
            return GuardrailDecision(False, "Guest network could not be verified.", "network_access", property_id, action_level, False, False, request_id, client_ip, "", trusted_proxy)
        matched = self._contains(address, policy["allowed_cidrs"])
        if not matched:
            return GuardrailDecision(False, "Concierge.AI is available only while connected to the hotel guest Wi-Fi network.", "network_access", property_id, action_level, False, False, request_id, client_ip, "", trusted_proxy)
        return GuardrailDecision(True, "approved_network", "network_access", property_id, action_level, False, False, request_id, client_ip, matched, trusted_proxy)


class PropertyGuard:
    @staticmethod
    def resolve(
        records: Iterable[Any],
        default_property_id: str,
        host: str,
        supplied_property_id: str | None = None,
        *,
        allow_body_selection: bool = False,
    ) -> Any:
        hostname = host.split(":", 1)[0].lower().rstrip(".")
        record_list = list(records)
        host_record = next((item for item in record_list if str(getattr(item, "domain", "")).lower().rstrip(".") == hostname and hostname), None)
        if host_record is not None:
            if supplied_property_id and supplied_property_id != host_record.property_id:
                raise PermissionError("Property does not match the guest hostname.")
            return host_record
        if not record_list:
            raise ValueError("No property is configured.")
        if default_property_id:
            configured = next((item for item in record_list if item.property_id == default_property_id), None)
            configured_domain = str(getattr(configured, "domain", "") or "").lower().rstrip(".") if configured is not None else ""
            if configured is not None and (not configured_domain or hostname == configured_domain):
                if supplied_property_id and supplied_property_id != configured.property_id:
                    if allow_body_selection:
                        selected = next((item for item in record_list if item.property_id == supplied_property_id), None)
                        if selected is not None:
                            return selected
                    raise ValueError("Property not found.")
                return configured
        if not supplied_property_id and not default_property_id and len(record_list) == 1:
            sole_domain = str(getattr(record_list[0], "domain", "") or "").lower().rstrip(".")
            if not sole_domain:
                return record_list[0]
        if not allow_body_selection:
            raise PermissionError("Guest hostname is not mapped to a property.")
        requested = supplied_property_id or default_property_id
        record = next((item for item in record_list if item.property_id == requested), None)
        if record is None:
            raise ValueError("Property not found.")
        return record


class ActionGuard:
    LEVELS = {"read": 1, "request": 2, "transaction": 3, "restricted": 4}

    def decide(self, action: str, property_id: str, config: dict[str, Any] | None, request_id: str, confirmed: bool = False) -> GuardrailDecision:
        policy = normalize_guardrails(config)
        action_map = {
            "service_request": (2, "service_requests_enabled"),
            "reservation": (3, "reservations_enabled"),
            "financial_action": (3, "financial_actions_enabled"),
            "admin": (4, None),
        }
        level, feature = action_map.get(action, (1, None))
        if level == 4:
            return GuardrailDecision(False, "This action is restricted.", "action_policy", property_id, level, False, True, request_id)
        if feature and not policy[feature]:
            return GuardrailDecision(False, "This service is not enabled for this property.", "action_policy", property_id, level, level >= 2, True, request_id)
        if level >= 2 and not confirmed:
            return GuardrailDecision(False, "Please review and explicitly confirm this request before it is submitted.", "action_confirmation", property_id, level, True, False, request_id)
        return GuardrailDecision(True, "action_allowed", "action_policy", property_id, level, level >= 2, False, request_id)


class PrivacyGuard:
    PRIVATE_PATTERNS = (
        r"\bwho (?:is|was) staying\b", r"\bis .{1,80} staying (?:here|at|in)\b",
        r"\bwhat room (?:is|does)\b", r"\bguest (?:name|room number|contact)\b",
        r"\b(?:list|show|name) (?:all )?guests\b", r"\banother guest(?:'s)?\b", r"\bcredit card\b", r"\bcvv\b", r"\batm pin\b",
        r"\bbanking password\b", r"\bone[- ]time password\b", r"\botp\b",
    )
    INJECTION_PATTERNS = (
        r"ignore (?:all |any |the )?(?:previous|prior|system|earlier)[^\n]{0,24}instructions",
        r"(?:show|reveal|print|repeat|give|tell me|read|display).{0,60}(?:system prompt|api key|password|secret|database configuration|database url|environment variables?|\.env|admin logs|hidden hotel configuration)",
        r"(?:i am|i'm) (?:the )?(?:hotel )?(?:administrator|admin|system)\b",
        r"act as (?:an? )?(?:administrator|admin|system)",
        r"(?:execute|run).{0,40}(?:shell|server|terminal)?\s*commands?",
        r"disable (?:your )?(?:security|guardrails|policy|safety restrictions)",
    )

    @classmethod
    def classify(cls, text: str) -> str | None:
        normalized = " ".join(text.lower().split())
        if any(re.search(pattern, normalized) for pattern in cls.INJECTION_PATTERNS):
            return "prompt_injection"
        if any(re.search(pattern, normalized) for pattern in cls.PRIVATE_PATTERNS):
            return "privacy"
        return None

    @staticmethod
    def safe_response(reason: str) -> str:
        if reason == "prompt_injection":
            return "I can’t override security rules or reveal system instructions, credentials, or hidden configuration. I can still help with hotel services and verified local information."
        return "I can’t confirm or disclose another guest’s identity, room, stay, contact details, payment data, or other private information. Please contact hotel staff for a properly authorized request."


class AIInputSanitizer:
    PATTERNS = (
        (re.compile(r"(?i)\b(?:api[_ -]?key|password|secret|token|authorization)\s*[:=]\s*[^\s,;]+"), "[REDACTED]"),
        (re.compile(r"\b(?:\d[ -]*?){13,19}\b"), "[PAYMENT DATA REDACTED]"),
        (re.compile(r"(?i)\b(?:cvv|cvc|otp|pin)\s*[:=]?\s*\d{3,8}\b"), "[SENSITIVE DATA REDACTED]"),
    )

    @classmethod
    def sanitize_text(cls, value: str) -> str:
        result = re.sub(r"<[^>]{0,2048}>", " ", str(value))
        result = "".join(character for character in result if character in "\n\t" or ord(character) >= 32)
        for pattern, replacement in cls.PATTERNS:
            result = pattern.sub(replacement, result)
        return re.sub(r"[ \t]+", " ", result)[:50_000]

    @classmethod
    def sanitize_context(cls, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for item in items[:40]:
            result.append({
                str(key)[:80]: cls.sanitize_text(str(value))
                for key, value in item.items()
                if str(key).lower() not in SECRET_KEYS
            })
        return result


class AIOutputValidator:
    SECRET_OUTPUT = re.compile(r"(?i)\b(?:api[_ -]?key|password|private key|bearer token)\s*[:=]\s*\S+")
    UNVERIFIED_CONFIRMATION = re.compile(r"(?i)\b(?:your (?:booking|reservation|payment)|the charge) (?:is|has been) confirmed\b")

    @classmethod
    def validate(cls, text: str) -> str:
        if cls.SECRET_OUTPUT.search(text):
            return "I can’t provide credentials or private system configuration. Please contact authorized hotel staff."
        if cls.UNVERIFIED_CONFIRMATION.search(text):
            return "I can’t confirm that transaction without a verified response from the hotel system. Please ask hotel staff to verify it."
        return text


class InternetGuard:
    @staticmethod
    def validate_url(url: str, allowed_hosts: Iterable[str] | None = None, allow_private: bool = False) -> str:
        parsed = urlsplit(str(url).strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Only credential-free HTTP(S) URLs are allowed.")
        if parsed.port is not None and parsed.port not in {80, 443}:
            raise ValueError("Only standard HTTP(S) ports are allowed.")
        hostname = parsed.hostname.lower().rstrip(".")
        if hostname == "localhost" or hostname.endswith(".localhost"):
            raise ValueError("Local and internal destinations are blocked.")
        allowed = {value.lower().rstrip(".") for value in (allowed_hosts or [])}
        if allowed and hostname not in allowed:
            raise ValueError("Destination host is not approved.")
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)}
        except socket.gaierror as exc:
            raise ValueError("Destination host could not be resolved.") from exc
        for value in addresses:
            address = ipaddress.ip_address(value)
            blocked = address.is_private or address.is_loopback or address.is_link_local or address.is_multicast or address.is_reserved or address.is_unspecified
            if blocked and not allow_private:
                raise ValueError("Private, local, metadata, and management destinations are blocked.")
        clean_netloc = hostname if parsed.port is None else f"{hostname}:{parsed.port}"
        return urlunsplit((parsed.scheme, clean_netloc, parsed.path or "/", parsed.query, ""))


class GatewayGuard:
    @staticmethod
    def validate(
        headers: Any,
        body: bytes,
        direct_ip: str,
        config: dict[str, Any] | None,
        *,
        property_id: str | None = None,
        nonce_consumer: Any = None,
    ) -> bool:
        policy = normalize_guardrails(config)
        if not policy["antlabs_gateway_enabled"]:
            return False
        try:
            source = ipaddress.ip_address("127.0.0.1" if direct_ip == "testclient" else direct_ip)
        except ValueError:
            return False
        if not NetworkGuard()._contains(source, policy["antlabs_gateway_ranges"]):
            return False
        secret = policy.get("antlabs_signature_secret", "")
        signature = str(headers.get("x-antlabs-signature", ""))
        timestamp = str(headers.get("x-antlabs-timestamp", ""))
        nonce = str(headers.get("x-antlabs-nonce", ""))
        if not secret or not signature or not timestamp or not nonce or len(nonce) < 16 or len(nonce) > 256:
            return False
        try:
            if abs(int(time.time()) - int(timestamp)) > 300:
                return False
        except ValueError:
            return False
        if not property_id or not callable(nonce_consumer):
            return False
        try:
            payload = json.loads(body)
        except (TypeError, ValueError, json.JSONDecodeError):
            return False
        if not isinstance(payload, dict) or payload.get("property_id") != property_id:
            return False
        canonical = timestamp.encode() + b"." + nonce.encode() + b"." + body
        expected = hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature.removeprefix("sha256="), expected):
            return False
        try:
            return bool(nonce_consumer(property_id, nonce))
        except (OSError, sqlite3.Error):
            return False


class RateLimiter:
    def __init__(self) -> None:
        self._windows: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, limit: int, seconds: int = 60) -> bool:
        now = time.monotonic()
        window = self._windows[key]
        while window and window[0] <= now - seconds:
            window.popleft()
        if len(window) >= limit:
            return False
        window.append(now)
        return True


class SQLiteRateLimiter:
    """A process-shared fixed-window event limiter for local appliance deployments."""

    def __init__(self, path: Path) -> None:
        self.path = path
        with sqlite3.connect(self.path) as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS rate_limit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rate_key TEXT NOT NULL,
                    created_at REAL NOT NULL
                )"""
            )
            db.execute("CREATE INDEX IF NOT EXISTS idx_rate_limit_key_time ON rate_limit_events(rate_key, created_at)")

    def allow(self, key: str, limit: int, seconds: int = 60) -> bool:
        now = time.time()
        cutoff = now - seconds
        with sqlite3.connect(self.path, timeout=5) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM rate_limit_events WHERE rate_key=? AND created_at<=?", (key, cutoff))
            count = db.execute(
                "SELECT COUNT(*) FROM rate_limit_events WHERE rate_key=? AND created_at>?",
                (key, cutoff),
            ).fetchone()[0]
            if count >= limit:
                return False
            db.execute("INSERT INTO rate_limit_events(rate_key, created_at) VALUES (?, ?)", (key, now))
            return True


class RateLimitUnavailable(RuntimeError):
    """Raised when the distributed limiter cannot make a safe decision."""


class RedisRateLimiter:
    """Atomic fixed-window limiter shared by every API replica.

    A missing/failed Redis service is fail-closed: sensitive guest/admin actions
    return 503 instead of quietly switching to a replica-local limit.
    """

    _INCREMENT_SCRIPT = """
    local count = redis.call('INCR', KEYS[1])
    if count == 1 then
      redis.call('PEXPIRE', KEYS[1], ARGV[1])
    end
    return count
    """

    def __init__(self, url: str, client: Redis | None = None) -> None:
        if not url and client is None:
            raise ValueError("Redis URL is required for the distributed rate limiter.")
        self.client = client or Redis.from_url(
            url,
            decode_responses=False,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
            health_check_interval=30,
            retry=Retry(NoBackoff(), retries=0),
        )

    @staticmethod
    def _redis_key(key: str) -> str:
        digest = hashlib.sha256(key.encode("utf-8", errors="replace")).hexdigest()
        return f"concierge:rate:{digest}"

    async def allow(self, key: str, limit: int, seconds: int = 60) -> bool:
        scope = key.split(":", 1)[0][:60] or "unknown"
        try:
            count = int(await self.client.eval(
                self._INCREMENT_SCRIPT,
                1,
                self._redis_key(key),
                max(1000, min(int(seconds), 86400 * 30) * 1000),
            ))
        except (RedisError, OSError, TimeoutError) as exc:
            metrics.REDIS_ERRORS.inc()
            metrics.RATE_LIMIT_EVENTS.labels(scope, "error").inc()
            raise RateLimitUnavailable("Distributed request protection is temporarily unavailable.") from exc
        allowed = count <= max(1, int(limit))
        metrics.RATE_LIMIT_EVENTS.labels(scope, "allowed" if allowed else "blocked").inc()
        return allowed

    async def ping(self) -> bool:
        try:
            return bool(await self.client.ping())
        except (RedisError, OSError, TimeoutError) as exc:
            metrics.REDIS_ERRORS.inc()
            raise RateLimitUnavailable("Redis readiness check failed.") from exc

    async def close(self) -> None:
        await self.client.aclose()


class SecurityAuditLogger:
    def __init__(self, path: Path) -> None:
        self.path = path
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS security_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp INTEGER NOT NULL,
                    request_id TEXT NOT NULL,
                    property_id TEXT,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    result TEXT NOT NULL,
                    source_ip TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        return connect_database(self.path)

    def record(self, request_id: str, property_id: str | None, action: str, result: str, source_ip: str = "", resource: str = "guardrail", actor: str = "guest", metadata: dict[str, Any] | None = None) -> None:
        clean = {
            str(key)[:80]: str(value)[:500]
            for key, value in (metadata or {}).items()
            if str(key).lower() not in SECRET_KEYS
        }
        with self._connect() as db:
            db.execute(
                "INSERT INTO security_events(timestamp,request_id,property_id,actor,action,resource,result,source_ip,metadata_json) VALUES(?,?,?,?,?,?,?,?,?)",
                (int(time.time()), request_id, property_id, actor[:80], action[:120], resource[:200], result[:80], source_ip[:120], json.dumps(clean, separators=(",", ":"))),
            )

    def list(self, property_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM security_events WHERE property_id=? ORDER BY timestamp DESC,event_id DESC LIMIT ?",
                (property_id, max(1, min(limit, 500))),
            ).fetchall()
        return [{**dict(row), "metadata": json.loads(row["metadata_json"])} for row in rows]
