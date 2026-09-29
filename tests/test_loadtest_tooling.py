import os
from pathlib import Path
import subprocess
import sys
import csv
import json

from loadtest.run_stages import _ai_wait_percentiles, _api_resource_sample, _counter_delta, _locust_summary, _selected_profiles


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


def test_staff_conversation_load_flow_checks_both_absent_and_active_responses():
    script = r'''
from loadtest.locustfile import GuestUser

class FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.body = body
        self.outcome = None
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def json(self): return self.body
    def success(self): self.outcome = "success"
    def failure(self, message): self.outcome = message

class FakeClient:
    def __init__(self):
        self.all_responses = [
            FakeResponse(404, {"detail": "Staff conversation not found."}),
            FakeResponse(200, {"status": "waiting_for_staff"}),
            FakeResponse(200, {"state": "waiting_for_staff", "messages": []}),
        ]
        self.responses = list(self.all_responses)
        self.calls = []
    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.responses.pop(0)
    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.responses.pop(0)

user = GuestUser.__new__(GuestUser)
user.client_id = "load-guest"
user.session_id = "session-a"
user.session_headers = {"X-Concierge-Session": "session-a"}
user.restaurant_id = "restaurant-a"
user.staff_conversation_active = False
user.client = FakeClient()
user._start_staff_conversation_flow()
assert [call[0] for call in user.client.calls] == ["GET", "POST", "GET"]
assert user.client.calls[0][2]["name"].endswith("[no staff conversation]")
assert user.client.calls[1][2]["json"]["restaurant_id"] == "restaurant-a"
assert user.client.calls[2][2]["name"].endswith("[active staff conversation]")
assert user.staff_conversation_active is True
assert all(response.outcome == "success" for response in user.client.all_responses)
'''
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_load_smoke_requires_real_staff_conversation_when_requested(tmp_path):
    path = tmp_path / "staff-stats.csv"
    fields = ["Name", "Request Count", "Failure Count", "Requests/s", "50%", "95%", "99%"]
    required = [
        "GET /api/guest/conversations/{session_id}/staff-messages [no staff conversation]",
        "POST /api/guest/conversations/{session_id}/escalate [guest escalation]",
        "GET /api/guest/conversations/{session_id}/staff-messages [active staff conversation]",
    ]

    def run(names):
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerow({"Name": "Aggregated", "Request Count": 4, "Failure Count": 0})
            for name in names:
                writer.writerow({"Name": name, "Request Count": 1, "Failure Count": 0})
        return subprocess.run(
            [sys.executable, str(ROOT / "loadtest" / "assert_smoke.py"), str(path), "--require-staff-conversation"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    assert run(required).returncode == 0
    incomplete = run(required[:2])
    assert incomplete.returncode != 0
    assert "active staff conversation" in incomplete.stderr


def test_controlled_load_profile_has_requested_stages_and_metrics():
    profile = json.loads((ROOT / "loadtest" / "profiles.json").read_text(encoding="utf-8"))
    assert [stage["users"] for stage in profile["controlled_stages"]] == [10, 50, 100, 250, 500, 1000]
    assert {
        "success_rate_percent", "request_throughput_per_second", "http_latency_p50_ms",
        "http_latency_p95_ms", "http_latency_p99_ms", "http_errors", "database_errors",
        "cpu_percent_mean_max", "memory_percent_mean_max", "ai_provider_queue_wait_p50_p95_ms",
        "api_process_rss_mb_mean_max", "locust_failures", "rate_limit_events",
    } == set(profile["collected_metrics"])


def test_high_scale_spike_and_soak_profiles_are_defined_without_capacity_claims():
    profile = json.loads((ROOT / "loadtest" / "profiles.json").read_text(encoding="utf-8"))
    assert [stage["users"] for stage in profile["high_scale_profiles"]] == [5000, 10000, 30000]
    assert [stage["name"] for stage in _selected_profiles(profile, "high-scale")] == [
        "high-scale-5000", "high-scale-10000", "high-scale-30000"
    ]
    assert profile["spike_profile"]["warmup_users"] == 100
    assert profile["spike_profile"]["users"] == 5000
    assert profile["soak_profile"]["users"] == 5000
    assert profile["soak_profile"]["duration"] == "4h"
    assert any("not capacity claims" in item for item in profile["notes"])

    result = subprocess.run(
        [sys.executable, str(ROOT / "loadtest" / "run_stages.py"), "--help"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert all(name in result.stdout for name in ("controlled", "high-scale", "spike", "soak"))

    environment = os.environ.copy()
    environment["LOADTEST_SHAPE"] = "spike-100-to-5000"
    shape_check = subprocess.run(
        [
            sys.executable,
            "-c",
            "from loadtest.locustfile import SelectedCapacityShape; "
            "shape=SelectedCapacityShape(); elapsed=[0]; shape.get_run_time=lambda: elapsed[0]; "
            "assert shape.tick()==(100,10); elapsed[0]=60; assert shape.tick()==(5000,500); "
            "elapsed[0]=360; assert shape.tick() is None",
        ],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert shape_check.returncode == 0, shape_check.stderr


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
