import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_load_overlay_declares_a_private_network_and_overlays_the_base_api():
    overlay = (ROOT / "docker-compose.load.yml").read_text(encoding="utf-8")

    assert "  concierge:" in overlay
    assert "  api:" not in overlay
    assert "- backend" not in overlay
    assert "  loadtest:\n    internal: true" in overlay
    assert "  frontend:\n    internal: true" in overlay
    assert "COMPATIBLE_API_BASE_URL: http://mock-ai:8081" in overlay
    assert "extra_hosts: !reset []" in overlay
    assert "ports: !override" in overlay


def test_base_and_load_compose_configuration_is_valid_and_network_isolated(tmp_path: Path):
    docker = shutil.which("docker")
    if not docker:
        pytest.skip("Docker CLI is unavailable; static load overlay assertions still run.")

    configuration = tmp_path / "loadtest.env"
    configuration.write_text(
        "\n".join(
            [
                f"CONCIERGE_CONFIG_FILE={configuration}",
                f"CONCIERGE_BACKUP_DIR={tmp_path / 'backups'}",
                "CONCIERGE_VERSION=loadtest-audit",
                "LOADTEST_PORT=18081",
                "ADMIN_BOOTSTRAP_USERNAME=loadtest-admin",
                "ADMIN_BOOTSTRAP_PASSWORD=LoadtestOnly-Admin-123!",
                "CREDENTIAL_ENCRYPTION_SECRET=LoadtestOnly-Encryption-Secret-1234567890",
                "METRICS_TOKEN=LoadtestOnly-Metrics-Token-1234567890",
                "CANONICAL_HOSTS=loadtest.example.test",
                "PUBLIC_BASE_URL=https://loadtest.example.test",
                "ADMIN_ALLOWED_CIDRS=127.0.0.1/32",
                "ANTLABS_MODE=mock",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(Path.home()),
    }
    if os.environ.get("DOCKER_CONFIG"):
        environment["DOCKER_CONFIG"] = os.environ["DOCKER_CONFIG"]
    result = subprocess.run(
        [
            docker,
            "compose",
            "--project-name",
            "concierge-load-audit",
            "--env-file",
            str(configuration),
            "-f",
            "docker-compose.yml",
            "-f",
            "docker-compose.load.yml",
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    rendered = json.loads(result.stdout)
    services = rendered["services"]
    networks = rendered["networks"]
    assert {"concierge", "mock-ai", "proxy"}.issubset(services)
    assert "postgres" not in services and "redis" not in services

    internal_network_names = {name for name, network in networks.items() if network.get("internal") is True}
    assert len(internal_network_names) == 2
    load_network = next(name for name in internal_network_names if name.endswith("loadtest"))
    assert set(services["mock-ai"]["networks"]) == {load_network}
    assert load_network in services["concierge"]["networks"]
    assert load_network not in services["proxy"]["networks"]
    frontend_names = set(services["concierge"]["networks"]) & set(services["proxy"]["networks"])
    assert len(frontend_names) == 1

    assert services["concierge"]["environment"]["ENABLE_BACKGROUND_WORKERS"] == "false"
    assert services["concierge"]["environment"]["AI_PROVIDER_MODE"] == "compatible"
    assert services["concierge"]["environment"]["COMPATIBLE_API_BASE_URL"] == "http://mock-ai:8081"
    assert services["concierge"].get("extra_hosts") in (None, [])
    assert services["mock-ai"]["build"]["dockerfile"] == "mock-ai.Dockerfile"
    assert re.search(r"@sha256:[a-f0-9]{64}$", services["proxy"]["image"])
    assert any(
        port.get("published") == "18081" and port.get("host_ip") == "127.0.0.1"
        for port in services["proxy"]["ports"]
    )
    assert rendered["volumes"]["concierge-state"]["name"].startswith("concierge-load-audit_")
