#!/usr/bin/env python3
"""Import RWG Hotel Knowledge Package v2 into existing property knowledge scopes.

The command is a dry run unless --apply is supplied. It only inserts new,
dataset-namespaced knowledge rows and refuses to replace conflicting rows.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.rwg_knowledge import build_import_plan, default_property_map, load_rwg_package  # noqa: E402


PROPERTY_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _property_map(value: str | None, package) -> dict[str, str]:
    if not value:
        result = default_property_map(package)
    else:
        path = Path(value)
        try:
            raw = path.read_text(encoding="utf-8") if path.is_file() else value
            result = json.loads(raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("--property-map must be JSON text or a readable JSON file.") from exc
    if not isinstance(result, dict) or any(not isinstance(key, str) or not isinstance(item, str) for key, item in result.items()):
        raise ValueError("--property-map must be a JSON object of package hotel IDs to Concierge property IDs.")
    if any(not PROPERTY_ID_PATTERN.fullmatch(item) for item in result.values()):
        raise ValueError("Concierge property IDs must use lowercase letters, digits, hyphens, or underscores (up to 64 characters).")
    return result


def _create_property_scopes(property_store: PropertyStore, package, property_map: dict[str, str]) -> list[str]:
    from app.properties import PropertyRecord

    hotel_by_id = {str(item["id"]): item for item in package.hotel_knowledge["hotels"]}
    created: list[str] = []
    for hotel_id, property_id in property_map.items():
        if property_store.get(property_id) is not None:
            continue
        hotel = hotel_by_id[hotel_id]
        created_scope = property_store.create_if_absent(PropertyRecord(
            property_id=property_id,
            hotel_name=str(hotel.get("name") or property_id)[:160],
            description=str(hotel.get("description") or "")[:1000],
            timezone=str(hotel.get("time_zone") or "UTC")[:80],
            address=str(hotel.get("location") or "")[:500],
            contact_details={
                key: value for key, value in (hotel.get("contact") or {}).items()
                if key in {"email", "telephone"} and isinstance(value, str) and value.strip()
            },
        ))
        if not created_scope:
            raise RuntimeError(f"Property scope {property_id!r} appeared during import; it was left unchanged. Review the mapping and retry.")
        created.append(property_id)
    return created


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="RWG v2 ZIP package")
    parser.add_argument(
        "--property-map",
        help="JSON object or file mapping package hotel IDs to existing Concierge property IDs; defaults to rwg-<hotel-id>",
    )
    parser.add_argument("--apply", action="store_true", help="Write the additive import to the configured database")
    parser.add_argument(
        "--create-property-scopes",
        action="store_true",
        help="Create missing property records with empty domains before import; never updates existing property profiles",
    )
    args = parser.parse_args(argv)

    try:
        package = load_rwg_package(args.archive)
        property_map = _property_map(args.property_map, package)
        records, report = build_import_plan(package, property_map)
        if not args.apply:
            report["mode"] = "dry_run"
            report["database_modified"] = False
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0

        from app.config import settings
        from app.operations import OperationsStore
        from app.properties import PropertyRecord, PropertyStore

        deployment_mode = str(getattr(settings, "deployment_mode", "") or "").casefold()
        if settings.app_environment == "production" or deployment_mode in {"production", "docker-production"}:
            raise RuntimeError("Refusing to apply the import to a production-configured database.")

        property_store = PropertyStore(settings.db_path)
        existing_ids = {record.property_id for record in property_store.list()}
        missing_ids = set(property_map.values()) - existing_ids
        if missing_ids and not args.create_property_scopes:
            raise RuntimeError(
                "Mapped property scopes do not exist: " + ", ".join(sorted(missing_ids))
                + ". Create the scopes explicitly with --create-property-scopes or map to existing properties."
            )
        created_properties = _create_property_scopes(property_store, package, property_map) if args.create_property_scopes else []
        result_items = OperationsStore(settings.db_path).import_reference_knowledge_batch(records)
        created = Counter()
        skipped = Counter()
        for record, was_created in result_items:
            item_type = record["source_name"].split(":", 3)[2]
            target = created if was_created else skipped
            target[f"{record['property_id']}:{item_type}"] += 1
        report.update({
            "mode": "applied",
            "database_modified": bool(created_properties or created),
            "created_properties": created_properties,
            "created_records_by_property_and_type": dict(sorted(created.items())),
            "skipped_identical_records_by_property_and_type": dict(sorted(skipped.items())),
            "total_created_records": sum(created.values()),
            "total_skipped_records": sum(skipped.values()),
        })
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
