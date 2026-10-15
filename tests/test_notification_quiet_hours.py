"""Daytime quiet hours must not suppress every notification of the day."""

from datetime import datetime, timezone

import pytest

from app.hospitality import HospitalityStore


@pytest.mark.parametrize("start,end,hour,allowed", [
    (9, 17, 8, True), (9, 17, 9, False), (9, 17, 16, False),
    (9, 17, 17, True), (9, 17, 23, True),
    (22, 7, 6, False), (22, 7, 7, True), (22, 7, 21, True), (22, 7, 22, False),
])
def test_notification_quiet_interval_boundaries(tmp_path, start, end, hour, allowed):
    store = HospitalityStore(tmp_path / "quiet-hours.db")
    rule = store.create_notification_rule("synthetic", {
        "name": "Quiet hours", "category": "operational",
        "policy": {"timezone": "UTC", "quiet_hours": {"start": start, "end": end}},
    })
    moment = int(datetime(2026, 1, 1, hour, tzinfo=timezone.utc).timestamp())
    result = store.evaluate_notification("synthetic", rule["rule_id"], "synthetic-stay", {}, now=moment)
    assert result["allowed"] is allowed
    assert result["reason"] == ("eligible" if allowed else "quiet_hours")
