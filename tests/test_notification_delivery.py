from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier
from types import SimpleNamespace
import importlib
import time
import uuid

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import create_engine, inspect

from app.hospitality import HospitalityStore
from app.properties import PropertyRecord, PropertyStore
import app.main as main_module


def _start_authenticated_guest(admin_client, property_id="test-property"):
    session = admin_client.post("/api/session/start", json={
        "client_id": f"notification-{uuid.uuid4().hex}", "property_id": property_id,
    })
    assert session.status_code == 200, session.text
    session_id = session.json()["session_id"]
    main_module.store.mark_authenticated(session_id)
    mac_suffix = uuid.uuid4().hex[:6]
    raw_mac = f"02:00:00:{mac_suffix[:2]}:{mac_suffix[2:4]}:{mac_suffix[4:6]}"
    device_id = main_module.guest_identities.observe_device(
        property_id, raw_mac,
    )
    stay = main_module.guest_identities.reconnect_or_create_stay(
        property_id, device_id, concierge_session_id=session_id,
    )
    return session_id, stay


def _guest_headers(session_id):
    return {"X-Concierge-Session": session_id}


def _queue(store, *, property_id="hotel-a", stay_id="stay-1", event_id="event-1", **overrides):
    values = {
        "category": "operational",
        "title": "Pool hours changed",
        "body": "The pool closes at 8 PM today.",
    }
    values.update(overrides)
    now = values.pop("now", 100)
    return store.create_guest_inbox_notification(
        property_id, stay_id, event_id, now=now, **values
    )


def test_schema_is_idempotent_and_notification_rules_remain_compatible(tmp_path):
    db_path = tmp_path / "hospitality.db"
    store = HospitalityStore(db_path)
    preferences = store.get_guest_notification_preferences("hotel-a", "stay-1")
    assert preferences == {
        "operational": True,
        "assistance": True,
        "experience": False,
        "promotional": False,
    }

    with pytest.raises(PermissionError):
        _queue(store, category="promotional")
    store.set_guest_notification_preference(
        "hotel-a", "stay-1", "promotional", True, now=101
    )
    queued = _queue(store, category="promotional", event_id="promo-1")

    rule = store.create_notification_rule(
        "hotel-a", {"name": "Existing rule", "category": "operational"}
    )
    legacy = store.evaluate_notification(
        "hotel-a", rule["rule_id"], "stay-1", {}, now=102
    )
    reopened = HospitalityStore(db_path)

    assert reopened.get_guest_notification_preferences("hotel-a", "stay-1")["promotional"] is True
    assert reopened.list_guest_inbox_notifications("hotel-a", "stay-1", now=103)[0]["notification_id"] == queued["notification_id"]
    assert reopened.list_guest_inbox_notifications("hotel-a", "stay-1", now=103)[0]["dispatch_status"] == "queued"
    assert legacy["allowed"] is True
    assert reopened.overview("hotel-a")["notification_rules"][0]["rule_id"] == rule["rule_id"]


def test_postgres_notification_migration_creates_dispatch_schema_idempotently():
    migration = importlib.import_module(
        "migrations.versions.20261015_0003_guest_notification_dispatch"
    )
    assert migration.down_revision == "20261015_0002"
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()
            migration.upgrade()
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        assert {
            "guest_privacy_consents",
            "guest_notification_preferences",
            "guest_inbox_notifications",
            "guest_notification_frequency_locks",
        } <= tables
        privacy_columns = {item["name"] for item in inspector.get_columns("guest_privacy_consents")}
        assert {"property_id", "session_id", "category", "granted", "stay_id", "updated_at", "expires_at"} <= privacy_columns
        assert "idx_guest_privacy_expiry" in {
            item["name"] for item in inspector.get_indexes("guest_privacy_consents")
        }
        columns = {item["name"] for item in inspector.get_columns("guest_inbox_notifications")}
        assert {
            "dispatch_status", "attempt_count", "next_attempt_at", "claim_token",
            "claimed_at", "dead_letter_at", "scheduled_at", "timezone_name",
            "quiet_hours", "send_window", "max_per_window", "frequency_window_seconds",
        } <= columns
        indexes = {item["name"] for item in inspector.get_indexes("guest_inbox_notifications")}
        assert {
            "idx_guest_inbox_scope_created", "idx_guest_inbox_expiry",
            "idx_guest_inbox_dispatch_due", "idx_guest_inbox_dispatch_frequency",
        } <= indexes
    engine.dispose()


def test_event_deduplication_is_scoped_and_content_is_bounded(tmp_path):
    store = HospitalityStore(tmp_path / "inbox.db")
    title = "Title " * 100
    body = "Body " * 1000
    first = _queue(store, event_id="same-event", title=title, body=body)
    retry = _queue(
        store,
        event_id="same-event",
        title="different retry payload",
        body="different retry body",
    )

    assert first["created"] is True
    assert retry["created"] is False
    assert retry["notification_id"] == first["notification_id"]
    assert retry["title"] == first["title"]
    assert retry["body"] == first["body"]
    assert len(first["title"]) <= 160
    assert len(first["body"]) <= 2000
    assert first["status"] == "queued"
    assert first["sent_at"] is first["delivered_at"] is first["read_at"] is None

    other_property = _queue(store, property_id="hotel-b", event_id="same-event")
    other_stay = _queue(store, stay_id="stay-2", event_id="same-event")
    assert len({first["notification_id"], other_property["notification_id"], other_stay["notification_id"]}) == 3


def test_concurrent_duplicate_creation_returns_one_stable_inbox_record(tmp_path):
    store = HospitalityStore(tmp_path / "race.db")
    calls = 16
    barrier = Barrier(calls)

    def create(index):
        barrier.wait(timeout=5)
        return _queue(
            store,
            event_id="race-event",
            title=f"Attempt {index}",
            body="Only one durable inbox record should exist.",
        )

    with ThreadPoolExecutor(max_workers=calls) as pool:
        results = list(pool.map(create, range(calls)))

    ids = {item["notification_id"] for item in results}
    assert len(ids) == 1
    assert sum(item["created"] for item in results) == 1
    assert len(store.list_guest_inbox_notifications("hotel-a", "stay-1")) == 1


def test_atomic_claim_is_durable_leased_and_requires_claim_token(tmp_path):
    db_path = tmp_path / "claims.db"
    store = HospitalityStore(db_path)
    queued = _queue(store, event_id="claim-me")

    first = store.claim_guest_inbox_notifications(now=100, lease_seconds=5)
    assert len(first) == 1
    assert first[0]["notification_id"] == queued["notification_id"]
    assert first[0]["dispatch_status"] == "sending"
    assert first[0]["attempt_count"] == 1
    assert first[0]["claim_token"]
    assert store.claim_guest_inbox_notifications(now=104, lease_seconds=5) == []

    reopened = HospitalityStore(db_path)
    persisted = reopened.list_guest_inbox_notifications("hotel-a", "stay-1", now=104)[0]
    assert persisted["dispatch_status"] == "sending"
    assert persisted["claim_token"] == first[0]["claim_token"]

    reclaimed = reopened.claim_guest_inbox_notifications(now=105, lease_seconds=5)
    assert len(reclaimed) == 1
    assert reclaimed[0]["attempt_count"] == 2
    assert reclaimed[0]["claim_token"] != first[0]["claim_token"]
    with pytest.raises(ValueError, match="claim is no longer active"):
        reopened.mark_guest_inbox_notification_sent(
            "hotel-a", "stay-1", queued["notification_id"], claim_token=first[0]["claim_token"], now=106,
        )
    sent = reopened.mark_guest_inbox_notification_sent(
        "hotel-a", "stay-1", queued["notification_id"], claim_token=reclaimed[0]["claim_token"], now=107,
    )
    assert sent["status"] == "sent"
    assert sent["dispatch_status"] == "sent"
    assert sent["claim_token"] is None


def test_concurrent_workers_atomically_claim_one_record(tmp_path):
    store = HospitalityStore(tmp_path / "claim-race.db")
    _queue(store, event_id="one-claim")
    workers = 12
    barrier = Barrier(workers)

    def claim(_index):
        barrier.wait(timeout=5)
        return store.claim_guest_inbox_notifications(now=100, limit=1)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        batches = list(pool.map(claim, range(workers)))

    claimed = [item for batch in batches for item in batch]
    assert len(claimed) == 1
    assert claimed[0]["dispatch_status"] == "sending"


def test_retry_backoff_is_bounded_and_dead_letters_are_visible(tmp_path):
    store = HospitalityStore(tmp_path / "retries.db")
    queued = _queue(store, event_id="retry-me")

    first = store.claim_guest_inbox_notifications(now=100)[0]
    retry_one = store.retry_guest_inbox_notification(
        "hotel-a", "stay-1", queued["notification_id"], first["claim_token"],
        "temporary failure", max_attempts=3, base_backoff_seconds=5, max_backoff_seconds=10, now=101,
    )
    assert retry_one["status"] == "queued"
    assert retry_one["dispatch_status"] == "retry_wait"
    assert retry_one["next_attempt_at"] == 106
    assert store.claim_guest_inbox_notifications(now=105) == []

    second = store.claim_guest_inbox_notifications(now=106)[0]
    retry_two = store.retry_guest_inbox_notification(
        "hotel-a", "stay-1", queued["notification_id"], second["claim_token"],
        "still unavailable", max_attempts=3, base_backoff_seconds=5, max_backoff_seconds=10, now=107,
    )
    assert retry_two["next_attempt_at"] == 117
    third = store.claim_guest_inbox_notifications(now=117)[0]
    dead = store.retry_guest_inbox_notification(
        "hotel-a", "stay-1", queued["notification_id"], third["claim_token"],
        "final failure", max_attempts=3, base_backoff_seconds=5, max_backoff_seconds=10, now=118,
    )
    assert dead["status"] == "failed"
    assert dead["dispatch_status"] == "dead_letter"
    assert dead["attempt_count"] == 3
    assert dead["dead_letter_at"] == 118
    assert dead["failure_reason"] == "final failure"
    assert store.list_guest_notification_dead_letters("hotel-a")[0]["notification_id"] == queued["notification_id"]
    assert store.list_guest_notification_dead_letters("hotel-b") == []


def test_due_scheduling_quiet_hours_timezone_and_frequency_limits(tmp_path):
    store = HospitalityStore(tmp_path / "schedule.db")
    at_manila_nine = int(datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc).timestamp())
    schedule_rule = store.create_notification_rule("hotel-a", {
        "name": "Manila morning window", "category": "operational",
        "policy": {
            "timezone": "Asia/Manila",
            "quiet_hours": {"start": "22:00", "end": "07:00"},
            "send_window": {"start": "09:00", "end": "17:00"},
        },
    })
    allowed = store.evaluate_notification(
        "hotel-a", schedule_rule["rule_id"], "stay-schedule", {}, now=at_manila_nine,
    )
    quiet = store.evaluate_notification(
        "hotel-a", schedule_rule["rule_id"], "stay-schedule-2", {},
        now=at_manila_nine + 13 * 60 * 60,
    )
    assert allowed["allowed"] is True
    assert quiet["allowed"] is False
    assert quiet["reason"] == "quiet_hours"

    future_rule = store.create_notification_rule("hotel-a", {
        "name": "Scheduled notice", "category": "operational",
        "policy": {"scheduled_at": at_manila_nine + 120},
    })
    not_yet = store.evaluate_notification(
        "hotel-a", future_rule["rule_id"], "stay-scheduled", {}, now=at_manila_nine,
    )
    due = store.evaluate_notification(
        "hotel-a", future_rule["rule_id"], "stay-scheduled", {}, now=at_manila_nine + 120,
    )
    assert not_yet["reason"] == "scheduled_for_later"
    assert due["allowed"] is True

    limited_rule = store.create_notification_rule("hotel-a", {
        "name": "Once per day", "category": "operational",
        "policy": {"frequency_limit": {"max": 1, "window_seconds": 86400}},
    })
    first = store.evaluate_notification(
        "hotel-a", limited_rule["rule_id"], "stay-frequency", {}, now=at_manila_nine,
    )
    second = store.evaluate_notification(
        "hotel-a", limited_rule["rule_id"], "stay-frequency", {}, now=at_manila_nine + 60,
    )
    assert first["allowed"] is True
    assert second["allowed"] is False
    assert second["reason"] == "frequency_limit"


def test_notification_rules_use_property_timezone_across_countries_and_dst(tmp_path):
    db_path = tmp_path / "property-clocks.db"
    properties = PropertyStore(db_path)
    store = HospitalityStore(db_path)
    cases = (
        ("singapore", "Asia/Singapore", True),
        ("australia", "Australia/Sydney", True),
        ("uae", "Asia/Dubai", False),
    )
    at_utc_midnight = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp())
    for property_id, zone, expected in cases:
        properties.upsert(PropertyRecord(property_id=property_id, hotel_name=property_id, timezone=zone))
        rule = store.create_notification_rule(property_id, {
            "name": "Local morning", "policy": {"send_window": {"start": "08:00", "end": "12:00"}},
        })
        result = store.evaluate_notification(property_id, rule["rule_id"], "stay", {}, now=at_utc_midnight)
        assert result["allowed"] is expected

    sydney_rule = store.create_notification_rule("australia", {
        "name": "Sydney summer hour", "policy": {"send_window": {"start": "11:00", "end": "12:00"}},
    })
    july = int(datetime(2026, 7, 1, tzinfo=timezone.utc).timestamp())
    assert store.evaluate_notification("australia", sydney_rule["rule_id"], "summer", {}, now=at_utc_midnight)["allowed"] is True
    assert store.evaluate_notification("australia", sydney_rule["rule_id"], "winter", {}, now=july)["reason"] == "outside_send_window"


def test_quiet_hours_follow_dst_gap_and_repeated_local_hour(tmp_path):
    properties = PropertyStore(tmp_path / "dst-quiet-hours.db")
    store = HospitalityStore(tmp_path / "dst-quiet-hours.db")
    properties.upsert(PropertyRecord(
        property_id="new-york-dst", hotel_name="DST Test Property", timezone="America/New_York",
    ))
    spring_rule = store.create_notification_rule("new-york-dst", {
        "name": "Spring quiet interval", "category": "operational",
        "policy": {"quiet_hours": {"start": "02:00", "end": "04:00"}},
    })
    fall_rule = store.create_notification_rule("new-york-dst", {
        "name": "Fall repeated hour", "category": "operational",
        "policy": {"quiet_hours": {"start": "01:00", "end": "02:00"}},
    })
    spring_after_jump = int(datetime(2026, 3, 8, 7, 30, tzinfo=timezone.utc).timestamp())
    fall_first_one_thirty = int(datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc).timestamp())
    fall_second_one_thirty = int(datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc).timestamp())

    assert store.evaluate_notification(
        "new-york-dst", spring_rule["rule_id"], "spring-stay", {}, now=spring_after_jump,
    )["reason"] == "quiet_hours"
    assert store.evaluate_notification(
        "new-york-dst", fall_rule["rule_id"], "fall-stay-a", {}, now=fall_first_one_thirty,
    )["reason"] == "quiet_hours"
    assert store.evaluate_notification(
        "new-york-dst", fall_rule["rule_id"], "fall-stay-b", {}, now=fall_second_one_thirty,
    )["reason"] == "quiet_hours"


def test_event_reminders_skip_unknown_property_timezone(monkeypatch):
    policy = {"guest_notification_delivery": {"event_reminders_enabled": True}}
    monkeypatch.setattr(
        main_module.properties, "get",
        lambda _property_id: SimpleNamespace(
            property_id="bad-timezone-property", timezone="Mars/Olympus_Mons", app_settings=policy,
        ),
    )
    assert main_module._queue_hotel_event_reminders(property_id="bad-timezone-property", now=100) == 0


def test_inbox_schedule_and_frequency_limits_are_enforced_on_atomic_claim(tmp_path):
    store = HospitalityStore(tmp_path / "inbox-schedule.db")
    at_utc_ten = int(datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc).timestamp())
    first = _queue(
        store, event_id="scheduled-first", now=at_utc_ten, scheduled_at=at_utc_ten + 100,
        timezone_name="UTC", send_window={"start": "08:00", "end": "22:00"},
        max_per_window=1, frequency_window_seconds=3600,
    )
    second = _queue(
        store, event_id="scheduled-second", now=at_utc_ten, scheduled_at=at_utc_ten + 101,
        timezone_name="UTC", send_window={"start": "08:00", "end": "22:00"},
        max_per_window=1, frequency_window_seconds=3600,
    )
    assert store.claim_guest_inbox_notifications(now=at_utc_ten + 99) == []
    with pytest.raises(ValueError, match="not due"):
        store.mark_guest_inbox_notification_sent(
            "hotel-a", "stay-1", first["notification_id"], now=at_utc_ten + 99,
        )
    with pytest.raises(ValueError, match="atomically claimed"):
        store.mark_guest_inbox_notification_sent(
            "hotel-a", "stay-1", first["notification_id"], now=at_utc_ten + 100,
        )
    claimed = store.claim_guest_inbox_notifications(now=at_utc_ten + 100)
    assert [item["notification_id"] for item in claimed] == [first["notification_id"]]
    store.mark_guest_inbox_notification_sent(
        "hotel-a", "stay-1", first["notification_id"],
        claim_token=claimed[0]["claim_token"], now=at_utc_ten + 100,
    )
    claimed_second = store.claim_guest_inbox_notifications(now=at_utc_ten + 101)
    assert claimed_second == []
    deferred = store.list_guest_inbox_notifications("hotel-a", "stay-1", now=at_utc_ten + 101)
    second_row = next(item for item in deferred if item["notification_id"] == second["notification_id"])
    assert second_row["dispatch_status"] == "retry_wait"
    assert second_row["next_attempt_at"] == at_utc_ten + 3700
    assert store.claim_guest_inbox_notifications(now=at_utc_ten + 3699) == []
    assert [item["notification_id"] for item in store.claim_guest_inbox_notifications(now=at_utc_ten + 3700)] == [second["notification_id"]]


def test_stale_claim_is_released_when_quiet_hours_begin(tmp_path):
    store = HospitalityStore(tmp_path / "stale-quiet.db")
    before_quiet = int(datetime(2026, 1, 1, 21, 59, tzinfo=timezone.utc).timestamp())
    queued = _queue(
        store, event_id="stale-quiet", now=before_quiet,
        quiet_hours={"start": "22:00", "end": "07:00"},
    )
    first = store.claim_guest_inbox_notifications(now=before_quiet, lease_seconds=5)
    assert [item["notification_id"] for item in first] == [queued["notification_id"]]
    assert store.claim_guest_inbox_notifications(now=before_quiet + 61, lease_seconds=5) == []
    row = store.list_guest_inbox_notifications("hotel-a", "stay-1", now=before_quiet + 61)[0]
    assert row["dispatch_status"] == "retry_wait"
    assert row["claim_token"] is None
    assert row["attempt_count"] == 1
    assert row["next_attempt_at"] >= before_quiet + 9 * 3600
    with pytest.raises(ValueError, match="claim is no longer active"):
        store.mark_guest_inbox_notification_sent(
            "hotel-a", "stay-1", queued["notification_id"],
            claim_token=first[0]["claim_token"], now=before_quiet + 62,
        )


def test_sent_delivery_and_read_require_distinct_evidence(tmp_path):
    store = HospitalityStore(tmp_path / "lifecycle.db")
    queued = _queue(store)
    assert queued["status"] == "queued"

    # Merely listing the queued row is not evidence that a client received it.
    listed = store.list_guest_inbox_notifications("hotel-a", "stay-1", now=110)[0]
    assert listed["status"] == "queued"
    assert listed["delivered_at"] is None
    with pytest.raises(ValueError, match="Cannot transition"):
        store.acknowledge_guest_inbox_notification(
            "hotel-a", "stay-1", queued["notification_id"], "delivered", now=111
        )

    sent = store.mark_guest_inbox_notification_sent(
        "hotel-a", "stay-1", queued["notification_id"], now=112
    )
    assert sent["status"] == "sent"
    assert sent["sent_at"] == 112
    assert sent["delivered_at"] is None
    with pytest.raises(ValueError, match="Cannot transition"):
        store.acknowledge_guest_inbox_notification(
            "hotel-a", "stay-1", queued["notification_id"], "read", now=112
        )
    delivered = store.acknowledge_guest_inbox_notification(
        "hotel-a", "stay-1", queued["notification_id"], "delivered", now=113
    )
    assert delivered["status"] == "delivered"
    assert delivered["delivered_at"] == 113

    # In-app read means the guest client explicitly acknowledged its read action.
    read = store.acknowledge_guest_inbox_notification(
        "hotel-a", "stay-1", queued["notification_id"], "read", now=115
    )
    assert read["status"] == "read"
    assert read["delivered_at"] == 113
    assert read["read_at"] == 115
    assert store.acknowledge_guest_inbox_notification(
        "hotel-a", "stay-1", queued["notification_id"], "read", now=116
    )["read_at"] == 115


def test_failure_and_expiry_are_terminal_and_timestamps_are_deterministic(tmp_path):
    store = HospitalityStore(tmp_path / "terminal.db")
    failed = _queue(store, event_id="failed")
    failed = store.fail_guest_inbox_notification(
        "hotel-a", "stay-1", failed["notification_id"], "dispatch unavailable", now=105
    )
    assert failed["status"] == "failed"
    assert failed["failed_at"] == 105
    assert failed["failure_reason"] == "dispatch unavailable"
    with pytest.raises(ValueError, match="Cannot transition"):
        store.mark_guest_inbox_notification_sent(
            "hotel-a", "stay-1", failed["notification_id"], now=106
        )

    expiring = _queue(store, event_id="expires", expires_at=120)
    other_guest = _queue(
        store, stay_id="stay-2", event_id="also-expires", expires_at=120
    )
    scoped = store.list_guest_inbox_notifications("hotel-a", "stay-1", now=120)
    expired = next(item for item in scoped if item["notification_id"] == expiring["notification_id"])
    assert expired["status"] == "expired"
    assert expired["expired_at"] == 120
    assert next(item for item in scoped if item["event_id"] == "failed")["status"] == "failed"

    # Listing one stay does not mutate another stay's inbox.
    assert next(
        item for item in store.list_guest_inbox_notifications("hotel-a", "stay-2", now=119)
        if item["notification_id"] == other_guest["notification_id"]
    )["status"] == "queued"
    assert store.expire_guest_inbox_notifications(now=120) == 1
    with pytest.raises(ValueError, match="Cannot transition"):
        store.mark_guest_inbox_notification_sent(
            "hotel-a", "stay-2", other_guest["notification_id"], now=121
        )


def test_guest_listing_and_acknowledgement_cannot_cross_property_or_stay(tmp_path):
    store = HospitalityStore(tmp_path / "scope.db")
    hotel_a = _queue(store, property_id="hotel-a", stay_id="stay-a", event_id="event")
    hotel_b = _queue(store, property_id="hotel-b", stay_id="stay-a", event_id="event")
    another_stay = _queue(store, property_id="hotel-a", stay_id="stay-b", event_id="event")

    assert [n["notification_id"] for n in store.list_guest_inbox_notifications("hotel-a", "stay-a")] == [hotel_a["notification_id"]]
    assert [n["notification_id"] for n in store.list_guest_inbox_notifications("hotel-b", "stay-a")] == [hotel_b["notification_id"]]
    assert [n["notification_id"] for n in store.list_guest_inbox_notifications("hotel-a", "stay-b")] == [another_stay["notification_id"]]
    with pytest.raises(KeyError, match="Notification not found"):
        store.acknowledge_guest_inbox_notification(
            "hotel-b", "stay-a", hotel_a["notification_id"], "delivered"
        )
    with pytest.raises(KeyError, match="Notification not found"):
        store.acknowledge_guest_inbox_notification(
            "hotel-a", "stay-b", hotel_a["notification_id"], "delivered"
        )


def test_checkout_expires_pending_and_visible_inbox_items(tmp_path):
    store = HospitalityStore(tmp_path / "checkout-expiry.db")
    pending = _queue(store, event_id="pending-at-checkout")
    visible = _queue(store, event_id="visible-at-checkout")
    claim = next(
        item for item in store.claim_guest_inbox_notifications(now=100, limit=2)
        if item["notification_id"] == visible["notification_id"]
    )
    store.mark_guest_inbox_notification_sent(
        "hotel-a", "stay-1", visible["notification_id"], claim_token=claim["claim_token"], now=101,
    )

    assert store.expire_guest_inbox_for_stay("hotel-a", "stay-1", now=102) == 2
    rows = {item["notification_id"]: item for item in store.list_guest_inbox_notifications("hotel-a", "stay-1", now=103)}
    assert rows[pending["notification_id"]]["status"] == "expired"
    assert rows[visible["notification_id"]]["status"] == "expired"
    assert rows[visible["notification_id"]]["dispatch_status"] == "expired"


def test_checkout_purges_read_and_pending_content_without_cross_property_deletion(tmp_path):
    store = HospitalityStore(tmp_path / "checkout-purge.db")
    pending = _queue(store, event_id="pending")
    read_item = _queue(store, event_id="read")
    other_property = _queue(store, property_id="hotel-b", event_id="other")
    store.mark_guest_inbox_notification_sent("hotel-a", "stay-1", read_item["notification_id"], now=101)
    store.acknowledge_guest_inbox_notification("hotel-a", "stay-1", read_item["notification_id"], "delivered", now=102)
    store.acknowledge_guest_inbox_notification("hotel-a", "stay-1", read_item["notification_id"], "read", now=103)
    assert store.purge_guest_inbox_for_stay("hotel-a", "stay-1") == 2
    assert store.purge_guest_inbox_for_stay("hotel-a", "stay-1") == 0
    assert store.list_guest_inbox_notifications("hotel-a", "stay-1", now=104) == []
    assert store.list_guest_inbox_notifications("hotel-b", "stay-1", now=104)[0]["notification_id"] == other_property["notification_id"]


def test_preferences_are_guest_scoped_and_input_validation_is_strict(tmp_path):
    store = HospitalityStore(tmp_path / "preferences.db")
    store.set_guest_notification_preference("hotel-a", "stay-a", "experience", True, now=100)
    assert store.get_guest_notification_preferences("hotel-a", "stay-a")["experience"] is True
    assert store.get_guest_notification_preferences("hotel-a", "stay-b")["experience"] is False
    assert store.get_guest_notification_preferences("hotel-b", "stay-a")["experience"] is False
    with pytest.raises(ValueError, match="Invalid notification category"):
        store.set_guest_notification_preference("hotel-a", "stay-a", "unknown", True)
    with pytest.raises(ValueError, match="must be a boolean"):
        store.set_guest_notification_preference("hotel-a", "stay-a", "promotional", 1)
    with pytest.raises(ValueError, match="title and body"):
        _queue(store, event_id="empty", title="  ", body=" \n ")


def test_guest_notification_api_requires_linked_stay_and_optional_consent(admin_client):
    session = admin_client.post("/api/session/start", json={
        "client_id": f"notification-unlinked-{uuid.uuid4().hex}", "property_id": "test-property",
    })
    assert session.status_code == 200, session.text
    session_id = session.json()["session_id"]
    headers = _guest_headers(session_id)

    inbox = admin_client.get("/api/guest/notifications", headers=headers)
    assert inbox.status_code == 200, inbox.text
    assert inbox.json()["notifications"] == []
    assert inbox.json()["can_manage"] is False
    denied = admin_client.put(
        "/api/guest/notifications/preferences",
        json={"category": "experience", "enabled": True}, headers=headers,
    )
    assert denied.status_code == 409

    main_module.store.mark_authenticated(session_id)
    device_id = main_module.guest_identities.observe_device("test-property", "02:00:00:00:00:ab")
    stay = main_module.guest_identities.reconnect_or_create_stay(
        "test-property", device_id, concierge_session_id=session_id,
    )
    consent_required = admin_client.put(
        "/api/guest/notifications/preferences",
        json={"category": "experience", "enabled": True}, headers=headers,
    )
    assert consent_required.status_code == 409
    grant = admin_client.put("/api/guest/privacy", json={
        "session_id": session_id, "consents": {"proactive_notifications": True},
    })
    assert grant.status_code == 200, grant.text
    saved = admin_client.put(
        "/api/guest/notifications/preferences",
        json={"category": "experience", "enabled": True}, headers=headers,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["preferences"]["experience"] is True
    assert main_module.guest_identities.active_stay_for_session("test-property", session_id)["stay_id"] == stay["stay_id"]


def test_service_status_update_reaches_only_the_active_guest_inbox(admin_client):
    property_record = main_module.properties.get("test-property")
    property_record.app_settings = {"guest_notification_delivery": {"quiet_hours": {}}}
    main_module.properties.upsert(property_record)
    session_id, stay = _start_authenticated_guest(admin_client)
    request_record = main_module.hospitality.create_service_request("test-property", {
        "stay_id": session_id,
        "request_type": "Towel request",
        "description": "Please bring two towels to room 407.",
        "room": "407",
    })

    updated = admin_client.put(
        f"/api/admin/properties/test-property/service-requests/{request_record['request_id']}/status",
        json={"status": "in_progress"},
    )
    assert updated.status_code == 200, updated.text
    inbox = admin_client.get("/api/guest/notifications", headers=_guest_headers(session_id))
    assert inbox.status_code == 200, inbox.text
    item = inbox.json()["notifications"][0]
    assert item["status"] == "sent"
    assert item["category"] == "operational"
    assert item["title"] == "Service request update"
    assert "in progress" in item["body"]
    assert "room 407" not in item["body"]
    assert "407" not in item["body"]
    assert "event_id" not in item and "stay_id" not in item and "property_id" not in item

    delivered = admin_client.post(
        f"/api/guest/notifications/{item['notification_id']}/ack",
        json={"action": "delivered"}, headers=_guest_headers(session_id),
    )
    assert delivered.status_code == 200, delivered.text
    assert delivered.json()["status"] == "delivered"
    read = admin_client.post(
        f"/api/guest/notifications/{item['notification_id']}/ack",
        json={"action": "read"}, headers=_guest_headers(session_id),
    )
    assert read.status_code == 200, read.text
    assert read.json()["status"] == "read"
    assert main_module.hospitality.list_guest_inbox_notifications("test-property", stay["stay_id"])[0]["status"] == "read"


def test_opted_out_operational_notifications_do_not_change_request_status_delivery(admin_client):
    session_id, stay = _start_authenticated_guest(admin_client)
    main_module.hospitality.set_guest_notification_preference(
        "test-property", stay["stay_id"], "operational", False,
    )
    request_record = main_module.hospitality.create_service_request("test-property", {
        "stay_id": session_id, "request_type": "Towel request", "description": "Bring towels.",
    })
    updated = admin_client.put(
        f"/api/admin/properties/test-property/service-requests/{request_record['request_id']}/status",
        json={"status": "accepted"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "accepted"
    inbox = admin_client.get("/api/guest/notifications", headers=_guest_headers(session_id))
    assert inbox.status_code == 200, inbox.text
    assert inbox.json()["notifications"] == []


def test_notification_evaluation_cannot_trust_caller_preferences_or_inactive_stays(admin_client):
    _session_id, stay = _start_authenticated_guest(admin_client)
    rule = main_module.hospitality.create_notification_rule("test-property", {
        "name": "Optional experience", "category": "experience", "policy": {},
    })
    spoofed = admin_client.post(
        f"/api/admin/properties/test-property/notifications/rules/{rule['rule_id']}/evaluate",
        json={
            "stay_id": stay["stay_id"], "verified_payload": {"event": "synthetic"},
            "guest_preferences": {"proactive_notifications": True},
        },
    )
    assert spoofed.status_code == 422

    main_module.guest_identities.checkout("test-property", stay["stay_id"])
    inactive = admin_client.post(
        f"/api/admin/properties/test-property/notifications/rules/{rule['rule_id']}/evaluate",
        json={"stay_id": stay["stay_id"], "verified_payload": {"event": "synthetic"}},
    )
    assert inactive.status_code == 409


def test_verified_hotel_event_reaches_only_consented_guest_once(admin_client):
    property_id = f"event-property-{uuid.uuid4().hex[:10]}"
    main_module.properties.upsert(PropertyRecord(
        property_id=property_id, hotel_name="Verified Event Hotel", timezone="Asia/Singapore",
        app_settings={"guest_notification_delivery": {
            "event_reminders_enabled": True, "event_reminder_minutes": 30,
            "quiet_hours": {}, "send_window": {},
        }},
    ))
    opted_session, opted_stay = _start_authenticated_guest(admin_client, property_id)
    disabled_session, disabled_stay = _start_authenticated_guest(admin_client, property_id)
    main_module.hospitality.set_guest_notification_preference(
        property_id, opted_stay["stay_id"], "experience", True,
    )
    main_module.hospitality.set_guest_notification_preference(
        property_id, disabled_stay["stay_id"], "experience", True,
    )
    main_module.privacy_consents.set(
        property_id, opted_session, {"proactive_notifications": True},
    )
    now = int(time.time())
    event = main_module.hospitality.create_event(property_id, {
        "title": "Poolside film", "starts_at": now + 120,
        "status": "scheduled", "audience": "all_guests",
    })
    assert main_module._queue_hotel_event_reminders(property_id=property_id, now=now) == 1
    assert main_module._queue_hotel_event_reminders(property_id=property_id, now=now) == 0
    assert main_module._dispatch_guest_inbox_notifications(property_id=property_id) == 1
    opted = main_module.hospitality.list_guest_inbox_notifications(property_id, opted_stay["stay_id"])
    disabled = main_module.hospitality.list_guest_inbox_notifications(property_id, disabled_stay["stay_id"])
    assert len(opted) == 1 and opted[0]["status"] == "sent"
    assert opted[0]["event_id"] == f"hotel-event:{event['event_id']}:{now + 120}"
    assert "Poolside film" in opted[0]["body"]
    assert disabled == []


def test_withdrawing_proactive_consent_immediately_removes_optional_notifications(admin_client):
    session_id, stay = _start_authenticated_guest(admin_client)
    stay_id = stay["stay_id"]
    second_session_response = admin_client.post("/api/session/start", json={
        "client_id": f"notification-linked-{uuid.uuid4().hex}", "property_id": "test-property",
    })
    assert second_session_response.status_code == 200, second_session_response.text
    second_session_id = second_session_response.json()["session_id"]
    main_module.store.mark_authenticated(second_session_id)
    device_id = next(
        row["device_id"] for row in main_module.guest_identities.list_guest_sessions("test-property")
        if row["stay_id"] == stay_id
    )
    linked = main_module.guest_identities.reconnect_or_create_stay(
        "test-property", device_id, concierge_session_id=second_session_id,
    )
    assert linked["stay_id"] == stay_id
    main_module.privacy_consents.set(
        "test-property", session_id, {"proactive_notifications": True},
    )
    main_module.privacy_consents.set(
        "test-property", second_session_id, {"proactive_notifications": True},
        linked_stay_id=stay_id,
    )
    main_module.hospitality.set_guest_notification_preference(
        "test-property", stay_id, "experience", True,
    )
    optional = _queue(
        main_module.hospitality, property_id="test-property", stay_id=stay_id,
        event_id=f"withdraw-{uuid.uuid4().hex}", category="experience",
    )
    operational = _queue(
        main_module.hospitality, property_id="test-property", stay_id=stay_id,
        event_id=f"operational-{uuid.uuid4().hex}",
    )
    response = admin_client.put("/api/guest/privacy", json={
        "session_id": session_id, "consents": {"proactive_notifications": False},
    })
    assert response.status_code == 200, response.text
    assert main_module.privacy_consents.get("test-property", session_id)["proactive_notifications"] is False
    assert main_module.privacy_consents.get("test-property", second_session_id)["proactive_notifications"] is False
    rows = main_module.hospitality.list_guest_inbox_notifications("test-property", stay_id)
    assert [row["notification_id"] for row in rows] == [operational["notification_id"]]
    assert optional["notification_id"] not in {row["notification_id"] for row in rows}

    reconsented = admin_client.put("/api/guest/privacy", json={
        "session_id": session_id, "consents": {"proactive_notifications": True},
    })
    assert reconsented.status_code == 200, reconsented.text
    suppressed = main_module.hospitality.create_guest_inbox_notification(
        "test-property", stay_id, optional["event_id"], "experience",
        "Poolside reminder", "Previously withdrawn event reminder.",
    )
    assert suppressed["suppressed"] is True
    assert suppressed["created"] is False
    assert [row["notification_id"] for row in main_module.hospitality.list_guest_inbox_notifications("test-property", stay_id)] == [
        operational["notification_id"],
    ]


def test_retention_worker_recovers_interrupted_optional_notification_withdrawal(admin_client):
    session_id, stay = _start_authenticated_guest(admin_client)
    stay_id = stay["stay_id"]
    granted = admin_client.put("/api/guest/privacy", json={
        "session_id": session_id, "consents": {"proactive_notifications": True},
    })
    assert granted.status_code == 200, granted.text
    main_module.hospitality.set_guest_notification_preference(
        "test-property", stay_id, "experience", True,
    )
    notification = _queue(
        main_module.hospitality, property_id="test-property", stay_id=stay_id,
        event_id=f"interrupted-withdrawal-{uuid.uuid4().hex}", category="experience",
    )

    # Simulate a process restart after consent persistence but before the API's
    # immediate inbox purge.
    main_module.privacy_consents.set(
        "test-property", session_id, {"proactive_notifications": False},
        linked_stay_id=stay_id,
    )
    main_module.hospitality.cleanup_guest_inbox_retention()

    assert main_module.hospitality.list_guest_inbox_notifications("test-property", stay_id) == []
    requeued = main_module.hospitality.create_guest_inbox_notification(
        "test-property", stay_id, notification["event_id"], "experience",
        "Old reminder", "This content was withdrawn.",
    )
    assert requeued["suppressed"] is True
