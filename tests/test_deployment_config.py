import re
from pathlib import Path


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
