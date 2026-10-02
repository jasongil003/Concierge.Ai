import copy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.admin_auth import DEFAULT_ROLES, AdminAuthStore
from app.guest_identity import GuestIdentityStore
from app.hospitality import HospitalityStore
from app.main import app
from app.operations import OperationsStore
from app.observability import ObservabilityStore
from app.properties import PropertyRecord, PropertyStore
from app.session_store import SessionStore


class AllowLimiter:
    @staticmethod
    def allow(*_args, **_kwargs):
        return True


def _login(client: TestClient, username: str, password: str) -> None:
    response = client.post("/api/admin/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["user"]["csrf_token"]


def test_content_manager_property_serializer_and_update_respect_permission_domains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    database = tmp_path / "property-boundaries.db"
    properties = PropertyStore(database)
    original = PropertyRecord(
        property_id="hotel-a",
        hotel_name="Hotel A",
        domain="hotel-a.example.test",
        ai_settings={"provider_secret_ref": "AI_PRIVATE_SENTINEL"},
        antlabs_config={"authentication_enabled": True, "gateway_secret_ref": "AUTH_PRIVATE_SENTINEL"},
        knowledge_sources=[{"source_id": "safe-knowledge-reference"}],
        personality={"system_prompt": "PERSONALITY_PRIVATE_SENTINEL"},
        guardrails={"antlabs_signature_secret": "GUARDRAIL_PRIVATE_SENTINEL", "internet_search_enabled": False},
        app_settings={
            "application": {"maintenance_enabled": False},
            "deployment": {"public_base_url": "https://hotel-a.example.test", "internal_token": "DEPLOY_PRIVATE_SENTINEL"},
            "internal": {"token": "NESTED_PRIVATE_SENTINEL"},
        },
    )
    properties.upsert(original)
    auth = AdminAuthStore(database)
    auth.ensure_bootstrap_admin("root", "PropertyRoot123!")
    _, root = auth.login("root", "PropertyRoot123!", "127.0.0.1", "property-boundary")
    auth.create_user(
        {
            "username": "content.manager",
            "display_name": "Content Manager",
            "password": "ContentManager123!",
            "role_id": "role-content-manager",
            "property_id": "hotel-a",
            "status": "active",
        },
        root,
    )
    monkeypatch.setattr(main_module, "properties", properties)
    monkeypatch.setattr(main_module, "admin_auth", auth)
    monkeypatch.setattr(main_module, "rate_limiter", AllowLimiter())

    with TestClient(app) as client:
        _login(client, "content.manager", "ContentManager123!")

        visible = client.get("/api/admin/properties/hotel-a")
        assert visible.status_code == 200, visible.text
        payload = visible.json()
        violations = []
        assert "knowledge_sources" in payload
        leaked_fields = {"ai_settings", "personality", "antlabs_config", "guardrails", "domain", "deployment_mode"} & set(payload)
        if leaked_fields:
            violations.append(f"unauthorized top-level fields exposed: {sorted(leaked_fields)}")
        if "deployment" in payload.get("app_settings", {}) or "internal" in payload.get("app_settings", {}):
            violations.append("unauthorized app_settings nested keys exposed")
        if "DEPLOY_PRIVATE_SENTINEL" in visible.text or "NESTED_PRIVATE_SENTINEL" in visible.text:
            violations.append("private nested configuration exposed")

        denied = client.put(
            "/api/admin/properties/hotel-a",
            json={
                "property_id": "hotel-a",
                "hotel_name": "Hotel A",
                "domain": "hotel-a.example.test",
                "ai_settings": {"provider_secret_ref": "ATTACKER_REPLACEMENT"},
                "app_settings": {
                    "deployment": {
                        "guest_access_enabled": True,
                        "public_base_url": "https://hotel-a.example.test",
                        "reverse_proxy": False,
                        "https_required": True,
                        "trusted_proxy": "",
                        "internal_token": "ATTACKER_NESTED_REPLACEMENT",
                    },
                    "internal": {"token": "ATTACKER_UNKNOWN_NESTED_REPLACEMENT"},
                },
            },
        )
        if denied.status_code != 403:
            violations.append(f"unauthorized generic property write returned {denied.status_code}")
        stored = properties.get("hotel-a")
        if stored.ai_settings != {"provider_secret_ref": "AI_PRIVATE_SENTINEL"}:
            violations.append("unauthorized write changed ai_settings")
        if stored.app_settings.get("deployment", {}).get("internal_token") != "DEPLOY_PRIVATE_SENTINEL":
            violations.append("unauthorized nested write changed app_settings.deployment")
        if stored.app_settings.get("internal", {}).get("token") != "NESTED_PRIVATE_SENTINEL":
            violations.append("unauthorized nested write changed unknown app_settings key")

        # Verify each permission domain independently, including nested settings.
        unauthorized_updates = [
            ({"ai_settings": {"provider_secret_ref": "ATTACKER_REPLACEMENT"}}, "ai.configure"),
            ({"personality": {"system_prompt": "ATTACKER_REPLACEMENT"}}, "ai.configure"),
            (
                {"antlabs_config": {"gateway_secret_ref": "ATTACKER_REPLACEMENT"}},
                "integrations.configure, security.configure",
            ),
            ({"guardrails": {"internet_search_enabled": False}}, "security.configure"),
            ({"domain": "hotel-a.example.test"}, "domains.configure, network.manage"),
            ({"deployment_mode": "cloud"}, "domains.configure"),
            (
                {"app_settings": {"deployment": {"guest_access_enabled": False}}},
                "domains.configure, network.manage",
            ),
            (
                {"app_settings": {"internal": {"token": "ATTACKER_NESTED_REPLACEMENT"}}},
                "system.configure",
            ),
        ]
        for update_fields, expected_permission in unauthorized_updates:
            denied = client.put(
                "/api/admin/properties/hotel-a",
                json={"property_id": "hotel-a", "hotel_name": "Hotel A", **update_fields},
            )
            assert denied.status_code == 403, denied.text
            assert denied.json()["detail"] == f"Permission required: {expected_permission}"

        # A permitted basic edit is partial and must preserve protected fields.
        saved = client.put(
            "/api/admin/properties/hotel-a",
            json={"property_id": "hotel-a", "hotel_name": "Hotel A Updated"},
        )
        if saved.status_code != 200:
            violations.append(f"basic property edit unexpectedly returned {saved.status_code}")
        stored = properties.get("hotel-a")
        if stored.hotel_name != "Hotel A Updated":
            violations.append("basic property edit did not save")
        if stored.ai_settings != {"provider_secret_ref": "AI_PRIVATE_SENTINEL"}:
            violations.append("partial basic update destroyed ai_settings")
        if stored.antlabs_config.get("gateway_secret_ref") != "AUTH_PRIVATE_SENTINEL":
            violations.append("partial basic update destroyed antlabs_config")
        if stored.guardrails.get("antlabs_signature_secret") != "GUARDRAIL_PRIVATE_SENTINEL":
            violations.append("partial basic update destroyed guardrails")
        if stored.app_settings.get("deployment", {}).get("internal_token") != "DEPLOY_PRIVATE_SENTINEL":
            violations.append("partial basic update destroyed app_settings.deployment")
        assert not violations, "; ".join(violations)

    # Owners see masked credential fields; saving surrounding settings keeps
    # the stored values instead of persisting the mask literal.
    with TestClient(app) as root_client:
        _login(root_client, "root", "PropertyRoot123!")
        visible_to_owner = root_client.get("/api/admin/properties/hotel-a")
        assert visible_to_owner.status_code == 200, visible_to_owner.text
        assert visible_to_owner.json()["ai_settings"]["provider_secret_ref"] == "[redacted]"
        assert visible_to_owner.json()["app_settings"]["internal"]["token"] == "[redacted]"
        saved = root_client.put(
            "/api/admin/properties/hotel-a",
            json={
                "property_id": "hotel-a",
                "hotel_name": "Hotel A Updated",
                "ai_settings": {"provider_secret_ref": "[redacted]", "mode": "updated"},
                "app_settings": {"internal": {"token": "[redacted]"}},
            },
        )
        assert saved.status_code == 200, saved.text
        stored = properties.get("hotel-a")
        assert stored.ai_settings == {"provider_secret_ref": "AI_PRIVATE_SENTINEL", "mode": "updated"}
        assert stored.app_settings["internal"]["token"] == "NESTED_PRIVATE_SENTINEL"


def test_department_manager_cannot_read_or_mutate_unscoped_stays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    database = tmp_path / "stay-boundaries.db"
    properties = PropertyStore(database)
    properties.upsert(PropertyRecord(property_id="hotel-a", hotel_name="Hotel A"))
    properties.upsert(PropertyRecord(property_id="hotel-b", hotel_name="Hotel B"))
    hospitality = HospitalityStore(database)
    housekeeping = hospitality.upsert_department(
        "hotel-a", {"department_id": "housekeeping", "name": "Housekeeping"}
    )
    front_desk = hospitality.upsert_department("hotel-a", {"department_id": "front-desk", "name": "Front Desk"})
    # The schema makes department IDs globally unique, so exercise the same
    # department name across properties without inventing an invalid duplicate ID.
    hospitality.upsert_department("hotel-b", {"department_id": "hotel-b-housekeeping", "name": "Housekeeping"})

    identities = GuestIdentityStore(database)
    department_a_device = identities.observe_device("hotel-a", "02:00:00:00:00:11")
    department_a_stay = identities.reconnect_or_create_stay(
        "hotel-a", department_a_device, room="DEPT-A-ROOM", pms_guest_id="DEPT-A-PMS"
    )
    identities.update_memory(
        "hotel-a", department_a_stay["stay_id"], {"conversation_summary": "DEPT-A-MEMORY"}
    )
    department_b_device = identities.observe_device("hotel-a", "02:00:00:00:00:22")
    department_b_stay = identities.reconnect_or_create_stay(
        "hotel-a", department_b_device, room="DEPT-B-ROOM", pms_guest_id="DEPT-B-PMS"
    )
    identities.update_memory(
        "hotel-a", department_b_stay["stay_id"], {"conversation_summary": "DEPT-B-MEMORY"}
    )
    cross_property_device = identities.observe_device("hotel-b", "02:00:00:00:00:33")
    cross_property_stay = identities.reconnect_or_create_stay(
        "hotel-b", cross_property_device, room="PROPERTY-B-ROOM", pms_guest_id="PROPERTY-B-PMS"
    )
    assert "department_id" not in department_a_stay
    assert "department_id" not in department_b_stay

    auth = AdminAuthStore(database)
    auth.ensure_bootstrap_admin("root", "StayRoot123!")
    _, root = auth.login("root", "StayRoot123!", "127.0.0.1", "stay-boundary")
    manager = auth.create_user(
        {
            "username": "housekeeping.manager",
            "display_name": "Housekeeping Manager",
            "password": "Housekeeping123!",
            "role_id": "role-department-manager",
            "property_id": "hotel-a",
            "department_id": housekeeping["department_id"],
            "status": "active",
        },
        root,
    )
    front_desk_manager = auth.create_user(
        {
            "username": "frontdesk.manager",
            "display_name": "Front Desk Manager",
            "password": "FrontDesk123!",
            "role_id": "role-department-manager",
            "property_id": "hotel-a",
            "department_id": front_desk["department_id"],
            "status": "active",
        },
        root,
    )
    # Simulate a stale database role row with legacy broad grants. Effective
    # principals must remain fail-closed until stay records gain department scope.
    with auth._connect() as db:
        db.executemany(
            "INSERT INTO admin_role_permissions (role_id, permission) VALUES (?, ?)",
            [
                ("role-department-manager", "guest_sessions.view"),
                ("role-department-manager", "guest_sessions.manage"),
            ],
        )

    monkeypatch.setattr(main_module, "properties", properties)
    monkeypatch.setattr(main_module, "hospitality", hospitality)
    monkeypatch.setattr(main_module, "guest_identities", identities)
    monkeypatch.setattr(main_module, "admin_auth", auth)
    monkeypatch.setattr(main_module, "rate_limiter", AllowLimiter())
    monkeypatch.setattr(main_module, "store", SessionStore(database))
    monkeypatch.setattr(main_module, "operations", OperationsStore(database))
    monkeypatch.setattr(main_module, "observability", ObservabilityStore(database))

    def check_manager_cannot_access_guest_records(manager_user, password, stays, raw_mac):
        with TestClient(app) as client:
            _login(client, manager_user["username"], password)
            listed = client.get("/api/admin/properties/hotel-a/sessions")
            assert listed.status_code == 403, listed.text
            assert not any(value in listed.text for value in ("DEPT-A-PMS", "DEPT-B-PMS", "DEPT-A-MEMORY", "DEPT-B-MEMORY"))
            assert client.get("/api/admin/properties/hotel-a/sessions?department_id=housekeeping").status_code == 403
            assert client.get("/api/admin/properties/hotel-a/sessions?property_id=hotel-b").status_code == 403
            assert client.get("/api/admin/properties/hotel-b/sessions").status_code == 403

            for stay, expected_room, expected_pms, expected_memory in stays:
                update = client.put(
                    f"/api/admin/properties/hotel-a/stays/{stay['stay_id']}/memory",
                    json={"memory": {"conversation_summary": "UNAUTHORIZED_MEMORY_REPLACEMENT"}},
                )
                assert update.status_code == 403, update.text
                checkout = client.post(f"/api/admin/properties/hotel-a/stays/{stay['stay_id']}/checkout")
                assert checkout.status_code == 403, checkout.text
                unchanged = next(
                    item for item in identities.list_stays("hotel-a") if item["stay_id"] == stay["stay_id"]
                )
                assert unchanged["status"] == "active"
                assert unchanged["room"] == expected_room
                assert unchanged["pms_guest_id"] == expected_pms
                assert unchanged["memory_summary"].get("conversation_summary") == expected_memory

            before = len(identities.list_stays("hotel-a"))
            reconnect = client.post(
                "/api/admin/properties/hotel-a/sessions/reconnect",
                json={"raw_mac": raw_mac, "room": "UNAUTHORIZED-ROOM", "pms_guest_id": "UNAUTHORIZED-PMS"},
            )
            assert reconnect.status_code == 403, reconnect.text
            assert len(identities.list_stays("hotel-a")) == before
            assert client.get("/api/admin/properties/hotel-a/conversations/retention").status_code == 403
            old_retention = main_module.store.retention("hotel-a")
            retention = client.put(
                "/api/admin/properties/hotel-a/conversations/retention", json={"retention_days": 45}
            )
            assert retention.status_code == 403, retention.text
            assert main_module.store.retention("hotel-a") == old_retention

            other_property_checkout = client.post(
                f"/api/admin/properties/hotel-b/stays/{cross_property_stay['stay_id']}/checkout"
            )
            assert other_property_checkout.status_code == 403, other_property_checkout.text
            other_property = identities.list_stays("hotel-b")[0]
            assert other_property["status"] == "active"
            assert other_property["room"] == "PROPERTY-B-ROOM"
            assert other_property["pms_guest_id"] == "PROPERTY-B-PMS"

    check_manager_cannot_access_guest_records(
        manager,
        "Housekeeping123!",
        [
            (department_a_stay, "DEPT-A-ROOM", "DEPT-A-PMS", "DEPT-A-MEMORY"),
            (department_b_stay, "DEPT-B-ROOM", "DEPT-B-PMS", "DEPT-B-MEMORY"),
        ],
        "02:00:00:00:00:44",
    )
    check_manager_cannot_access_guest_records(
        front_desk_manager,
        "FrontDesk123!",
        [
            (department_b_stay, "DEPT-B-ROOM", "DEPT-B-PMS", "DEPT-B-MEMORY"),
            (department_a_stay, "DEPT-A-ROOM", "DEPT-A-PMS", "DEPT-A-MEMORY"),
        ],
        "02:00:00:00:00:55",
    )


def test_generic_property_rbac_role_matrix_and_guest_session_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    database = tmp_path / "rbac-role-matrix.db"
    properties = PropertyStore(database)
    baseline = PropertyRecord(
        property_id="hotel-a",
        hotel_name="Hotel A",
        domain="hotel-a.example.test",
        ai_settings={"provider": "AI-READ-SENTINEL", "api_key": "AI-SECRET-SENTINEL"},
        antlabs_config={"authentication_enabled": True, "gateway_key": "ANTLABS-SECRET-SENTINEL"},
        guardrails={"internet_search_enabled": False, "antlabs_signature_secret": "GUARDRAIL-SECRET-SENTINEL"},
        knowledge_sources=[{"source_id": "knowledge-a"}],
        app_settings={
            "application": {"default_language": "en"},
            "deployment": {
                "guest_access_enabled": True,
                "public_base_url": "https://hotel-a.example.test",
                "reverse_proxy": False,
                "https_required": True,
                "trusted_proxy": "",
            },
        },
    )
    properties.upsert(copy.deepcopy(baseline))
    properties.upsert(PropertyRecord(property_id="hotel-b", hotel_name="Hotel B"))
    hospitality = HospitalityStore(database)
    department_a = hospitality.upsert_department("hotel-a", {"department_id": "housekeeping", "name": "Housekeeping"})
    identities = GuestIdentityStore(database)
    auth = AdminAuthStore(database)
    auth.ensure_bootstrap_admin("root", "MatrixRoot123!")
    _, root = auth.login("root", "MatrixRoot123!", "127.0.0.1", "rbac-matrix")

    role_slugs = (
        "super-admin",
        "property-manager",
        "content-manager",
        "department-manager",
        "restaurant-manager",
        "restaurant-staff",
    )
    users = {"super-admin": {"username": "root", "password": "MatrixRoot123!"}}
    for slug in role_slugs[1:]:
        user = auth.create_user(
            {
                "username": f"matrix.{slug}",
                "display_name": DEFAULT_ROLES[slug]["name"],
                "password": "MatrixUser123!",
                "role_id": f"role-{slug}",
                "property_id": "hotel-a",
                "department_id": department_a["department_id"] if slug == "department-manager" else None,
                "status": "active",
            },
            root,
        )
        users[slug] = {"username": user["username"], "password": "MatrixUser123!"}

    sessions = SessionStore(database)
    monkeypatch.setattr(main_module, "properties", properties)
    monkeypatch.setattr(main_module, "hospitality", hospitality)
    monkeypatch.setattr(main_module, "guest_identities", identities)
    monkeypatch.setattr(main_module, "admin_auth", auth)
    monkeypatch.setattr(main_module, "rate_limiter", AllowLimiter())
    monkeypatch.setattr(main_module, "store", sessions)
    monkeypatch.setattr(main_module, "operations", OperationsStore(database))
    monkeypatch.setattr(main_module, "observability", ObservabilityStore(database))

    normal_edit_roles = {"super-admin", "property-manager", "content-manager"}
    ai_read_roles = {"super-admin", "property-manager"}
    ai_edit_roles = {"super-admin"}
    security_read_roles = {"super-admin"}
    security_edit_roles = {"super-admin"}
    guest_session_view_roles = {"super-admin", "property-manager"}
    guest_session_manage_roles = {"super-admin", "property-manager"}

    for index, slug in enumerate(role_slugs, start=1):
        properties.upsert(copy.deepcopy(baseline))
        user = users[slug]
        with TestClient(app) as client:
            _login(client, user["username"], user["password"])
            visible = client.get("/api/admin/properties/hotel-a")
            assert visible.status_code == 200, f"{slug}: {visible.text}"
            data = visible.json()
            assert data["property_id"] == "hotel-a" and data["hotel_name"] == "Hotel A"
            assert ("ai_settings" in data) is (slug in ai_read_roles)
            assert ("guardrails" in data) is (slug in security_read_roles)
            assert ("antlabs_config" in data) is (slug in security_read_roles)
            assert ("deployment" in data.get("app_settings", {})) is (slug in {"super-admin", "property-manager"})
            if "ai_settings" in data:
                assert data["ai_settings"]["api_key"] == "[redacted]"
            if "guardrails" in data:
                assert data["guardrails"]["antlabs_signature_configured"] is True
                assert data["guardrails"].get("antlabs_signature_secret") is None
            if "antlabs_config" in data:
                assert data["antlabs_config"]["gateway_key"] == "[redacted]"

            normal = client.put(
                "/api/admin/properties/hotel-a",
                json={"property_id": "hotel-a", "hotel_name": f"Edited by {slug}"},
            )
            assert normal.status_code == (200 if slug in normal_edit_roles else 403), f"{slug}: {normal.text}"
            if slug in normal_edit_roles:
                assert properties.get("hotel-a").hotel_name == f"Edited by {slug}"
            else:
                assert properties.get("hotel-a").hotel_name == "Hotel A"

            properties.upsert(copy.deepcopy(baseline))
            ai_write = client.put(
                "/api/admin/properties/hotel-a",
                json={"property_id": "hotel-a", "hotel_name": "Hotel A", "ai_settings": {"provider": "AI-WRITE-SENTINEL"}},
            )
            assert ai_write.status_code == (200 if slug in ai_edit_roles else 403), f"{slug}: {ai_write.text}"
            assert properties.get("hotel-a").ai_settings["provider"] == (
                "AI-WRITE-SENTINEL" if slug in ai_edit_roles else "AI-READ-SENTINEL"
            )

            properties.upsert(copy.deepcopy(baseline))
            guardrail_write = client.put(
                "/api/admin/properties/hotel-a",
                json={"property_id": "hotel-a", "hotel_name": "Hotel A", "guardrails": {"internet_search_enabled": True}},
            )
            assert guardrail_write.status_code == (200 if slug in security_edit_roles else 403), f"{slug}: {guardrail_write.text}"
            assert properties.get("hotel-a").guardrails["internet_search_enabled"] is (slug in security_edit_roles)

            properties.upsert(copy.deepcopy(baseline))
            integration_write = client.put(
                "/api/admin/properties/hotel-a",
                json={"property_id": "hotel-a", "hotel_name": "Hotel A", "antlabs_config": {"gateway_key": "NEW-ANTLABS-KEY"}},
            )
            assert integration_write.status_code == (200 if slug in security_edit_roles else 403), f"{slug}: {integration_write.text}"
            assert properties.get("hotel-a").antlabs_config["gateway_key"] == (
                "NEW-ANTLABS-KEY" if slug in security_edit_roles else "ANTLABS-SECRET-SENTINEL"
            )

            device_id = identities.observe_device("hotel-a", f"02:00:00:00:{index:02x}:01")
            stay = identities.reconnect_or_create_stay(
                "hotel-a", device_id, room=f"{slug}-ROOM", pms_guest_id=f"{slug}-PMS"
            )
            identities.update_memory("hotel-a", stay["stay_id"], {"conversation_summary": f"{slug}-MEMORY"})

            listing = client.get("/api/admin/properties/hotel-a/sessions")
            assert listing.status_code == (200 if slug in guest_session_view_roles else 403), f"{slug}: {listing.text}"
            retention = client.get("/api/admin/properties/hotel-a/conversations/retention")
            assert retention.status_code == (200 if slug in guest_session_view_roles else 403), f"{slug}: {retention.text}"
            memory_write = client.put(
                f"/api/admin/properties/hotel-a/stays/{stay['stay_id']}/memory",
                json={"memory": {"conversation_summary": f"{slug}-UPDATED-MEMORY"}},
            )
            assert memory_write.status_code == (200 if slug in guest_session_manage_roles else 403), f"{slug}: {memory_write.text}"
            stored_stay = next(item for item in identities.list_stays("hotel-a") if item["stay_id"] == stay["stay_id"])
            assert stored_stay["memory_summary"]["conversation_summary"] == (
                f"{slug}-UPDATED-MEMORY" if slug in guest_session_manage_roles else f"{slug}-MEMORY"
            )
            checkout = client.post(f"/api/admin/properties/hotel-a/stays/{stay['stay_id']}/checkout")
            assert checkout.status_code == (200 if slug in guest_session_manage_roles else 403), f"{slug}: {checkout.text}"
            stored_stay = next(item for item in identities.list_stays("hotel-a") if item["stay_id"] == stay["stay_id"])
            assert stored_stay["status"] == ("checked_out" if slug in guest_session_manage_roles else "active")

            retention_update = client.put(
                "/api/admin/properties/hotel-a/conversations/retention", json={"retention_days": 45}
            )
            assert retention_update.status_code == (200 if slug in guest_session_manage_roles else 403), f"{slug}: {retention_update.text}"
            assert client.get("/api/admin/properties/hotel-b/sessions").status_code == (
                200 if slug == "super-admin" else 403
            )
