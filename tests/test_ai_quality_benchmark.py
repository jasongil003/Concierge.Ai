"""Deterministic guardrail slice of the synthetic concierge quality benchmark."""

import json
from collections import Counter
from pathlib import Path

import pytest

from app import main as main_module
from app.guest_actions import GuestActionRegistry


BENCHMARK_PATH = Path(__file__).with_name("ai_quality_benchmark.json")
BENCHMARK = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
CASES = BENCHMARK["cases"]


def test_ai_quality_benchmark_has_required_synthetic_scenario_counts():
    counts = Counter(case["category"] for case in CASES)
    assert len(CASES) == 100
    assert len({case["id"] for case in CASES}) == len(CASES)
    assert counts == BENCHMARK["category_minimums"]
    assert all(case["live_provider_status"] == "not_run" for case in CASES)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_ai_quality_benchmark_deterministic_action_routing(case: dict[str, str]):
    category = case["category"]
    message = case["prompt"]
    routed_as_service = main_module._is_guest_service_request(message)

    if category == "service_request":
        assert routed_as_service, message
    elif category == "dining":
        assert main_module._is_intelligent_dining_request(message), message
        assert not routed_as_service, message
    elif category == "adversarial":
        if routed_as_service:
            # A malicious instruction may resemble a request, but the server
            # still requires the signed, session/property-bound confirmation.
            definition = GuestActionRegistry().get("service_request.create")
            assert definition is not None and definition.confirmation_required
    else:
        assert not routed_as_service, message
