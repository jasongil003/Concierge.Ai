"""Bounded loopback HTTP sample using synthetic, disposable application state.

This measures shell/health HTTP handling, not guest or AI concurrency capacity.
No URL argument exists: this cannot target a hotel or third-party service.
"""

from concurrent.futures import ThreadPoolExecutor
import json
import math
import os
from pathlib import Path
import secrets
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen
from urllib.error import HTTPError

import psutil


ROOT = Path(__file__).resolve().parents[1]


def _build_environment(temporary: str) -> dict[str, str]:
    """Return only the environment needed by the disposable loopback app."""
    temporary_root = Path(temporary)
    return {
        "PATH": os.environ.get("PATH", os.defpath),
        "HOME": temporary,
        "TMPDIR": temporary,
        "TEMP": temporary,
        "TMP": temporary,
        "APP_ENVIRONMENT": "test",
        "CONCIERGE_TESTING": "1",
        "STATE_DIRECTORY": temporary,
        "DB_PATH": str(temporary_root / "test.db"),
        "UPLOAD_ROOT": str(temporary_root / "uploads"),
        "DATABASE_URL": "",
        "REDIS_URL": "",
        "PROPERTY_ID": "synthetic-http",
        "ENABLE_BACKGROUND_WORKERS": "false",
        "LOCAL_AI_ENABLED": "false",
        "ADMIN_BOOTSTRAP_PASSWORD": secrets.token_urlsafe(32) + "A!",
        "CREDENTIAL_ENCRYPTION_SECRET": secrets.token_urlsafe(48),
    }


def request(base_url, index):
    started = time.perf_counter()
    try:
        with urlopen(base_url + ("/" if index % 2 else "/health/live"), timeout=5) as response:
            response.read()
            status = response.status
    except HTTPError as error:
        status = error.code
    except Exception:
        status = 0
    return (time.perf_counter() - started) * 1000, status


def main():
    with tempfile.TemporaryDirectory(prefix="concierge-master-http-") as temporary:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        environment = _build_environment(temporary)
        base_url = f"http://127.0.0.1:{port}"
        subprocess.run([
            sys.executable, "-c",
            "from app.config import settings; from app.properties import PropertyStore, PropertyRecord; "
            "PropertyStore(settings.db_path).upsert(PropertyRecord(property_id='synthetic-http', hotel_name='Synthetic HTTP Hotel'))",
        ], cwd=ROOT, env=environment, check=True, capture_output=True)
        with (Path(temporary) / "server.log").open("w") as log:
            server = subprocess.Popen([
                sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                "--port", str(port), "--no-proxy-headers",
            ], cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 20
                while request(base_url, 0)[1] != 200:
                    if server.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("Disposable loopback app failed to start")
                    time.sleep(0.1)
                process = psutil.Process(server.pid)
                stages = []
                for concurrency in (1, 5, 10):
                    cpu_before = sum(process.cpu_times()[:2])
                    started = time.perf_counter()
                    with ThreadPoolExecutor(max_workers=concurrency) as pool:
                        samples = list(pool.map(lambda i: request(base_url, i), range(100)))
                    elapsed = time.perf_counter() - started
                    values = sorted(value for value, _ in samples)
                    failures = sum(status != 200 for _, status in samples)
                    stages.append({
                        "workers": concurrency, "requests": len(samples), "failures": failures,
                        "status_counts": {str(status): sum(code == status for _, code in samples) for status in sorted({code for _, code in samples})},
                        "duration_seconds": round(elapsed, 3),
                        "requests_per_second": round(len(samples) / elapsed, 2),
                        "p50_ms": round(statistics.median(values), 3),
                        "p95_ms": round(values[math.ceil(len(values) * .95) - 1], 3),
                        "p99_ms": round(values[math.ceil(len(values) * .99) - 1], 3),
                        "server_rss_mib": round(process.memory_info().rss / 1048576, 2),
                        "server_cpu_seconds": round(sum(process.cpu_times()[:2]) - cpu_before, 3),
                    })
                    if failures:
                        break
                server.terminate()
                server.wait(timeout=10)
                server = subprocess.Popen([
                    sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                    "--port", str(port), "--no-proxy-headers",
                ], cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)
                deadline = time.monotonic() + 20
                while request(base_url, 0)[1] != 200:
                    if server.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("Disposable app did not recover after restart")
                    time.sleep(.1)
                result = {
                    "scope": "loopback HTTP shell/health only; synthetic SQLite; one Uvicorn worker; no AI, guest sessions, proxy, or capacity certification",
                    "stages": stages, "health_after_restart": "PASS",
                }
                print(json.dumps(result, indent=2))
                return int(any(stage["failures"] for stage in stages))
            finally:
                if server.poll() is None:
                    server.terminate()
                    try:
                        server.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        server.kill()
                        server.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
