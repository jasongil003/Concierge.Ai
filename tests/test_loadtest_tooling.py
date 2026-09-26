import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_loadtest_ai_configuration_cli_requires_explicit_confirmation():
    environment = os.environ.copy()
    environment.pop("LOADTEST_CONFIRMATION", None)
    environment.pop("PYTHONPATH", None)

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "configure_loadtest_ai.py")],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "Set LOADTEST_CONFIRMATION=YES" in result.stderr


def test_optional_loadtest_admin_user_is_not_scheduled_without_credentials():
    environment = os.environ.copy()
    environment["LOADTEST_ADMIN_USERNAME"] = ""
    environment["LOADTEST_ADMIN_PASSWORD"] = ""
    environment.pop("PYTHONPATH", None)
    script = (
        "from loadtest.locustfile import ADMIN_ENABLED, AdminReadWriteUser; "
        "assert not ADMIN_ENABLED; "
        "assert AdminReadWriteUser.weight == 0; "
        "assert AdminReadWriteUser.fixed_count == 0"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
