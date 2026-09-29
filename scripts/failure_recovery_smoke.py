"""Exercise API, PostgreSQL, and Redis interruption/recovery on disposable containers."""

from __future__ import annotations

import http.cookiejar
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen
import uuid


ROOT = Path(__file__).resolve().parents[1]
PYTHON = str(ROOT / ".venv" / "bin" / "python")
ALEMBIC = str(ROOT / ".venv" / "bin" / "alembic")


def _docker(*arguments: str) -> str:
    result = subprocess.run(["docker", *arguments], cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"Docker {arguments[0]} failed: {result.stderr.strip()[-1000:]}")
    return result.stdout.strip()


def _published_port(container: str, internal_port: str) -> str:
    return _docker("port", container, internal_port).splitlines()[0].rsplit(":", 1)[1]


def _unused_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_container(command: list[str], timeout: int = 90) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            return
        time.sleep(1)
    raise RuntimeError(f"Container service did not recover: {command[2:5]}")


def _json_request(base_url: str, path: str, method: str = "GET", payload=None, headers=None, opener=None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request_headers = {"Accept": "application/json", **(headers or {})}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    request = Request(base_url + path, data=body, headers=request_headers, method=method)
    try:
        with (opener or build_opener()).open(request, timeout=8) as response:
            content = response.read()
            try:
                parsed = json.loads(content or b"{}")
            except (UnicodeDecodeError, json.JSONDecodeError):
                parsed = None
            return response.status, parsed
    except HTTPError as exc:
        content = exc.read()
        try:
            parsed = json.loads(content or b"{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed = None
        return exc.code, parsed
    except URLError:
        return 0, None


def _wait_ready(base_url: str, *, expected: bool, timeout: int = 90) -> None:
    deadline = time.monotonic() + timeout
    last_status, last_payload = 0, None
    while time.monotonic() < deadline:
        status, payload = _json_request(base_url, "/health/ready")
        last_status, last_payload = status, payload
        if expected and status == 200 and payload and payload.get("status") == "ok":
            return
        if not expected and status == 503:
            return
        time.sleep(1)
    raise RuntimeError(
        f"API readiness did not become {'ready' if expected else 'unavailable'}; "
        f"last response was HTTP {last_status}: {last_payload!r}"
    )


def _launch_api(environment: dict[str, str], port: int, log_path: Path):
    stream = log_path.open("a", encoding="utf-8")
    process = subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=environment,
        stdout=stream,
        stderr=subprocess.STDOUT,
    )
    process._qa_log_stream = stream
    return process


def _stop_api(process) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    process._qa_log_stream.close()


def _login(base_url: str, password: str):
    jar = http.cookiejar.CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))
    status, payload = _json_request(
        base_url,
        "/api/admin/auth/login",
        "POST",
        {"username": "admin", "password": password, "remember_me": False},
        opener=opener,
    )
    if status != 200:
        raise RuntimeError(f"Admin login failed during recovery smoke (HTTP {status}).")
    return opener, {"X-CSRF-Token": payload["user"]["csrf_token"]}


def _verify_config(base_url: str, password: str) -> None:
    opener, headers = _login(base_url, password)
    status, record = _json_request(base_url, "/api/admin/properties/recovery-test", opener=opener)
    if status != 200 or record.get("hotel_name") != "Recovery Test Property":
        raise RuntimeError("Property configuration did not persist across the restart/recovery event.")
    status, guardrails = _json_request(base_url, "/api/admin/properties/recovery-test/guardrails", opener=opener)
    if status != 200 or guardrails["config"].get("guest_access_hosts") != ["guest.recovery.example.test"]:
        raise RuntimeError("Guest hostname configuration did not persist across the restart/recovery event.")


def main() -> None:
    suffix = uuid.uuid4().hex[:10]
    postgres = f"concierge-qa-pg-{suffix}"
    redis = f"concierge-qa-redis-{suffix}"
    pg_port = _unused_port()
    redis_port = _unused_port()
    while redis_port == pg_port:
        redis_port = _unused_port()
    password = secrets.token_urlsafe(24) + "A!"
    environment = {
        **os.environ,
        "APP_ENVIRONMENT": "development",
        "PROPERTY_ID": "recovery-test",
        "ADMIN_BOOTSTRAP_PASSWORD": password,
        "CREDENTIAL_ENCRYPTION_SECRET": secrets.token_urlsafe(48),
        "METRICS_TOKEN": secrets.token_urlsafe(32),
        "ADMIN_COOKIE_SECURE": "false",
        "ALLOW_BODY_PROPERTY_SELECTION": "true",
        "ALLOW_DEMO_SETTINGS": "true",
        "ANTLABS_MODE": "mock",
        "ENABLE_BACKGROUND_WORKERS": "false",
        "ADMIN_ALLOWED_CIDRS": "127.0.0.1/32",
    }
    app_process = None
    phases = []
    with tempfile.TemporaryDirectory(prefix=f"concierge-recovery-{suffix}-") as temporary:
        temporary_root = Path(temporary)
        environment["DB_PATH"] = str(temporary_root / "fallback.sqlite")
        environment["UPLOAD_ROOT"] = str(temporary_root / "uploads")
        Path(environment["UPLOAD_ROOT"]).mkdir()
        log_path = temporary_root / "api.log"
        try:
            _docker(
                "run", "-d", "--name", postgres, "-e", "POSTGRES_USER=concierge",
                "-e", "POSTGRES_DB=concierge", "-e", "POSTGRES_HOST_AUTH_METHOD=trust",
                "-p", f"127.0.0.1:{pg_port}:5432", "postgres:16",
            )
            if _published_port(postgres, "5432/tcp") != str(pg_port):
                raise RuntimeError("PostgreSQL test port was not bound to its reserved host port.")
            _wait_container(["docker", "exec", postgres, "pg_isready", "-U", "concierge", "-d", "concierge"])
            _docker("run", "-d", "--name", redis, "-p", f"127.0.0.1:{redis_port}:6379", "redis:7-alpine")
            if _published_port(redis, "6379/tcp") != str(redis_port):
                raise RuntimeError("Redis test port was not bound to its reserved host port.")
            _wait_container(["docker", "exec", redis, "redis-cli", "ping"])
            environment["DATABASE_URL"] = f"postgresql+psycopg://concierge@127.0.0.1:{pg_port}/concierge"
            environment["REDIS_URL"] = f"redis://127.0.0.1:{redis_port}/0"
            environment["REDIS_TEST_URL"] = f"redis://127.0.0.1:{redis_port}/2"
            migration = subprocess.run([ALEMBIC, "upgrade", "head"], cwd=ROOT, env=environment, text=True, capture_output=True, check=False)
            if migration.returncode:
                raise RuntimeError(f"Disposable PostgreSQL schema setup failed: {migration.stderr[-1000:]}")
            integrations = subprocess.run(
                [
                    PYTHON, "-m", "pytest", "-q",
                    "tests/test_postgres_integration.py",
                    "tests/test_redis_rate_limiter.py",
                    "tests/test_ai_provider_distributed_bulkhead.py",
                ],
                cwd=ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
                timeout=180,
            )
            if integrations.returncode:
                diagnostic = "\n".join((integrations.stdout, integrations.stderr)).strip()[-6000:]
                raise RuntimeError(f"PostgreSQL/Redis integration suite failed:\n{diagnostic}")
            integration_summary = next(
                (line.strip() for line in reversed(integrations.stdout.splitlines()) if "passed" in line or "skipped" in line),
                "passed",
            )
            phases.append("postgresql_redis_repository_integration_tests")
            port = _unused_port()
            base_url = f"http://127.0.0.1:{port}"
            app_process = _launch_api(environment, port, log_path)
            _wait_ready(base_url, expected=True)
            opener, csrf = _login(base_url, password)
            status, _ = _json_request(
                base_url,
                "/api/admin/properties/recovery-test",
                "PUT",
                {
                    "property_id": "recovery-test",
                    "hotel_name": "Recovery Test Property",
                    "timezone": "UTC",
                    "domain": "recovery.example.test",
                    "guardrails": {"guest_access_hosts": ["guest.recovery.example.test"]},
                },
                headers=csrf,
                opener=opener,
            )
            if status != 200:
                raise RuntimeError(f"Property configuration write failed before recovery tests (HTTP {status}).")
            phases.append("initial_service_start_and_property_write")

            _stop_api(app_process)
            app_process = _launch_api(environment, port, log_path)
            _wait_ready(base_url, expected=True)
            _verify_config(base_url, password)
            phases.append("application_process_restart")

            _docker("stop", postgres)
            if _json_request(base_url, "/health/live")[0] != 200:
                raise RuntimeError("Liveness endpoint failed during PostgreSQL interruption.")
            _wait_ready(base_url, expected=False)
            phases.append("postgresql_interruption_returns_unready_but_live")
            _docker("start", postgres)
            if _published_port(postgres, "5432/tcp") != str(pg_port):
                raise RuntimeError("PostgreSQL host port changed across its container restart.")
            _wait_container(["docker", "exec", postgres, "pg_isready", "-U", "concierge", "-d", "concierge"])
            database_probe = subprocess.run(
                [
                    PYTHON, "-c",
                    "import os; from app.database import configure_database, database_ready; "
                    "configure_database(os.environ['DATABASE_URL']); database_ready()",
                ],
                cwd=ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
                timeout=15,
            )
            if database_probe.returncode:
                raise RuntimeError(
                    "PostgreSQL passed its container probe but was not reachable from the app host: "
                    f"{database_probe.stderr[-1500:]}"
                )
            _wait_ready(base_url, expected=True)
            _verify_config(base_url, password)
            phases.append("postgresql_reconnect_and_data_integrity")

            _docker("stop", redis)
            if _json_request(base_url, "/health/live")[0] != 200:
                raise RuntimeError("Liveness endpoint failed during Redis interruption.")
            _wait_ready(base_url, expected=False)
            phases.append("redis_interruption_returns_unready_but_live")
            _docker("start", redis)
            _wait_container(["docker", "exec", redis, "redis-cli", "ping"])
            _wait_ready(base_url, expected=True)
            _verify_config(base_url, password)
            phases.append("redis_reconnect_and_data_integrity")
            print(json.dumps({"status": "passed", "phases": phases, "postgres_redis_tests": integration_summary}))
        except Exception:
            if log_path.exists():
                print("API diagnostic tail:")
                print("\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-60:]))
            pg_logs = subprocess.run(["docker", "logs", postgres], cwd=ROOT, capture_output=True, text=True, check=False)
            if pg_logs.stdout or pg_logs.stderr:
                print("PostgreSQL diagnostic tail:")
                print("\n".join((pg_logs.stdout + pg_logs.stderr).splitlines()[-40:]))
            raise
        finally:
            if app_process is not None:
                _stop_api(app_process)
            subprocess.run(["docker", "rm", "-f", postgres, redis], cwd=ROOT, capture_output=True, check=False)


if __name__ == "__main__":
    main()
