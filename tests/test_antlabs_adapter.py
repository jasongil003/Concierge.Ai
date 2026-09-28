from dataclasses import replace

import pytest

import app.antlabs as antlabs_module
from app.antlabs import AntlabsAdapter


@pytest.fixture
def live_gateway_settings(monkeypatch):
    configured = replace(
        antlabs_module.settings,
        antlabs_mode="browser_handoff",
        antlabs_auth_url="https://sg5.example.test/login/main.ant?c=proc&site=hotel-a",
        antlabs_auth_method="POST",
        antlabs_room_field="uid",
        antlabs_last_name_field="pwd",
        antlabs_session_field="",
        antlabs_session_context_key="",
        antlabs_passthrough_fields=(),
    )
    monkeypatch.setattr(antlabs_module, "settings", configured)


@pytest.mark.parametrize(
    ("auth_type", "credentials", "expected_url", "expected_fields"),
    [
        (
            "complimentary",
            {},
            "https://sg5.example.test/login/main.ant?c=proc&site=hotel-a",
            {"p": "complimentary"},
        ),
        (
            "local",
            {"username": "guest", "password": "secret"},
            "https://sg5.example.test/login/main.ant?c=proc&site=hotel-a",
            {"p": "local", "uid": "guest", "pwd": "secret"},
        ),
        (
            "pms",
            {"room": "412", "last_name": "Smith"},
            "https://sg5.example.test/login/main.ant?c=proc&site=hotel-a",
            {"p": "pms", "uid": "412", "pwd": "Smith"},
        ),
        (
            "access_code",
            {"access_code": "hotel-code"},
            "https://sg5.example.test/login/main.ant?c=proc&site=hotel-a",
            {"p": "code", "code": "hotel-code"},
        ),
        (
            "credit_card",
            {},
            "https://sg5.example.test/login/main.ant?c=cc&site=hotel-a",
            {"p": "cc"},
        ),
    ],
)
def test_live_handoff_matches_antlabs_builtin_processor_guide(
    live_gateway_settings, auth_type, credentials, expected_url, expected_fields
):
    result = AntlabsAdapter().authenticate(auth_type, credentials, "session-a", {})

    assert result.status == "handoff_required"
    assert result.handoff == {"method": "POST", "url": expected_url, "fields": expected_fields}


@pytest.mark.parametrize(
    ("auth_type", "credentials"),
    [
        ("radius", {"username": "guest", "password": "secret"}),
        ("global_account", {"username": "guest", "password": "secret"}),
        ("global_code", {"global_code": "code"}),
        ("user_form", {"name": "Guest", "email": "guest@example.test"}),
        ("social_network", {"social_provider": "facebook"}),
    ],
)
def test_live_handoff_does_not_claim_unimplemented_methods_are_supported(
    live_gateway_settings, auth_type, credentials
):
    result = AntlabsAdapter().authenticate(auth_type, credentials, "session-a", {})

    assert result.status == "failed"
    assert "separate ANTlabs integration" in result.message
    assert result.handoff is None


@pytest.mark.parametrize(
    ("auth_url", "method", "message"),
    [
        ("https://sg5.example.test/custom-login", "POST", "/login/main.ant"),
        ("https://sg5.example.test/login/main.ant", "GET", "requires POST"),
    ],
)
def test_live_handoff_fails_closed_for_non_guide_endpoint_or_method(
    live_gateway_settings, monkeypatch, auth_url, method, message
):
    monkeypatch.setattr(
        antlabs_module,
        "settings",
        replace(antlabs_module.settings, antlabs_auth_url=auth_url, antlabs_auth_method=method),
    )

    result = AntlabsAdapter().authenticate("access_code", {"access_code": "code"}, "session-a", {})

    assert result.status == "failed"
    assert message in result.message
    assert result.handoff is None
