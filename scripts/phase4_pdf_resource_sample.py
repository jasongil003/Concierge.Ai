"""Measure bounded parent RSS supervision with a disposable synthetic worker."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="concierge-phase4-pdf-") as temporary:
        os.environ.update({
            "APP_ENVIRONMENT": "test",
            "CONCIERGE_TESTING": "1",
            "STATE_DIRECTORY": temporary,
            "DB_PATH": str(Path(temporary) / "concierge.db"),
            "UPLOAD_ROOT": str(Path(temporary) / "uploads"),
            "DATABASE_URL": "",
            "REDIS_URL": "",
            "CREDENTIAL_ENCRYPTION_SECRET": "Synthetic-PDF-Only-Encryption-Secret-123456",
            "ADMIN_BOOTSTRAP_PASSWORD": "Synthetic-PDF-Only-123!",
        })
        pid_file = Path(temporary) / "worker.pid"
        worker_script = (
            "import pathlib,sys,time; "
            "pathlib.Path(sys.argv[1]).write_text(str(__import__('os').getpid())); "
            "chunks=[]; "
            "exec('for _ in range(192):\\n chunks.append(bytearray(1024*1024))\\n time.sleep(0.002)'); "
            "time.sleep(5)"
        )
        limit = 96 * 1024 * 1024
        peak_rss: list[int] = []
        stop = threading.Event()

        def sample_worker() -> None:
            import psutil

            while not stop.is_set():
                try:
                    pid = int(pid_file.read_text(encoding="utf-8"))
                except (FileNotFoundError, ValueError):
                    time.sleep(0.001)
                    continue
                try:
                    peak_rss.append(psutil.Process(pid).memory_info().rss)
                except psutil.NoSuchProcess:
                    return
                time.sleep(0.001)

        sampler = threading.Thread(target=sample_worker, daemon=True)
        sampler.start()
        try:
            from app.knowledge_management import _run_limited_pdf_worker

            try:
                _run_limited_pdf_worker(
                    [sys.executable, "-c", worker_script, str(pid_file)],
                    b"",
                    memory_limit_bytes=limit,
                    timeout_seconds=5,
                    poll_interval=0.025,
                )
                terminated_for_memory = False
            except MemoryError:
                terminated_for_memory = True
        finally:
            stop.set()
            sampler.join(timeout=1)

        import psutil

        worker_pid = int(pid_file.read_text(encoding="utf-8"))
        output = {
            "platform": sys.platform,
            "configured_threshold_mib": round(limit / 1_048_576, 1),
            "peak_sampled_worker_rss_mib": round(max(peak_rss, default=0) / 1_048_576, 1),
            "enforcement": "parent psutil RSS sampling at 25 ms poll interval followed by kill and communicate/reap",
            "kernel_hard_memory_limit_in_this_sample": False,
            "worker_terminated_and_reaped": terminated_for_memory and not psutil.pid_exists(worker_pid),
            "parent_process_alive": psutil.pid_exists(os.getpid()),
        }
    output["temporary_worker_directory_removed"] = not Path(temporary).exists()
    print(json.dumps(output, sort_keys=True))
    if (
        not output["worker_terminated_and_reaped"]
        or not output["parent_process_alive"]
        or not output["temporary_worker_directory_removed"]
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
