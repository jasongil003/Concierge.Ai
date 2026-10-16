import json
import sqlite3
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .database import connect_database


def _now() -> int:
    return int(time.time())


class LocationAnalyticsStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return connect_database(self.path)

    def _init_db(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS location_observations (
                    observation_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    stay_id TEXT,
                    access_point_identifier TEXT NOT NULL,
                    zone_id TEXT NOT NULL,
                    observed_at INTEGER NOT NULL,
                    source TEXT NOT NULL DEFAULT 'antlabs'
                );
                CREATE TABLE IF NOT EXISTS zone_visits (
                    visit_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    stay_id TEXT,
                    zone_id TEXT NOT NULL,
                    entered_at INTEGER NOT NULL,
                    exited_at INTEGER,
                    dwell_seconds INTEGER
                );
                CREATE TABLE IF NOT EXISTS movement_transitions (
                    transition_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    stay_id TEXT,
                    device_id TEXT NOT NULL,
                    source_zone_id TEXT NOT NULL,
                    destination_zone_id TEXT NOT NULL,
                    occurred_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ai_interaction_events (
                    event_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    stay_id TEXT,
                    event_type TEXT NOT NULL,
                    facility_id TEXT,
                    zone_id TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS facility_conversion_events (
                    conversion_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    stay_id TEXT,
                    source_event_id TEXT,
                    facility_id TEXT,
                    zone_id TEXT,
                    observed_at INTEGER NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_location_observations_property_time
                    ON location_observations(property_id, observed_at);
                CREATE INDEX IF NOT EXISTS idx_zone_visits_property_time
                    ON zone_visits(property_id, entered_at);
                CREATE INDEX IF NOT EXISTS idx_movement_transitions_property_time
                    ON movement_transitions(property_id, occurred_at);
                """
            )

    def record_observation(
        self,
        property_id: str,
        device_id: str,
        zone_id: str,
        access_point_identifier: str,
        stay_id: str | None = None,
        observed_at: int | None = None,
        source: str = "antlabs",
    ) -> dict[str, Any]:
        observed = observed_at or _now()
        observation = {
            "observation_id": "obs_" + uuid.uuid4().hex[:16],
            "property_id": property_id,
            "device_id": device_id,
            "stay_id": stay_id,
            "access_point_identifier": access_point_identifier,
            "zone_id": zone_id,
            "observed_at": observed,
            "source": source,
        }
        with self._connect() as db:
            previous = db.execute(
                "SELECT * FROM zone_visits WHERE property_id=? AND device_id=? AND exited_at IS NULL ORDER BY entered_at DESC LIMIT 1",
                (property_id, device_id),
            ).fetchone()
            db.execute(
                "INSERT INTO location_observations VALUES (:observation_id,:property_id,:device_id,:stay_id,:access_point_identifier,:zone_id,:observed_at,:source)",
                observation,
            )
            if previous is None:
                self._insert_visit(db, property_id, device_id, stay_id, zone_id, observed)
            elif previous["zone_id"] != zone_id:
                dwell = max(0, observed - previous["entered_at"])
                db.execute(
                    "UPDATE zone_visits SET exited_at=?, dwell_seconds=? WHERE visit_id=?",
                    (observed, dwell, previous["visit_id"]),
                )
                db.execute(
                    "INSERT INTO movement_transitions VALUES (?,?,?,?,?,?,?)",
                    ("move_" + uuid.uuid4().hex[:16], property_id, stay_id, device_id, previous["zone_id"], zone_id, observed),
                )
                self._insert_visit(db, property_id, device_id, stay_id, zone_id, observed)
        return observation

    def _insert_visit(self, db: sqlite3.Connection, property_id: str, device_id: str, stay_id: str | None, zone_id: str, entered_at: int) -> None:
        db.execute(
            "INSERT INTO zone_visits VALUES (?,?,?,?,?,?,?,?)",
            ("visit_" + uuid.uuid4().hex[:16], property_id, device_id, stay_id, zone_id, entered_at, None, None),
        )

    def delete_stay_data(self, property_id: str, stay_id: str) -> int:
        """Erase location and facility analytics linked to one checked-out stay."""
        tables = (
            "location_observations",
            "zone_visits",
            "movement_transitions",
            "ai_interaction_events",
            "facility_conversion_events",
        )
        deleted = 0
        with self._connect() as db:
            for table in tables:
                # Table names come only from the fixed tuple above.
                cursor = db.execute(
                    f"DELETE FROM {table} WHERE property_id=? AND stay_id=?",  # nosec B608
                    (property_id, stay_id),
                )
                deleted += cursor.rowcount
        return deleted

    def cleanup_retention(self, now: int | None = None) -> int:
        """Purge records without a currently active stay."""
        tables = (
            "location_observations",
            "zone_visits",
            "movement_transitions",
            "ai_interaction_events",
            "facility_conversion_events",
        )
        deleted = 0
        with self._connect() as db:
            for table in tables:
                # Table names come only from the fixed tuple above.
                cursor = db.execute(
                    f"""DELETE FROM {table}
                    WHERE stay_id IS NULL OR NOT EXISTS (
                        SELECT 1 FROM concierge_stays s
                        WHERE s.property_id={table}.property_id
                          AND s.stay_id={table}.stay_id
                          AND s.status='active'
                    )""",  # nosec B608
                    (),
                )
                deleted += cursor.rowcount
        return deleted

    def record_ai_event(self, property_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        record = {
            "event_id": "aie_" + uuid.uuid4().hex[:16],
            "property_id": property_id,
            "stay_id": payload.get("stay_id"),
            "event_type": str(payload.get("event_type") or "facility_inquiry")[:80],
            "facility_id": payload.get("facility_id"),
            "zone_id": payload.get("zone_id"),
            "metadata": json.dumps(payload.get("metadata") or {}),
            "created_at": _now(),
        }
        with self._connect() as db:
            db.execute("INSERT INTO ai_interaction_events VALUES (:event_id,:property_id,:stay_id,:event_type,:facility_id,:zone_id,:metadata,:created_at)", record)
        record["metadata"] = json.loads(record["metadata"])
        return record

    def live(self, property_id: str) -> dict[str, Any]:
        cutoff = _now() - 15 * 60
        with self._connect() as db:
            rows = [dict(row) for row in db.execute("SELECT * FROM location_observations WHERE property_id=? AND observed_at>=?", (property_id, cutoff))]
        latest_by_device: dict[str, dict[str, Any]] = {}
        for row in rows:
            current = latest_by_device.get(row["device_id"])
            if current is None or row["observed_at"] > current["observed_at"]:
                latest_by_device[row["device_id"]] = row
        occupancy = Counter(row["zone_id"] for row in latest_by_device.values())
        busiest = occupancy.most_common(1)[0][0] if occupancy else None
        return {
            "currently_detected": len(latest_by_device),
            "active_sessions": len({row.get("stay_id") for row in latest_by_device.values() if row.get("stay_id")}),
            "busiest_zone_id": busiest,
            "occupancy_by_zone": dict(occupancy),
        }

    def aggregate(
        self,
        property_id: str,
        start_at: int,
        end_at: int,
        filters: dict[str, Any] | None = None,
        timezone_name: str = "UTC",
    ) -> dict[str, Any]:
        if end_at < start_at:
            raise ValueError("Report end must be at or after its start.")
        try:
            report_timezone = ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Report timezone must be a valid IANA timezone.") from exc
        filters = filters or {}
        params: list[Any] = [property_id, start_at, end_at]
        where = "property_id=? AND entered_at>=? AND entered_at<=?"
        if filters.get("zone_id"):
            where += " AND zone_id=?"
            params.append(filters["zone_id"])
        with self._connect() as db:
            # B608 rationale: where contains only fixed predicates appended above; zone values are bound.
            visits = [dict(row) for row in db.execute(f"SELECT * FROM zone_visits WHERE {where}", params)]  # nosec B608
            transitions = [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM movement_transitions WHERE property_id=? AND occurred_at>=? AND occurred_at<=?",
                    (property_id, start_at, end_at),
                )
            ]
            observation_params: list[Any] = [property_id, start_at, end_at]
            observation_where = "property_id=? AND observed_at>=? AND observed_at<=?"
            if filters.get("zone_id"):
                observation_where += " AND zone_id=?"
                observation_params.append(filters["zone_id"])
            # B608 rationale: predicates are fixed and zone_id is always bound.
            observations = db.execute(
                f"SELECT device_id, observed_at FROM location_observations WHERE {observation_where}",  # nosec B608
                observation_params,
            ).fetchall()
        observed_devices_by_local_hour: dict[tuple[str, int], set[str]] = defaultdict(set)
        for row in observations:
            try:
                local_time = datetime.fromtimestamp(int(row["observed_at"]), report_timezone)
            except (OverflowError, OSError, ValueError) as exc:
                raise ValueError("Observation timestamp is outside the supported reporting range.") from exc
            observed_devices_by_local_hour[(local_time.date().isoformat(), local_time.hour)].add(str(row["device_id"]))
        devices_by_hour: dict[int, list[int]] = defaultdict(list)
        for (_, hour), devices in observed_devices_by_local_hour.items():
            devices_by_hour[hour].append(len(devices))
        hourly_observed_devices = [
            {
                "hour": hour,
                "average_observed_devices": round(sum(counts) / len(counts), 2),
                "sample_days": len(counts),
            }
            for hour, counts in sorted(devices_by_hour.items())
        ]
        peak_average = max(
            (item["average_observed_devices"] for item in hourly_observed_devices),
            default=0,
        )
        peak_hours = [
            item for item in hourly_observed_devices
            if peak_average > 0 and item["average_observed_devices"] == peak_average
        ]
        by_zone: dict[str, dict[str, Any]] = defaultdict(lambda: {"visits": 0, "unique_devices": set(), "dwell": [], "peak_occupancy": 0})
        for visit in visits:
            zone = by_zone[visit["zone_id"]]
            zone["visits"] += 1
            zone["unique_devices"].add(visit["device_id"])
            if visit.get("dwell_seconds") is not None:
                zone["dwell"].append(visit["dwell_seconds"])
        area_metrics = {}
        for zone_id, metric in by_zone.items():
            dwell = metric["dwell"]
            area_metrics[zone_id] = {
                "total_visits": metric["visits"],
                "unique_visitors": len(metric["unique_devices"]),
                "average_dwell_seconds": int(sum(dwell) / len(dwell)) if dwell else 0,
                "repeat_visits": max(0, metric["visits"] - len(metric["unique_devices"])),
            }
        transition_counts = Counter((row["source_zone_id"], row["destination_zone_id"]) for row in transitions)
        total_transitions = sum(transition_counts.values()) or 1
        movement = [
            {
                "source_zone_id": source,
                "destination_zone_id": destination,
                "count": count,
                "percentage": round(count * 100 / total_transitions, 2),
            }
            for (source, destination), count in transition_counts.most_common()
        ]
        return {
            "period": {"start_at": start_at, "end_at": end_at},
            "timezone": timezone_name,
            "total_visits": len(visits),
            "unique_visits": len({row["device_id"] for row in visits}),
            "area_metrics": area_metrics,
            "movement_patterns": movement,
            "hourly_observed_devices": hourly_observed_devices,
            "peak_hours": peak_hours,
        }
