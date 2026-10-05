from types import SimpleNamespace

import pytest


@pytest.mark.parametrize(
    ("configured_username", "expected_username"),
    [(None, "root"), ("ci-admin", "ci-admin")],
)
def test_docker_smoke_login_uses_bootstrap_username(
    monkeypatch: pytest.MonkeyPatch,
    configured_username: str | None,
    expected_username: str,
):
    from scripts import docker_smoke

    monkeypatch.setattr(docker_smoke, "PASSWORD", "Smoke-Password-123!")
    if configured_username is None:
        monkeypatch.delenv("ADMIN_BOOTSTRAP_USERNAME", raising=False)
    else:
        monkeypatch.setenv("ADMIN_BOOTSTRAP_USERNAME", configured_username)

    calls = []

    def fake_request(path, method, payload, *, raw=False):
        calls.append((path, method, payload, raw))
        response = SimpleNamespace(headers={"Set-Cookie": "admin_session=token; Path=/"})
        return response, b'{"user":{"csrf_token":"csrf-token"}}'

    monkeypatch.setattr(docker_smoke, "request", fake_request)

    headers, payload = docker_smoke.login()

    assert calls == [
        (
            "/api/admin/auth/login",
            "POST",
            {"username": expected_username, "password": "Smoke-Password-123!", "remember_me": False},
            True,
        )
    ]
    assert headers == {"Cookie": "admin_session=token", "X-CSRF-Token": "csrf-token"}
    assert payload["user"]["csrf_token"] == "csrf-token"
