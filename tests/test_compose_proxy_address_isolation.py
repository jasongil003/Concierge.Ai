"""Compose rendering regression for the trusted proxy's reserved address."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _render_compose(tmp_path: Path, overlay):
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker CLI unavailable for Compose rendering acceptance")
    configuration = tmp_path / "synthetic.env"
    configuration.write_text("\n".join([
        f"CONCIERGE_CONFIG_FILE={configuration}",
        f"CONCIERGE_BACKUP_DIR={tmp_path / 'backups'}",
        "ADMIN_BOOTSTRAP_PASSWORD=ComposeTestOnly-Bootstrap-1234567890",
        "CREDENTIAL_ENCRYPTION_SECRET=ComposeTestOnly-Encryption-1234567890",
        "CONCIERGE_BACKUP_ENCRYPTION_KEY=" + "ab" * 32,
        "METRICS_TOKEN=ComposeTestOnly-Metrics-1234567890",
        "CANONICAL_HOSTS=localhost",
        "PUBLIC_BASE_URL=https://localhost",
        "ADMIN_ALLOWED_CIDRS=127.0.0.1/32",
    ]) + "\n", encoding="utf-8")
    command = [docker, "compose", "--project-name", "concierge-address-regression", "--env-file", str(configuration), "-f", "docker-compose.yml"]
    if overlay:
        command.extend(["-f", overlay])
    command.extend(["config", "--format", "json"])
    environment = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    if os.environ.get("DOCKER_CONFIG"):
        environment["DOCKER_CONFIG"] = os.environ["DOCKER_CONFIG"]
    result = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("overlay", [None, "scripts/phase6/docker-compose.overlay.yml", "docker-compose.load.yml"])
def test_application_cannot_take_the_trusted_proxy_address(tmp_path: Path, overlay):
    services = _render_compose(tmp_path, overlay)["services"]
    app_networks = services["concierge"]["networks"]
    proxy_networks = services["proxy"]["networks"]
    common = set(app_networks) & set(proxy_networks)
    assert len(common) == 1
    frontend = common.pop()
    assert proxy_networks[frontend]["ipv4_address"] == "172.29.0.2"
    assert (app_networks[frontend] or {}).get("ipv4_address") == "172.29.0.3", "Dynamic app allocation can claim the trusted proxy address before proxy startup"
    assert services["concierge"]["environment"]["FORWARDED_ALLOW_IPS"] == "172.29.0.2"


def test_phase6_host_ingress_belongs_only_to_proxy_and_retains_internal_services(tmp_path):
    config = _render_compose(tmp_path, "scripts/phase6/docker-compose.overlay.yml")
    services, networks = config["services"], config["networks"]
    assert networks["frontend"]["internal"] is True
    assert networks["backend"]["internal"] is True
    assert networks["ingress"].get("internal", False) is False
    assert networks["ingress"]["ipam"]["config"][0]["gateway"] == "172.30.0.1"
    assert set(services["proxy"]["networks"]) == {"frontend", "ingress"}
    for service in ("concierge", "postgres", "redis"):
        assert "ingress" not in services[service]["networks"]
    assert services["proxy"]["ports"][0]["host_ip"] == "127.0.0.1"


def test_nginx_loopback_map_requires_exact_known_gateway_and_no_supplied_forwarding():
    nginx = (ROOT / "deploy/nginx.conf").read_text()
    line = next(line for line in nginx.splitlines() if "localhost|127" in line)
    assert "172\\.30\\.0\\.1" in line
    assert "\\|\\|" in line
    assert line.strip().endswith("$ 1;")
    assert "default 0;" in nginx
