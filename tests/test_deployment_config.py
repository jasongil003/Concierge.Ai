import re
import os
from pathlib import Path
import subprocess

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]


def test_nginx_upstream_targets_a_compose_service():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    service_section = compose.split("services:", 1)[1].split("\nvolumes:", 1)[0]
    services = {
        line[2:-1]
        for line in service_section.splitlines()
        if line.startswith("  ") and not line.startswith("    ") and line.endswith(":")
    }

    nginx = (ROOT / "deploy" / "nginx.conf").read_text(encoding="utf-8")
    upstream = re.search(
        r"upstream\s+concierge_api\s*\{[^}]*?server\s+([A-Za-z0-9_.-]+):8080\s+resolve;",
        nginx,
        flags=re.DOTALL,
    )

    assert upstream is not None, "Nginx must define the Concierge API upstream"
    assert upstream.group(1) in services, "Nginx upstream must name a service from Compose"


def test_container_runs_non_root_with_only_state_owned_by_the_app_user():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "USER concierge" in dockerfile
    assert "chown -R concierge:concierge /state" in dockerfile
    assert "chown -R concierge:concierge /state /app" not in dockerfile


def test_production_proxy_is_loopback_only_and_requires_canonical_admin_boundaries():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    nginx = (ROOT / "deploy" / "nginx.conf").read_text(encoding="utf-8")

    assert '"127.0.0.1:8080:80"' in compose
    assert "CANONICAL_HOSTS: ${CANONICAL_HOSTS:?" in compose
    assert "PUBLIC_BASE_URL: ${PUBLIC_BASE_URL:?" in compose
    assert "ADMIN_ALLOWED_CIDRS: ${ADMIN_ALLOWED_CIDRS:?" in compose
    assert "FORWARDED_ALLOW_IPS: ${FORWARDED_ALLOW_IPS:-172.29.0.2}" in compose
    assert "proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;" in nginx


def test_development_compose_does_not_publish_http_admin_on_host_interfaces():
    compose = (ROOT / "docker-compose.dev.yml").read_text(encoding="utf-8")

    assert '"${CONCIERGE_DEV_BIND_HOST:-127.0.0.1}:${CONCIERGE_DEV_PORT:-8081}:8080"' in compose
    assert "concierge-dev-state:/state" in compose
    assert "CONCIERGE_DEPLOYMENT_MODE: docker-dev" in compose
    assert '"8080:8080"' not in compose


def test_fresh_appliance_config_hides_and_saves_confirmed_admin_password(tmp_path: Path):
    config_path = tmp_path / "concierge.env"
    script = """
        . "$CONFIGURE_SCRIPT"
        info() { printf '%s\\n' "$*" >&2; }
        die() { printf '%s\\n' "$*" >&2; exit 1; }
        chown() { return 0; }
        CONCIERGE_OS=linux
        generate_config "$CONFIG_PATH" "$STATE_PATH" "$BACKUP_PATH" \\
          '127.0.0.1/32' 'http://127.0.0.1:11434' concierge
    """
    password = "Appliance-Setup-Password-42!"
    environment = {
        **os.environ,
        "CONFIGURE_SCRIPT": str(ROOT / "deploy/common/configure.sh"),
        "CONFIG_PATH": str(config_path),
        "STATE_PATH": str(tmp_path / "state"),
        "BACKUP_PATH": str(tmp_path / "backups"),
    }
    result = subprocess.run(
        ["bash", "-c", script],
        input=(
            "hotel.example\n"
            "https://sg5.example/login/main.ant\n"
            "192.0.2.0/24\n"
            f"{password}\n{password}\n"
        ),
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert password not in result.stdout + result.stderr
    values = dotenv_values(config_path)
    assert values["ADMIN_BOOTSTRAP_USERNAME"] == "root"
    assert values["ADMIN_BOOTSTRAP_PASSWORD"] == password
    assert values["CREDENTIAL_ENCRYPTION_SECRET"]
    if os.name != "nt":
        assert config_path.stat().st_mode & 0o777 == 0o640


def test_linux_appliance_migrates_postgresql_before_application_initialization():
    platform = (ROOT / "deploy/linux/platform.sh").read_text(encoding="utf-8")
    migration = re.search(r"platform_migrate\(\) \{(.*?)\n\}", platform, re.DOTALL)

    assert migration is not None
    commands = migration.group(1)
    assert commands.index('os.getenv("DATABASE_URL"') < commands.index("alembic upgrade head")
    assert commands.index("alembic upgrade head") < commands.index("import app.main")


def test_production_compose_rejects_weak_bootstrap_password_without_echoing_config(tmp_path: Path):
    config_path = tmp_path / "concierge.env"
    config_path.write_text("ADMIN_BOOTSTRAP_PASSWORD='admin'\n", encoding="utf-8")
    environment = {
        **os.environ,
        "CONCIERGE_CONFIG_FILE": str(config_path),
        "CONCIERGE_VERSION": "0.9.2",
        "CONCIERGE_COMMIT": "a1b2c3d4",
        "CONCIERGE_BUILD_DATE": "2026-10-06T01:02:03Z",
    }
    environment.pop("ADMIN_BOOTSTRAP_PASSWORD", None)
    wrapper = ROOT / "deploy/docker-compose.sh"
    rejected = subprocess.run(
        ["bash", str(wrapper), "appliance", "config", "--quiet"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert rejected.returncode == 1
    assert "unique ADMIN_BOOTSTRAP_PASSWORD" in rejected.stderr
    assert "admin'" not in rejected.stderr

    config_path.write_text("ADMIN_BOOTSTRAP_PASSWORD='Production-Only-Password-42!'\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    captured = tmp_path / "compose-args.txt"
    docker = fake_bin / "docker"
    docker.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$CAPTURE_COMPOSE_ARGS\"\n", encoding="utf-8")
    docker.chmod(0o755)
    environment.update({
        "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
        "CAPTURE_COMPOSE_ARGS": str(captured),
    })
    accepted = subprocess.run(
        ["bash", str(wrapper), "appliance", "config", "--quiet"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert accepted.returncode == 0, accepted.stderr
    assert captured.is_file()
    assert "Production-Only-Password-42!" not in accepted.stdout + accepted.stderr
