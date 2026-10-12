"""Run a small synthetic FastAPI/SQLite latency sample in temporary storage."""

from __future__ import annotations

import json
import math
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _measure(operation, count: int = 101) -> dict[str, float | int]:
    operation()  # warm-up
    samples = []
    for _ in range(count):
        started = time.perf_counter_ns()
        operation()
        samples.append((time.perf_counter_ns() - started) / 1_000_000)
    values = sorted(samples)

    def percentile(value: float) -> float:
        return values[max(0, math.ceil(len(values) * value) - 1)]

    return {
        "n": len(values),
        "p50_ms": round(statistics.median(values), 3),
        "p95_ms": round(percentile(0.95), 3),
        "p99_ms": round(percentile(0.99), 3),
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="concierge-phase4-perf-") as temporary:
        state = os.path.join(temporary, "state")
        os.makedirs(state, exist_ok=True)
        os.environ.update({
            "APP_ENVIRONMENT": "test",
            "CONCIERGE_TESTING": "1",
            "STATE_DIRECTORY": state,
            "DB_PATH": os.path.join(state, "concierge.db"),
            "UPLOAD_ROOT": os.path.join(state, "uploads"),
            "DATABASE_URL": "",
            "REDIS_URL": "",
            "ADMIN_BOOTSTRAP_PASSWORD": "Synthetic-Perf-Only-123!",
            "CREDENTIAL_ENCRYPTION_SECRET": "Synthetic-Perf-Encryption-Secret-123456789",
            "PROPERTY_ID": "synthetic-perf-property",
            "ALLOW_BODY_PROPERTY_SELECTION": "true",
        })

        import psutil
        from fastapi.testclient import TestClient

        from app.config import settings
        import app.main as main_module
        from app.main import app
        from app.properties import PropertyRecord
        from app.session_store import SessionStore

        main_module.properties.upsert(
            PropertyRecord(property_id="synthetic-perf-property", hotel_name="Synthetic Performance Hotel")
        )
        store = SessionStore(settings.db_path)
        process = psutil.Process()
        rss_start = process.memory_info().rss
        cpu_start = time.process_time()

        with TestClient(app) as client:
            def request(path: str) -> None:
                response = client.get(path)
                if response.status_code != 200:
                    raise RuntimeError(f"Synthetic request failed with HTTP {response.status_code}.")

            guest_shell = _measure(lambda: request("/"))
            health_live = _measure(lambda: request("/health/live"))
            transcript_write = _measure(lambda: store.record_message(
                "synthetic-guest",
                "synthetic-perf-property",
                "guest",
                "synthetic performance transcript",
            ))
            transcript_read = _measure(
                lambda: store.recent_messages("synthetic-guest", "synthetic-perf-property")
            )

        output = {
            "samples_per_operation": 101,
            "guest_shell": guest_shell,
            "health_live": health_live,
            "encrypted_transcript_write": transcript_write,
            "encrypted_transcript_retrieve": transcript_read,
            "process_rss_start_mib": round(rss_start / 1_048_576, 1),
            "process_rss_end_mib": round(process.memory_info().rss / 1_048_576, 1),
            "cpu_seconds_total": round(time.process_time() - cpu_start, 3),
            "scope": "in-process FastAPI TestClient with temporary SQLite and synthetic data; no provider, proxy, or capacity inference",
        }
        print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
