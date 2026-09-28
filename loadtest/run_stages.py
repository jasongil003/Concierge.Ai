"""Run the controlled Locust stages and collect app and host metrics.

This runner intentionally requires an explicit confirmation because the guest
workload creates service requests in the selected test property.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "loadtest" / "profiles.json"
METRICS_COUNTERS = {
    "http_errors": "concierge_http_errors_total",
    "database_errors": "concierge_database_errors_total",
    "rate_limit_events": "concierge_rate_limit_events_total",
}
AI_WAIT_BUCKET = "concierge_ai_provider_queue_wait_seconds_bucket"
PROM_SAMPLE = re.compile(r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{(?P<labels>.*)\})?\s+(?P<value>[-+0-9.eE]+)$")


def _scrape_metrics(base_url: str, token: str) -> str:
    request = Request(f"{base_url.rstrip('/')}/metrics", headers={"Authorization": f"Bearer {token}"})
    with urlopen(request, timeout=10) as response:
        if response.status != 200:
            raise RuntimeError(f"Metrics endpoint returned HTTP {response.status}.")
        return response.read().decode("utf-8", errors="replace")


def _samples(payload: str, metric: str) -> list[tuple[str, float]]:
    found: list[tuple[str, float]] = []
    for line in payload.splitlines():
        match = PROM_SAMPLE.match(line)
        if match and match.group("name") == metric:
            found.append((match.group("labels") or "", float(match.group("value"))))
    return found


def _api_resource_sample(payload: str) -> dict[str, float | None]:
    cpu = _samples(payload, "concierge_app_process_cpu_percent")
    memory_percent = _samples(payload, "concierge_app_process_memory_percent")
    memory_bytes = _samples(payload, "concierge_app_process_memory_bytes")
    return {
        "cpu_percent": cpu[-1][1] if cpu else None,
        "memory_percent": memory_percent[-1][1] if memory_percent else None,
        "rss_mb": memory_bytes[-1][1] / (1024 * 1024) if memory_bytes else None,
    }


def _counter_delta(before: str, after: str, metric: str) -> int:
    old = dict(_samples(before, metric))
    new = dict(_samples(after, metric))
    return int(sum(max(0.0, value - old.get(labels, 0.0)) for labels, value in new.items()))


def _ai_wait_percentiles(before: str, after: str) -> dict[str, float | int | None]:
    old = dict(_samples(before, AI_WAIT_BUCKET))
    new = dict(_samples(after, AI_WAIT_BUCKET))
    buckets: dict[float, float] = {}
    for labels, value in new.items():
        match = re.search(r'(?:^|,)le="([^"]+)"', labels)
        if not match:
            continue
        boundary = float("inf") if match.group(1) == "+Inf" else float(match.group(1))
        buckets[boundary] = buckets.get(boundary, 0.0) + max(0.0, value - old.get(labels, 0.0))
    count = int(buckets.get(float("inf"), 0))
    if not count:
        return {"count": 0, "p50_ms": None, "p95_ms": None}
    ordered = sorted(buckets.items(), key=lambda item: item[0])

    def percentile(target: float) -> float:
        for boundary, cumulative in ordered:
            if cumulative >= count * target:
                return boundary * 1000 if boundary != float("inf") else 10000.0
        return 10000.0

    return {"count": count, "p50_ms": percentile(0.50), "p95_ms": percentile(0.95)}


def _aggregate_row(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    row = next((item for item in rows if item.get("Name", "").casefold() == "aggregated"), None)
    if row is None:
        raise RuntimeError(f"Locust aggregate row is missing from {path}.")
    return row


def _number(row: dict[str, str], *keys: str) -> float | None:
    for key in keys:
        value = row.get(key, "")
        if value:
            try:
                return float(value)
            except ValueError:
                continue
    return None


def _locust_summary(path: Path) -> dict[str, float | int | None]:
    row = _aggregate_row(path)
    requests = int(_number(row, "Request Count") or 0)
    failures = int(_number(row, "Failure Count") or 0)
    return {
        "requests": requests,
        "failures": failures,
        "success_rate_percent": round((requests - failures) * 100 / requests, 4) if requests else None,
        "request_throughput_per_second": _number(row, "Requests/s", "Total RPS"),
        "http_latency_p50_ms": _number(row, "50%", "Median Response Time"),
        "http_latency_p95_ms": _number(row, "95%"),
        "http_latency_p99_ms": _number(row, "99%"),
    }


def _sample_api_resources(
    stop: threading.Event, output: list[dict[str, float | None]], base_url: str, token: str
) -> None:
    while not stop.is_set():
        try:
            payload = _scrape_metrics(base_url, token)
            output.append(_api_resource_sample(payload))
        except Exception:
            output.append({"cpu_percent": None, "memory_percent": None, "rss_mb": None})
        stop.wait(1)


def _system_summary(samples: list[dict[str, float | None]]) -> dict[str, float | int | str | None]:
    result: dict[str, float | int | str | None] = {"scope": "api_process", "samples": len(samples)}
    for metric in ("cpu_percent", "memory_percent", "rss_mb"):
        values = [float(item[metric]) for item in samples if item.get(metric) is not None]
        result[f"{metric}_mean"] = round(sum(values) / len(values), 3) if values else None
        result[f"{metric}_max"] = round(max(values), 3) if values else None
    return result


def main() -> None:
    if os.getenv("LOADTEST_CONFIRMATION") != "YES":
        raise SystemExit("Set LOADTEST_CONFIRMATION=YES after confirming the target is a disposable test property.")
    base_url = os.getenv("LOADTEST_BASE_URL", "").rstrip("/")
    token = os.getenv("LOADTEST_METRICS_TOKEN", "")
    property_id = os.getenv("PROPERTY_ID", "")
    if not base_url or not token or not property_id:
        raise SystemExit("Set LOADTEST_BASE_URL, LOADTEST_METRICS_TOKEN, and PROPERTY_ID for the test property.")
    try:
        with urlopen(base_url + "/health/ready", timeout=5) as response:
            if response.status != 200:
                raise RuntimeError(f"Readiness endpoint returned HTTP {response.status}.")
    except Exception as exc:
        raise SystemExit(f"The target readiness check failed: {exc}") from exc

    profiles = json.loads(PROFILE.read_text(encoding="utf-8"))
    output_root = Path(os.getenv("LOADTEST_OUTPUT_DIR", f"/tmp/concierge-load-stages-{int(time.time())}"))
    output_root.mkdir(parents=True, exist_ok=True)
    locust = shutil.which("locust")
    if not locust:
        raise SystemExit("Locust is not installed. Install loadtest/requirements.txt first.")
    results: list[dict[str, object]] = []

    for stage in profiles["controlled_stages"]:
        users = int(stage["users"])
        prefix = output_root / f"stage-{users}"
        before = _scrape_metrics(base_url, token)
        system_samples: list[dict[str, float | None]] = []
        stop = threading.Event()
        sampler = threading.Thread(
            target=_sample_api_resources,
            args=(stop, system_samples, base_url, token),
            daemon=True,
        )
        sampler.start()
        command = [
            locust, "--headless", "-f", str(ROOT / "loadtest" / "locustfile.py"),
            "--users", str(users), "--spawn-rate", str(stage["spawn_rate_per_second"]),
            "--run-time", str(stage["duration"]), "--host", base_url,
            "--csv", str(prefix), "--only-summary",
        ]
        environment = {**os.environ, "PROPERTY_ID": property_id}
        completed = subprocess.run(command, cwd=ROOT, env=environment, check=False)
        stop.set()
        sampler.join(timeout=3)
        after = _scrape_metrics(base_url, token)
        summary = _locust_summary(Path(f"{prefix}_stats.csv"))
        summary.update({name: _counter_delta(before, after, metric) for name, metric in METRICS_COUNTERS.items()})
        summary["ai_provider_queue_wait"] = _ai_wait_percentiles(before, after)
        summary["system"] = _system_summary(system_samples)
        item = {
            "stage": stage,
            "metrics": summary,
            "locust_exit_code": completed.returncode,
            "locust_csv_prefix": str(prefix),
        }
        results.append(item)
        (output_root / f"stage-{users}.json").write_text(json.dumps(item, indent=2), encoding="utf-8")
        print(json.dumps(item, indent=2))

    report = {"base_url": base_url, "property_id": property_id, "results": results}
    report_path = output_root / "summary.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Saved staged load results to {report_path}")


if __name__ == "__main__":
    main()
