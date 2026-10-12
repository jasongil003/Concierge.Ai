"""Daytime quiet hours must not suppress every notification of the day."""

from types import SimpleNamespace

import pytest

from app.hospitality import HospitalityStore


@pytest.mark.parametrize("start,end,hour,allowed", [
    (9, 17, 8, True), (9, 17, 9, False), (9, 17, 16, False),
    (9, 17, 17, True), (9, 17, 23, True),
    (22, 7, 6, False), (22, 7, 7, True), (22, 7, 21, True), (22, 7, 22, False),
])
def test_notification_quiet_interval_boundaries(tmp_path, monkeypatch, start, end, hour, allowed):
    monkeypatch.setattr("app.hospitality.time.localtime", lambda moment: SimpleNamespace(tm_hour=hour))
    store = HospitalityStore(tmp_path / "quiet-hours.db")
    rule = store.create_notification_rule("synthetic", {
        "name": "Quiet hours", "category": "operational",
        "policy": {"quiet_hours": {"start": start, "end": end}},
    })
    result = store.evaluate_notification("synthetic", rule["rule_id"], "synthetic-stay", {}, now=123456)
    assert result["allowed"] is allowed
    assert result["reason"] == ("eligible" if allowed else "quiet_hours")
