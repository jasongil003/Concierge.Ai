import os
from pathlib import Path
import subprocess
import sys
import csv
import json

from loadtest.run_stages import _ai_wait_percentiles, _api_resource_sample, _counter_delta, _locust_summary


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


def test_controlled_load_profile_has_requested_stages_and_metrics():
    profile = json.loads((ROOT / "loadtest" / "profiles.json").read_text(encoding="utf-8"))
    assert [stage["users"] for stage in profile["controlled_stages"]] == [10, 50, 100, 250, 500, 1000]
    assert {
        "success_rate_percent", "request_throughput_per_second", "http_latency_p50_ms",
        "http_latency_p95_ms", "http_latency_p99_ms", "http_errors", "database_errors",
        "cpu_percent_mean_max", "memory_percent_mean_max", "ai_provider_queue_wait_p50_p95_ms",
        "rate_limit_events",
    } == set(profile["collected_metrics"])


def test_loadtest_metric_helpers_compute_counter_deltas_and_wait_buckets():
    before = """# HELP metrics sample
concierge_database_errors_total{operation="query"} 2
concierge_ai_provider_queue_wait_seconds_bucket{provider="local",le="0.01"} 0
concierge_ai_provider_queue_wait_seconds_bucket{provider="local",le="0.1"} 0
concierge_ai_provider_queue_wait_seconds_bucket{provider="local",le="+Inf"} 0
"""
    after = """concierge_database_errors_total{operation="query"} 4
concierge_ai_provider_queue_wait_seconds_bucket{provider="local",le="0.01"} 1
concierge_ai_provider_queue_wait_seconds_bucket{provider="local",le="0.1"} 3
concierge_ai_provider_queue_wait_seconds_bucket{provider="local",le="+Inf"} 3
"""
    assert _counter_delta(before, after, "concierge_database_errors_total") == 2
    assert _ai_wait_percentiles(before, after) == {"count": 3, "p50_ms": 100.0, "p95_ms": 100.0}


def test_loadtest_resource_metrics_are_read_from_api_process_scrape():
    payload = """concierge_app_process_cpu_percent 27.5
concierge_app_process_memory_percent 1.25
concierge_app_process_memory_bytes 2097152
"""
    assert _api_resource_sample(payload) == {
        "cpu_percent": 27.5,
        "memory_percent": 1.25,
        "rss_mb": 2.0,
    }


def test_loadtest_summary_reads_locust_aggregate_csv(tmp_path):
    path = tmp_path / "stats.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["Name", "Request Count", "Failure Count", "Requests/s", "50%", "95%", "99%"],
        )
        writer.writeheader()
        writer.writerow({"Name": "Aggregated", "Request Count": 100, "Failure Count": 2, "Requests/s": 10, "50%": 20, "95%": 80, "99%": 120})
    summary = _locust_summary(path)
    assert summary["success_rate_percent"] == 98
    assert summary["request_throughput_per_second"] == 10
    assert summary["http_latency_p50_ms"] == 20
    assert summary["http_latency_p95_ms"] == 80
    assert summary["http_latency_p99_ms"] == 120
