"""Run the isolated Playwright app and remove only its generated temp state."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile


def _owned_state_directory() -> Path | None:
    configured = os.environ.get("STATE_DIRECTORY", "").strip()
    if not configured:
        return None
    state_directory = Path(configured).expanduser().resolve()
    temporary_root = Path(tempfile.gettempdir()).resolve()
    if (
        state_directory.parent != temporary_root
        or not state_directory.name.startswith("concierge-ai-e2e-")
    ):
        return None
    return state_directory


def main() -> int:
    server: subprocess.Popen | None = None
    try:
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8092",
                "--no-proxy-headers",
            ]
        )

        def forward_signal(signum, _frame) -> None:
            if server is not None and server.poll() is None:
                try:
                    server.send_signal(signum)
                except ProcessLookupError:
                    pass

        signal.signal(signal.SIGTERM, forward_signal)
        signal.signal(signal.SIGINT, forward_signal)
        return server.wait()
    finally:
        if server is not None and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
        state_directory = _owned_state_directory()
        if state_directory is not None:
            shutil.rmtree(state_directory, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
