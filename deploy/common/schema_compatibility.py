#!/usr/bin/env python3
"""Fail-closed schema and application rollback compatibility checks."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re


REVISION = re.compile(r"^\d{8}_\d{4}$")
MINIMUM_SCHEMA_REVISION = "20260926_0001"


@dataclass(frozen=True)
class ReleaseSchema:
    version: str
    revision: str
    minimum: str
    maximum: str
    metadata_complete: bool = True


def _valid_revision(value: str) -> bool:
    return bool(REVISION.fullmatch(value))


def read_release_schema(root: Path, *, candidate: bool = False) -> ReleaseSchema | None:
    """Read explicit release metadata, with a strict legacy-release fallback."""
    root = root.resolve()

    def read_text(name: str) -> str:
        try:
            return (root / name).read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    version = read_text("RELEASE_VERSION") or "unknown"
    revision = read_text("RELEASE_SCHEMA_REVISION")
    minimum = read_text("RELEASE_MINIMUM_SCHEMA_REVISION")
    maximum = read_text("RELEASE_MAXIMUM_SCHEMA_REVISION")
    if revision and minimum and maximum:
        if not all(_valid_revision(value) for value in (revision, minimum, maximum)):
            return None
        if not minimum <= revision <= maximum:
            return None
        return ReleaseSchema(version, revision, minimum, maximum)

    # Releases created before explicit metadata can only claim the schema
    # revision declared in their own source. Do not infer broader compatibility.
    if candidate:
        return None
    try:
        source = (root / "app" / "database.py").read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r'^CURRENT_SCHEMA_REVISION\s*=\s*["\']([^"\']+)["\']', source, re.MULTILINE)
    if not match or not _valid_revision(match.group(1)):
        return None
    revision = match.group(1)
    return ReleaseSchema(version, revision, revision, revision, metadata_complete=False)


def assess_update(
    *,
    current_schema: str,
    database_type: str,
    candidate: ReleaseSchema | None,
    previous: ReleaseSchema | None,
    allow_incompatible_rollback: bool = False,
) -> dict[str, object]:
    base: dict[str, object] = {
        "can_update": False,
        "candidate_can_migrate": False,
        "migration_required": False,
        "database_schema": current_schema,
        "candidate_schema": candidate.revision if candidate else "unknown",
        "candidate_version": candidate.version if candidate else "unknown",
        "previous_version": previous.version if previous else "unknown",
        "pre_migration_rollback_compatible": False,
        "rollback_compatible": False,
        "rollback_warning": "",
        "reason": "Schema compatibility metadata is unknown; refusing to change the active release.",
    }
    if database_type not in {"sqlite", "postgresql"} or candidate is None or previous is None:
        return base

    is_legacy_sqlite = database_type == "sqlite" and current_schema == "legacy/unmarked"
    if is_legacy_sqlite:
        migration_required = True
        post_migration_schema = candidate.revision
        pre_migration_rollback_compatible = True
    elif not _valid_revision(current_schema):
        base["reason"] = "Current database schema metadata is unknown; refusing to change the active release."
        return base
    else:
        if current_schema < candidate.minimum:
            base["reason"] = "Current database schema predates this release's supported migration range."
            return base
        if current_schema > candidate.maximum:
            base["reason"] = "Database schema is newer than this candidate release; refusing to downgrade application compatibility."
            return base
        migration_required = current_schema < candidate.revision
        post_migration_schema = candidate.revision if migration_required else current_schema
        pre_migration_rollback_compatible = previous.minimum <= current_schema <= previous.maximum

    base["candidate_can_migrate"] = True
    base["migration_required"] = migration_required
    base["pre_migration_rollback_compatible"] = pre_migration_rollback_compatible
    rollback_compatible = previous.minimum <= post_migration_schema <= previous.maximum
    base["rollback_compatible"] = rollback_compatible
    if migration_required and not rollback_compatible:
        base["rollback_warning"] = (
            f"Rollback warning: database migration to {post_migration_schema} will make "
            f"previous release v{previous.version} incompatible."
        )
    base["can_update"] = rollback_compatible or allow_incompatible_rollback
    if base["can_update"]:
        base["reason"] = "Schema compatibility checks passed."
    elif migration_required and not rollback_compatible:
        base["reason"] = (
            "The previous release cannot read the post-migration schema. "
            "Pass --allow-incompatible-rollback only after confirming the verified backup and recovery plan."
        )
    return base


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assess", choices=("assess",))
    parser.add_argument("--current-schema", required=True)
    parser.add_argument("--database-type", required=True, choices=("sqlite", "postgresql"))
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--allow-incompatible-rollback", action="store_true")
    args = parser.parse_args()
    assessment = assess_update(
        current_schema=args.current_schema,
        database_type=args.database_type,
        candidate=read_release_schema(args.candidate, candidate=True),
        previous=read_release_schema(args.previous),
        allow_incompatible_rollback=args.allow_incompatible_rollback,
    )
    print(json.dumps(assessment, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
