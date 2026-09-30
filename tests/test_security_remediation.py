from dataclasses import replace
from pathlib import Path
import time

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

import app.main as main_module
from app.admin_auth import AdminAuthStore
from app.config import Settings, validate_antlabs_mode, validate_production_settings
from app.guardrails import PropertyGuard
from app.hospitality import HospitalityStore
from app.main import app
from app.personalization import PersonalizationStore
from app.properties import PropertyRecord, PropertyStore
from app.session_store import SessionStore


def _production_settings(tmp_path: Path, **overrides) -> Settings:
    safe = Settings(
        app_environment="production",
        property_id="hotel-a",
        db_path=tmp_path / "concierge.db",
        admin_bootstrap_password="ProductionOnly123!",
        admin_cookie_secure=True,
        credential_encryption_secret="a" * 32,
        antlabs_mode="browser_handoff",
        antlabs_auth_url="https://gateway.example.test/login/main.ant?c=proc",
        allow_body_property_selection=False,
        metrics_token="m" * 40,
        canonical_hosts=("concierge.example.test", "admin.example.test"),
        admin_allowed_cidrs=("198.51.100.14/32",),
        public_base_url="https://concierge.example.test",
        forwarded_allow_ips="172.29.0.2,172.29.0.1",
    )
    return replace(safe, **overrides)


def test_production_rejects_default_admin_password(tmp_path: Path):
    with pytest.raises(RuntimeError, match="ADMIN_BOOTSTRAP_PASSWORD"):
        validate_production_settings(
            _production_settings(tmp_path, admin_bootstrap_password="ChangeMe123!")
        )


def test_production_rejects_default_encryption_secret(tmp_path: Path):
    with pytest.raises(RuntimeError, match="CREDENTIAL_ENCRYPTION_SECRET"):
        validate_production_settings(
            _production_settings(tmp_path, credential_encryption_secret="change-me")
        )


def test_production_requires_secure_cookie(tmp_path: Path):
    with pytest.raises(RuntimeError, match="ADMIN_COOKIE_SECURE"):
        validate_production_settings(
            _production_settings(tmp_path, admin_cookie_secure=False)
        )


def test_production_requires_canonical_hosts_and_admin_network_restrictions(tmp_path: Path):
    with pytest.raises(RuntimeError, match="CANONICAL_HOSTS"):
        validate_production_settings(_production_settings(tmp_path, canonical_hosts=()))
    with pytest.raises(RuntimeError, match="ADMIN_ALLOWED_CIDRS"):
        validate_production_settings(_production_settings(tmp_path, admin_allowed_cidrs=("0.0.0.0/0",)))
    with pytest.raises(RuntimeError, match="PUBLIC_BASE_URL"):
        validate_production_settings(_production_settings(tmp_path, public_base_url="http://concierge.example.test"))
    with pytest.raises(RuntimeError, match="FORWARDED_ALLOW_IPS"):
        validate_production_settings(_production_settings(tmp_path, forwarded_allow_ips="*"))


def test_staging_has_production_auth_and_gateway_requirements(tmp_path: Path):
    with pytest.raises(RuntimeError, match="ANTLABS_MODE=mock"):
        validate_production_settings(
            _production_settings(tmp_path, app_environment="staging", antlabs_mode="mock"),
            check_filesystem=False,
        )


def test_production_allows_persistent_sqlite_without_external_database_services(tmp_path: Path):
    settings = _production_settings(
        tmp_path,
        metrics_token="m" * 40,
        database_url="",
        redis_url="",
    )
    validate_production_settings(settings)


def test_production_rejects_example_metrics_token(tmp_path: Path):
    with pytest.raises(RuntimeError, match="METRICS_TOKEN"):
        validate_production_settings(
            _production_settings(
                tmp_path,
                metrics_token="replace-with-a-random-token-of-at-least-32-characters",
            )
        )


def test_antlabs_mode_is_explicitly_validated(tmp_path: Path):
    assert validate_antlabs_mode("mock") == "mock"
    assert validate_antlabs_mode("browser_handoff") == "browser_handoff"
    with pytest.raises(ValueError, match="Unsupported ANTLABS_MODE"):
        validate_antlabs_mode("live")
    with pytest.raises(RuntimeError, match="ANTLABS_MODE"):
        validate_production_settings(_production_settings(tmp_path, antlabs_mode="live"), check_filesystem=False)
    with pytest.raises(RuntimeError, match="ANTLABS_AUTH_URL"):
        validate_production_settings(_production_settings(tmp_path, antlabs_auth_url=""), check_filesystem=False)


def test_production_requires_sg5_builtin_processor_endpoint_and_post(tmp_path: Path):
    with pytest.raises(RuntimeError, match="ANTLABS_AUTH_URL must target the SG5 built-in processor"):
        validate_production_settings(
            _production_settings(tmp_path, antlabs_auth_url="https://gateway.example.test/custom-login"),
            check_filesystem=False,
        )
    with pytest.raises(RuntimeError, match="ANTLABS_AUTH_METHOD must be POST"):
        validate_production_settings(
            _production_settings(tmp_path, antlabs_auth_method="GET"),
            check_filesystem=False,
        )


def test_development_can_use_explicit_demo_settings(tmp_path: Path):
    development = replace(
        _production_settings(tmp_path),
        app_environment="development",
        property_id="tenant-a",
        antlabs_mode="mock",
        admin_cookie_secure=False,
        credential_encryption_secret="d" * 32,
        allow_body_property_selection=True,
    )
    validate_production_settings(development)


def test_every_environment_requires_explicit_bootstrap_and_encryption_secrets(tmp_path: Path):
    with pytest.raises(RuntimeError, match="ADMIN_BOOTSTRAP_PASSWORD must be explicitly set"):
        validate_production_settings(_production_settings(tmp_path, app_environment="development", admin_bootstrap_password=""))
    with pytest.raises(RuntimeError, match="CREDENTIAL_ENCRYPTION_SECRET must contain at least 32 characters"):
        validate_production_settings(_production_settings(tmp_path, app_environment="development", credential_encryption_secret=""))


def test_production_host_and_transport_boundary_reject_spoofing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    secure_settings = replace(
        main_module.settings,
        app_environment="production",
        canonical_hosts=("concierge.example.test",),
        admin_allowed_cidrs=("198.51.100.14/32",),
    )
    monkeypatch.setattr(main_module, "settings", secure_settings)

    with TestClient(app, base_url="http://concierge.example.test") as client:
        insecure = client.get("/api/hotel")
    with TestClient(app, base_url="https://concierge.example.test") as client:
        spoofed_ip = client.get(
            "/admin/login",
            headers={"X-Forwarded-For": "198.51.100.14"},
            follow_redirects=False,
        )
        bad_host = client.get("/admin/login", headers={"Host": "attacker.example"})

    assert insecure.status_code == 426
    assert insecure.headers["strict-transport-security"].startswith("max-age=")
    assert spoofed_ip.status_code == 403
    assert bad_host.status_code == 400


def test_production_allows_admin_only_from_configured_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    secure_settings = replace(
        main_module.settings,
        app_environment="production",
        canonical_hosts=("concierge.example.test",),
        admin_allowed_cidrs=("127.0.0.0/8",),
    )
    monkeypatch.setattr(main_module, "settings", secure_settings)
    with TestClient(app, base_url="https://concierge.example.test") as client:
        response = client.get("/admin/login")
    assert response.status_code == 200


def test_production_documents_are_disabled_but_remain_available_for_development():
    assert main_module.documentation_options("production") == {
        "docs_url": None,
        "redoc_url": None,
        "openapi_url": None,
    }
    assert main_module.documentation_options("staging")["openapi_url"] is None
    assert main_module.documentation_options("development")["openapi_url"] == "/openapi.json"


def test_password_recovery_link_uses_configured_public_origin(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        main_module,
        "settings",
        replace(main_module.settings, public_base_url="https://concierge.example.test"),
    )
    request = Request({
        "type": "http",
        "method": "POST",
        "scheme": "http",
        "path": "/api/admin/auth/password-reset/request",
        "query_string": b"",
        "headers": [(b"host", b"attacker.example")],
        "server": ("attacker.example", 80),
        "client": ("127.0.0.1", 12345),
        "http_version": "1.1",
    })
    assert main_module._admin_password_reset_url(request, "opaque-token") == (
        "https://concierge.example.test/admin/login#reset_token=opaque-token"
    )


def test_password_recovery_link_fails_closed_without_public_origin(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(main_module, "settings", replace(main_module.settings, public_base_url=""))
    request = Request({
        "type": "http",
        "method": "POST",
        "scheme": "http",
        "path": "/api/admin/auth/password-reset/request",
        "query_string": b"",
        "headers": [(b"host", b"attacker.example")],
        "server": ("attacker.example", 80),
        "client": ("127.0.0.1", 12345),
        "http_version": "1.1",
    })
    with pytest.raises(RuntimeError, match="PUBLIC_BASE_URL"):
        main_module._admin_password_reset_url(request, "opaque-token")


@pytest.mark.parametrize("address", ["127.0.0.1", "10.10.0.5", "100.64.0.1", "fd00::1"])
def test_deployment_verification_rejects_private_dns_answers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    address: str,
):
    import asyncio
    import socket

    record = PropertyRecord(property_id="hotel-a", hotel_name="Hotel A", domain="hotel.example.test")
    monkeypatch.setattr(
        main_module.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))
        ],
    )

    def unexpected_connection(*args, **kwargs):
        raise AssertionError("A non-public DNS answer must never receive a connection.")

    monkeypatch.setattr(main_module.socket, "create_connection", unexpected_connection)
    result = asyncio.run(main_module._verify_deployment(record))
    assert result["domain_status"] == "blocked"
    assert result["ssl_status"] == "not_checked"


def _tenant_stores(tmp_path: Path) -> tuple[PropertyStore, SessionStore]:
    property_store = PropertyStore(tmp_path / "tenants.db")
    property_store.upsert(PropertyRecord(property_id="hotel-a", hotel_name="Hotel A", domain="a.example.test"))
    property_store.upsert(PropertyRecord(property_id="hotel-b", hotel_name="Hotel B", domain="b.example.test"))
    return property_store, SessionStore(tmp_path / "tenants.db")


def test_unknown_host_cannot_select_property():
    records = [PropertyRecord(property_id="hotel-a", hotel_name="Hotel A", domain="a.example.test")]
    with pytest.raises(PermissionError, match="not mapped"):
        PropertyGuard.resolve(records, "hotel-a", "unknown.example.test", "hotel-a")


def test_unknown_host_cannot_resolve_a_single_domain_mapped_property_without_default():
    records = [PropertyRecord(property_id="hotel-a", hotel_name="Hotel A", domain="a.example.test")]
    with pytest.raises(PermissionError, match="not mapped"):
        PropertyGuard.resolve(records, "", "unknown.example.test")


def test_hotel_a_host_cannot_select_hotel_b():
    records = [
        PropertyRecord(property_id="hotel-a", hotel_name="Hotel A", domain="a.example.test"),
        PropertyRecord(property_id="hotel-b", hotel_name="Hotel B", domain="b.example.test"),
    ]
    with pytest.raises(PermissionError, match="does not match"):
        PropertyGuard.resolve(records, "hotel-a", "a.example.test", "hotel-b")


def test_hotel_a_guest_cannot_access_hotel_b_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    property_store, session_store = _tenant_stores(tmp_path)
    session = session_store.create("hotel-b", "hotel-b-guest")
    token, context = session_store.issue_guest_credentials(session.session_id, ttl_seconds=300)
    token_name, context_name = main_module._guest_cookie_names(session.session_id)
    monkeypatch.setattr(main_module, "properties", property_store)
    monkeypatch.setattr(main_module, "store", session_store)
    monkeypatch.setattr(
        main_module,
        "settings",
        replace(main_module.settings, allow_body_property_selection=False),
    )

    with TestClient(app, base_url="http://a.example.test") as client:
        response = client.get(
            f"/api/guest/personalization?session_id={session.session_id}",
            headers={"Cookie": f"{token_name}={token}; {context_name}={context}"},
        )

    assert response.status_code == 403
    assert response.json()["policy"] == "property_isolation"


def _guest_replay_stores(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, two_properties: bool = False):
    property_store = PropertyStore(tmp_path / "guest-replay.db")
    property_store.upsert(PropertyRecord(property_id="hotel-a", hotel_name="Hotel A", domain="a.example.test"))
    if two_properties:
        property_store.upsert(PropertyRecord(property_id="hotel-b", hotel_name="Hotel B", domain="b.example.test"))
    session_store = SessionStore(tmp_path / "guest-replay.db")
    monkeypatch.setattr(main_module, "properties", property_store)
    monkeypatch.setattr(main_module, "store", session_store)
    monkeypatch.setattr(main_module, "settings", replace(main_module.settings, allow_body_property_selection=False))
    return session_store


def _start_guest(client: TestClient, property_id: str = "hotel-a") -> str:
    response = client.post("/api/session/start", json={"client_id": "browser-client", "property_id": property_id})
    assert response.status_code == 200, response.text
    session_id = response.json()["session_id"]
    client.headers["X-Concierge-Session"] = session_id
    return session_id


def _client_guest_credentials(client: TestClient, session_id: str) -> tuple[str | None, str | None]:
    token_name, context_name = main_module._guest_cookie_names(session_id)
    token = client.cookies.get(token_name)
    context = client.cookies.get(context_name)
    if token and not context and "." in token:
        return tuple(token.split(".", 1))
    return token, context


def _client_guest_cookie_header(client: TestClient, session_id: str) -> str:
    token_name, context_name = main_module._guest_cookie_names(session_id)
    cookies = dict(client.cookies.items())
    selected = [f"{name}={cookies[name]}" for name in (token_name, context_name) if name in cookies]
    return "; ".join(selected)


def test_stolen_guest_session_id_alone_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _guest_replay_stores(tmp_path, monkeypatch)
    with TestClient(app, base_url="http://a.example.test") as original:
        session_id = _start_guest(original)
        assert original.get("/api/guest/personalization").status_code == 200

        with TestClient(app, base_url="http://a.example.test") as replay:
            response = replay.get(f"/api/guest/personalization?session_id={session_id}")

    assert response.status_code == 401


def test_guest_session_start_ignores_client_chosen_session_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    session_store = _guest_replay_stores(tmp_path, monkeypatch)
    supplied_session_id = "attacker-chosen-fixed-session-id"
    with TestClient(app, base_url="http://a.example.test") as client:
        response = client.post(
            "/api/session/start",
            json={
                "client_id": "browser-client",
                "property_id": "hotel-a",
                "session_id": supplied_session_id,
            },
        )
        assert response.status_code == 200, response.text
        created_session_id = response.json()["session_id"]
        assert created_session_id != supplied_session_id
        assert session_store.peek(supplied_session_id) is None
        assert session_store.peek(created_session_id) is not None
        cookie_name = main_module._guest_cookie_names(created_session_id)[0]
        assert client.cookies.get(cookie_name)


def test_legacy_guest_session_without_credentials_fails_closed_in_development(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    session_store = _guest_replay_stores(tmp_path, monkeypatch)
    legacy_session = session_store.create("hotel-a", "legacy-browser")
    with TestClient(app, base_url="http://a.example.test") as replay:
        response = replay.get(f"/api/guest/personalization?session_id={legacy_session.session_id}")
    assert response.status_code == 401


def test_guest_credentials_reject_cross_property_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    session_store = _guest_replay_stores(tmp_path, monkeypatch, two_properties=True)
    with TestClient(app, base_url="http://a.example.test") as original:
        session_id = _start_guest(original)
        token_name, context_name = main_module._guest_cookie_names(session_id)
        credentials = _client_guest_cookie_header(original, session_id)
        # The original browser can still access its session.
        assert original.get("/api/guest/personalization").status_code == 200

        with TestClient(app, base_url="http://b.example.test") as other_property:
            _start_guest(other_property, "hotel-b")
            response = other_property.get(
                f"/api/guest/personalization?session_id={session_id}",
                headers={"Cookie": credentials, "X-Concierge-Session": session_id},
            )

    assert response.status_code == 403
    assert response.json()["policy"] == "property_isolation"
    assert session_store.peek(session_id).property_id == "hotel-a"


def test_expired_guest_credential_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    session_store = _guest_replay_stores(tmp_path, monkeypatch)
    with TestClient(app, base_url="http://a.example.test") as client:
        session_id = _start_guest(client)
        with session_store._connect() as db:
            db.execute(
                "UPDATE sessions SET guest_token_expires_at=? WHERE session_id=?",
                (int(time.time()) - 1, session_id),
            )
        response = client.get("/api/guest/personalization")

    assert response.status_code == 401


def test_expired_guest_credentials_cannot_resume_and_their_cookie_is_cleared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    session_store = _guest_replay_stores(tmp_path, monkeypatch)
    with TestClient(app, base_url="http://a.example.test") as client:
        session_id = _start_guest(client)
        token_cookie_name = main_module._guest_cookie_names(session_id)[0]
        with session_store._connect() as db:
            db.execute(
                "UPDATE sessions SET guest_token_expires_at=? WHERE session_id=?",
                (int(time.time()) - 1, session_id),
            )
        resumed = client.post(
            "/api/session/resume",
            json={"client_id": "browser-client", "session_id": session_id},
        )
        assert resumed.status_code == 401
        assert client.cookies.get(token_cookie_name) is None


def test_active_guest_activity_slides_expiry_and_refreshes_cookie_age(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    session_store = _guest_replay_stores(tmp_path, monkeypatch)
    with TestClient(app, base_url="http://a.example.test") as client:
        session_id = _start_guest(client)
        with session_store._connect() as db:
            db.execute(
                "UPDATE sessions SET guest_token_expires_at=? WHERE session_id=?",
                (int(time.time()) + 1, session_id),
            )
        active = client.get("/api/guest/personalization")
        assert active.status_code == 200, active.text
        with session_store._connect() as db:
            extended_expiry = db.execute(
                "SELECT guest_token_expires_at FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()[0]
        assert extended_expiry >= int(time.time()) + 1700
        assert any(
            cookie.startswith(main_module._guest_cookie_names(session_id)[0] + "=")
            and "Max-Age=1800" in cookie
            for cookie in active.headers.get_list("set-cookie")
        )

        time.sleep(1.1)
        after_original_expiry = client.get("/api/guest/personalization")
        assert after_original_expiry.status_code == 200, after_original_expiry.text


def test_inactive_guest_session_expires_by_property_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    session_store = _guest_replay_stores(tmp_path, monkeypatch)
    with TestClient(app, base_url="http://a.example.test") as client:
        session_id = _start_guest(client)
        with session_store._connect() as db:
            db.execute(
                "UPDATE sessions SET last_seen_at=?,guest_token_expires_at=? WHERE session_id=?",
                (int(time.time()) - 31 * 60, int(time.time()) + 600, session_id),
            )
        response = client.get("/api/guest/personalization")
    assert response.status_code == 401


def test_revoked_guest_credential_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    session_store = _guest_replay_stores(tmp_path, monkeypatch)
    with TestClient(app, base_url="http://a.example.test") as client:
        revoked_session_id = _start_guest(client)
        active_session_id = _start_guest(client)
        revoked_cookie_name = main_module._guest_cookie_names(revoked_session_id)[0]
        active_cookie_name = main_module._guest_cookie_names(active_session_id)[0]
        session_store.revoke_guest_credentials(revoked_session_id)
        response = client.get(
            "/api/guest/personalization",
            headers={"X-Concierge-Session": revoked_session_id},
        )
        assert response.status_code == 401
        assert client.cookies.get(revoked_cookie_name) is None
        assert client.cookies.get(active_cookie_name) is not None
        assert client.get(
            "/api/guest/personalization",
            headers={"X-Concierge-Session": active_session_id},
        ).status_code == 200


@pytest.mark.parametrize("session_count", [2, 10, 25, 50])
def test_guest_cookie_headers_scale_across_concurrent_sessions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    session_count: int,
):
    _guest_replay_stores(tmp_path, monkeypatch)
    session_ids: list[str] = []
    with TestClient(app, base_url="http://a.example.test") as tabs:
        for index in range(session_count):
            started = tabs.post(
                "/api/session/start",
                json={"client_id": f"browser-tab-{index}", "property_id": "hotel-a"},
            )
            assert started.status_code == 200, started.text
            session_ids.append(started.json()["session_id"])

        cookie_header = "; ".join(
            f"{name}={value}" for name, value in tabs.cookies.items()
        )
        assert len(tabs.cookies) == session_count
        assert len(cookie_header.encode("ascii")) < 8192, (
            f"{session_count} active sessions produced a {len(cookie_header)} byte Cookie header"
        )

        # A browser sends all same-origin cookies to every tab. The session
        # selector must still pick only that tab's credential pair.
        for session_id in session_ids:
            response = tabs.get(
                f"/api/guest/personalization?session_id={session_id}",
                headers={"X-Concierge-Session": session_id},
            )
            assert response.status_code == 200, response.text


def test_resume_cannot_revive_revoked_guest_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    session_store = _guest_replay_stores(tmp_path, monkeypatch)
    with TestClient(app, base_url="http://a.example.test") as client:
        session_id = _start_guest(client)
        session_store.revoke_guest_credentials(session_id)
        response = client.post(
            "/api/session/resume",
            json={"client_id": "browser-client", "session_id": session_id},
        )
    assert response.status_code == 401
    session = session_store.peek(session_id)
    assert session is not None
    assert session.guest_token_hash is None
    assert session.guest_token_revoked_at is not None


def test_sqlite_startup_revokes_legacy_shared_credentials(tmp_path: Path):
    session_store = SessionStore(tmp_path / "legacy-shared-credentials.db")
    session_a = session_store.create("hotel-a", "browser-a")
    session_b = session_store.create("hotel-a", "browser-b")
    token, context = session_store.issue_guest_credentials(session_a.session_id, ttl_seconds=300)
    with session_store._connect() as db:
        db.execute("DROP INDEX uq_sessions_guest_token_hash")
        db.execute(
            "UPDATE sessions SET guest_token_hash=?,guest_context_hash=?,guest_token_expires_at=? WHERE session_id=?",
            (
                session_store._credential_hash(token),
                session_store._credential_hash(context),
                int(time.time()) + 300,
                session_b.session_id,
            ),
        )

    session_store._init_db()
    assert not session_store.verify_guest_credentials(session_a.session_id, token, context)
    assert not session_store.verify_guest_credentials(session_b.session_id, token, context)
    with session_store._connect() as db:
        duplicates = db.execute(
            "SELECT COUNT(*) FROM sessions WHERE guest_token_hash=?",
            (session_store._credential_hash(token),),
        ).fetchone()[0]
    assert duplicates == 0


def test_guest_sessions_keep_tab_credentials_and_data_separate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    session_store = _guest_replay_stores(tmp_path, monkeypatch)
    property_store = main_module.properties
    hospitality = HospitalityStore(tmp_path / "guest-replay.db")
    department = hospitality.upsert_department("hotel-a", {"name": "Test Guest Services"})
    service = hospitality.upsert_service("hotel-a", {
        "name": "Test Configured Service", "department_id": department["department_id"],
        "keywords": ["test service"],
    })
    service_id = service["service_id"]
    monkeypatch.setattr(main_module, "hospitality", hospitality)
    monkeypatch.setattr(main_module, "personalization", PersonalizationStore(tmp_path / "guest-replay.db"))

    class ModelResult:
        provider = "local"
        model = "test-model"
        text = "A private answer for this guest."

    chat_calls = []

    async def fake_chat(**kwargs):
        chat_calls.append(kwargs)
        return ModelResult()

    async def no_places(*_args, **_kwargs):
        return []

    monkeypatch.setattr(main_module.ai_models, "concierge_chat", fake_chat)
    monkeypatch.setattr(main_module.places, "search", no_places)

    with TestClient(app, base_url="http://a.example.test") as tabs:
        session_a = _start_guest(tabs)
        token_a, context_a = _client_guest_credentials(tabs, session_a)
        assert token_a and context_a

        session_b = _start_guest(tabs)
        token_b, context_b = _client_guest_credentials(tabs, session_b)
        assert token_b and context_b
        assert (token_a, context_a) != (token_b, context_b)
        token_a_name, context_a_name = main_module._guest_cookie_names(session_a)
        token_b_name, context_b_name = main_module._guest_cookie_names(session_b)
        assert token_a_name != token_b_name and context_a_name != context_b_name

        enabled = tabs.put(
            "/api/guest/personalization",
            json={"session_id": session_a, "enabled": True, "level": "personal"},
            headers={"X-Concierge-Session": session_a},
        )
        assert enabled.status_code == 200, enabled.text
        saved = tabs.put(
            "/api/guest/personalization/preferences",
            json={"session_id": session_a, "category": "dietary", "value": "vegetarian"},
            headers={"X-Concierge-Session": session_a},
        )
        assert saved.status_code == 200, saved.text
        state_a = tabs.get("/api/guest/personalization", headers={"X-Concierge-Session": session_a}).json()
        state_b = tabs.get("/api/guest/personalization", headers={"X-Concierge-Session": session_b}).json()
        assert any(item["value"] == "vegetarian" for item in state_a["preferences"])
        assert not state_b["preferences"]

        chat = tabs.post(
            "/api/chat",
            json={
                "session_id": session_a,
                "message": "Where should I eat?",
                "mode": "advanced",
                "conversation_history": [{"role": "guest", "content": "A-private-chat-history"}],
            },
            headers={"X-Concierge-Session": session_a},
        )
        assert chat.status_code == 200, chat.text
        chat_b = tabs.post(
            "/api/chat",
            json={"session_id": session_b, "message": "Where should I eat?", "mode": "advanced"},
            headers={"X-Concierge-Session": session_b},
        )
        assert chat_b.status_code == 200, chat_b.text
        assert chat_calls[0]["conversation_history"] == [{"role": "guest", "content": "A-private-chat-history"}]
        assert chat_calls[1]["conversation_history"] == []
        assert any(item["value"] == "vegetarian" for item in chat_calls[0]["guest_context"]["personalization"]["preferences"])
        assert not chat_calls[1]["guest_context"]["personalization"]["preferences"]

        request_a = tabs.post(
            "/api/guest/service-requests",
            json={
                "session_id": session_a,
                "service_id": service_id,
                "description": "Extra towels for tab A",
                "confirmed": True,
            },
            headers={"X-Concierge-Session": session_a},
        )
        assert request_a.status_code == 200, request_a.text
        requests_a = tabs.get("/api/guest/requests", headers={"X-Concierge-Session": session_a}).json()["requests"]
        requests_b = tabs.get("/api/guest/requests", headers={"X-Concierge-Session": session_b}).json()["requests"]
        assert any(item["description"] == "Extra towels for tab A" for item in requests_a)
        assert requests_b == []

        with TestClient(app, base_url="http://a.example.test") as stolen:
            theft = stolen.get(
                f"/api/guest/personalization?session_id={session_a}",
                headers={"X-Concierge-Session": session_a},
            )
        assert theft.status_code == 401

        a_only_cookie = _client_guest_cookie_header(tabs, session_a)
        with TestClient(app, base_url="http://a.example.test") as wrong_tab:
            wrong_tab_request = wrong_tab.post(
                "/api/guest/service-requests",
                json={
                    "session_id": session_b,
                    "service_id": service_id,
                    "description": "Must not be created for tab B",
                    "confirmed": True,
                },
                headers={
                    "Cookie": a_only_cookie,
                    "X-Concierge-Session": session_b,
                },
            )
        assert wrong_tab_request.status_code == 401
        assert session_store.peek(session_a).property_id == property_store.get("hotel-a").property_id


def test_guest_tokens_are_opaque_hashed_and_not_logged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog):
    session_store = _guest_replay_stores(tmp_path, monkeypatch)
    with TestClient(app, base_url="http://a.example.test") as client:
        response = client.post("/api/session/start", json={"client_id": "browser-client", "property_id": "hotel-a"})
        assert response.status_code == 200, response.text
        session_id = response.json()["session_id"]
        client.headers["X-Concierge-Session"] = session_id
        token, context = _client_guest_credentials(client, session_id)
        assert token and context
        assert len(token) >= 40 and len(context) >= 40
        assert token not in response.text and context not in response.text
        record = session_store.peek(session_id)
        assert record.guest_token_hash != token
        assert record.guest_context_hash != context
        assert client.get("/api/guest/personalization").status_code == 200

    assert token not in caplog.text
    assert context not in caplog.text


def test_guest_session_credentials_rotate_on_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _guest_replay_stores(tmp_path, monkeypatch)
    with TestClient(app, base_url="http://a.example.test") as client:
        session_id = _start_guest(client)
        old_credentials = _client_guest_credentials(client, session_id)
        resumed = client.post(
            "/api/session/resume",
            json={"client_id": "browser-client", "session_id": session_id},
        )
        assert resumed.status_code == 200, resumed.text
        new_credentials = _client_guest_credentials(client, session_id)
        assert new_credentials != old_credentials
        assert client.get("/api/guest/personalization").status_code == 200


def test_legacy_guest_cookies_are_rotated_and_removed_after_valid_use(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    session_store = _guest_replay_stores(tmp_path, monkeypatch)
    session = session_store.create("hotel-a", "legacy-browser")
    old_token, old_context = session_store.issue_guest_credentials(session.session_id, ttl_seconds=300)
    legacy_token_name, legacy_context_name = main_module._guest_cookie_names()
    with TestClient(app, base_url="http://a.example.test") as client:
        client.cookies.set(legacy_token_name, old_token, domain="a.example.test", path="/")
        client.cookies.set(legacy_context_name, old_context, domain="a.example.test", path="/")
        response = client.get(
            f"/api/guest/personalization?session_id={session.session_id}",
            headers={"X-Concierge-Session": session.session_id},
        )
        assert response.status_code == 200, response.text
        assert client.cookies.get(legacy_token_name) is None
        assert client.cookies.get(legacy_context_name) is None
        new_credentials = _client_guest_credentials(client, session.session_id)
        assert new_credentials[0] and new_credentials[1]
        assert new_credentials != (old_token, old_context)
        assert session_store.verify_guest_credentials(session.session_id, *new_credentials)


def test_production_guest_cookies_are_secure_httponly_and_same_site(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        main_module,
        "settings",
        replace(main_module.settings, app_environment="production", admin_cookie_secure=True),
    )
    response = main_module.Response()
    main_module._set_guest_cookies(response, "a" * 32, "random-token", "random-context", 300)

    cookies = response.headers.getlist("set-cookie")
    assert len(cookies) == 2
    credential_cookie = next(cookie for cookie in cookies if "Max-Age=300" in cookie)
    cleared_context_cookie = next(cookie for cookie in cookies if "Max-Age=0" in cookie)
    assert all("Secure" in cookie and "HttpOnly" in cookie and "SameSite=strict" in cookie for cookie in cookies)
    assert "Path=/" in credential_cookie and "__Host-concierge_guest_" in credential_cookie
    assert "Path=/" in cleared_context_cookie and "__Host-concierge_guest_" in cleared_context_cookie


def test_hotel_a_admin_cannot_access_hotel_b_without_permission(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    auth = AdminAuthStore(tmp_path / "admin-tenants.db")
    auth.ensure_bootstrap_admin("admin", "ChangeMe123!")
    _, super_admin = auth.login("admin", "ChangeMe123!", "127.0.0.1", "tests")
    auth.create_user(
        {
            "username": "hotel-a-admin",
            "display_name": "Hotel A Admin",
            "password": "HotelAOnly123!",
            "property_id": "hotel-a",
            "role_id": "role-property-administrator",
            "status": "active",
        },
        super_admin,
    )
    monkeypatch.setattr(main_module, "admin_auth", auth)
    with TestClient(app) as client:
        login = client.post(
            "/api/admin/auth/login",
            json={"username": "hotel-a-admin", "password": "HotelAOnly123!", "remember_me": False},
        )
        assert login.status_code == 200
        response = client.get("/api/admin/properties/hotel-b")
    assert response.status_code == 403


def test_super_admin_can_access_authorized_global_resource(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    auth = AdminAuthStore(tmp_path / "super-admin.db")
    auth.ensure_bootstrap_admin("admin", "ChangeMe123!")
    monkeypatch.setattr(main_module, "admin_auth", auth)
    with TestClient(app) as client:
        login = client.post(
            "/api/admin/auth/login",
            json={"username": "admin", "password": "ChangeMe123!", "remember_me": False},
        )
        assert login.status_code == 200
        response = client.get("/api/admin/system/email")
    assert response.status_code == 200
