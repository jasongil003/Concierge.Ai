"""Fresh-build and persistent-volume smoke for the production container."""

from __future__ import annotations

import json
from pathlib import Path
import secrets
import subprocess
import time
import uuid
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]


def _docker(*arguments: str) -> str:
    result = subprocess.run(["docker", *arguments], cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"Docker command failed ({arguments[0]}): {result.stderr.strip()[-1200:]}")
    return result.stdout.strip()


def _wait_ready(container: str, timeout: int = 120) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = _docker("inspect", "--format", "{{.State.Health.Status}}", container)
        if state == "healthy":
            return
        if state == "unhealthy":
            raise RuntimeError(f"Container {container} became unhealthy: {_docker('logs', '--tail', '80', container)}")
        time.sleep(2)
    raise RuntimeError(f"Container {container} did not become healthy within {timeout} seconds.")


def _host_port(container: str) -> str:
    published = _docker("port", container, "8080/tcp").splitlines()[0]
    return published.rsplit(":", 1)[1]


def _request_ready(base_url: str, timeout: int = 5) -> bool:
    try:
        with urlopen(base_url + "/health/ready", timeout=timeout) as response:
            return response.status == 200
    except Exception:
        return False


def main() -> None:
    suffix = uuid.uuid4().hex[:12]
    image = f"concierge-ai:qa-{suffix}"
    volume = f"concierge-qa-state-{suffix}"
    container = f"concierge-qa-{suffix}"
    password = secrets.token_urlsafe(24) + "A!"
    encryption_secret = secrets.token_urlsafe(48)
    metrics_token = secrets.token_urlsafe(32)
    phases: list[str] = []
    try:
        _docker("build", "--no-cache", "-t", image, ".")
        phases.append("fresh_image_build")
        _docker(
            "run", "--rm", "--entrypoint", "python",
            "-e", "APP_ENVIRONMENT=production", "-e", "PROPERTY_ID=hotel-a",
            "-e", "DB_PATH=/state/concierge.db", "-e", "UPLOAD_ROOT=/state/uploads",
            "-e", f"ADMIN_BOOTSTRAP_PASSWORD={password}",
            "-e", f"CREDENTIAL_ENCRYPTION_SECRET={encryption_secret}",
            "-e", f"METRICS_TOKEN={metrics_token}", "-e", "ADMIN_COOKIE_SECURE=true",
            "-e", "ALLOW_BODY_PROPERTY_SELECTION=false", "-e", "ALLOW_DEMO_SETTINGS=false",
            "-e", "APP_DEBUG=false", "-e", "CANONICAL_HOSTS=hotel-a.test",
            "-e", "PUBLIC_BASE_URL=https://hotel-a.test", "-e", "ADMIN_ALLOWED_CIDRS=127.0.0.1/32",
            "-e", "FORWARDED_ALLOW_IPS=127.0.0.1", "-e", "ANTLABS_MODE=browser_handoff",
            "-e", "ANTLABS_AUTH_URL=https://gateway.example.test/login/main.ant?c=proc",
            "-e", "ANTLABS_AUTH_METHOD=POST", image,
            "-c", "from app.config import settings; assert settings.app_environment == 'production'",
        )
        phases.append("production_settings_validation")
        _docker("volume", "create", volume)
        _docker(
            "run", "-d", "--name", container, "-p", "127.0.0.1::8080",
            "--health-cmd", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/ready', timeout=4)\"",
            "--health-interval=3s", "--health-timeout=4s", "--health-retries=20", "--health-start-period=5s",
            "-e", "APP_ENVIRONMENT=development", "-e", "ALLOW_DEMO_SETTINGS=true",
            "-e", "PROPERTY_ID=hotel-a", "-e", "DB_PATH=/state/concierge.db",
            "-e", "UPLOAD_ROOT=/state/uploads", "-e", f"ADMIN_BOOTSTRAP_PASSWORD={password}",
            "-e", f"CREDENTIAL_ENCRYPTION_SECRET={encryption_secret}",
            "-e", f"METRICS_TOKEN={metrics_token}", "-e", "ADMIN_COOKIE_SECURE=false",
            "-e", "ALLOW_BODY_PROPERTY_SELECTION=false", "-e", "ANTLABS_MODE=mock",
            "-e", "ENABLE_BACKGROUND_WORKERS=false", "-v", f"{volume}:/state", image,
        )
        port = _host_port(container)
        base_url = f"http://127.0.0.1:{port}"
        _wait_ready(container)
        uid = _docker("exec", container, "id", "-u")
        if uid == "0":
            raise RuntimeError("Production container is running as root.")
        _docker("exec", "--user", uid, container, "sh", "-c", "test -w /state && test ! -w /app/app/main.py")
        _docker("cp", str(ROOT / "scripts" / "docker_smoke.py"), f"{container}:/tmp/docker_smoke.py")
        _docker("exec", "--user", uid, "-e", "CONCIERGE_SMOKE_URL=http://127.0.0.1:8080", "-e", f"ADMIN_BOOTSTRAP_PASSWORD={password}", container, "python", "/tmp/docker_smoke.py", "write")
        if not _request_ready(base_url):
            raise RuntimeError("Application readiness failed after write phase.")
        phases.append("runtime_writes_and_health")
        _docker("rm", "-f", container)
        _docker(
            "run", "-d", "--name", container, "-p", f"127.0.0.1:{port}:8080",
            "--health-cmd", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/ready', timeout=4)\"",
            "--health-interval=3s", "--health-timeout=4s", "--health-retries=20", "--health-start-period=5s",
            "-e", "APP_ENVIRONMENT=development", "-e", "ALLOW_DEMO_SETTINGS=true",
            "-e", "PROPERTY_ID=hotel-a", "-e", "DB_PATH=/state/concierge.db",
            "-e", "UPLOAD_ROOT=/state/uploads", "-e", f"ADMIN_BOOTSTRAP_PASSWORD={password}",
            "-e", f"CREDENTIAL_ENCRYPTION_SECRET={encryption_secret}",
            "-e", f"METRICS_TOKEN={metrics_token}", "-e", "ADMIN_COOKIE_SECURE=false",
            "-e", "ALLOW_BODY_PROPERTY_SELECTION=false", "-e", "ANTLABS_MODE=mock",
            "-e", "ENABLE_BACKGROUND_WORKERS=false", "-v", f"{volume}:/state", image,
        )
        _wait_ready(container)
        _docker("cp", str(ROOT / "scripts" / "docker_smoke.py"), f"{container}:/tmp/docker_smoke.py")
        uid = _docker("exec", container, "id", "-u")
        _docker("exec", "--user", uid, "-e", "CONCIERGE_SMOKE_URL=http://127.0.0.1:8080", "-e", f"ADMIN_BOOTSTRAP_PASSWORD={password}", container, "python", "/tmp/docker_smoke.py", "verify")
        phases.append("container_recreation_persistence")
        print(json.dumps({"status": "passed", "phases": phases, "image": image}))
    finally:
        subprocess.run(["docker", "rm", "-f", container], cwd=ROOT, capture_output=True, check=False)
        subprocess.run(["docker", "volume", "rm", volume], cwd=ROOT, capture_output=True, check=False)
        subprocess.run(["docker", "image", "rm", "-f", image], cwd=ROOT, capture_output=True, check=False)


if __name__ == "__main__":
    main()
