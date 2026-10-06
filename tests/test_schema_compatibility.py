from pathlib import Path

import pytest

from deploy.common.schema_compatibility import ReleaseSchema, assess_update, read_release_schema


def _release(version: str, revision: str, minimum: str, maximum: str) -> ReleaseSchema:
    return ReleaseSchema(version, revision, minimum, maximum)


@pytest.mark.parametrize(
    ("database_schema", "candidate", "previous", "migration", "rollback", "can_update"),
    [
        (
            "20261005_0001", _release("1.0.0", "20261005_0001", "20260926_0001", "20261005_0001"),
            _release("0.9.2", "20261005_0001", "20260926_0001", "20261005_0001"),
            False, True, True,
        ),
        (
            "20260928_0003", _release("1.0.0", "20261006_0002", "20260926_0001", "20261006_0002"),
            _release("0.9.2", "20261005_0001", "20260926_0001", "20261006_0002"),
            True, True, True,
        ),
        (
            "20260928_0003", _release("1.0.0", "20261006_0002", "20260926_0001", "20261006_0002"),
            _release("0.9.2", "20261005_0001", "20260926_0001", "20261005_0001"),
            True, False, False,
        ),
    ],
)
def test_schema_compatibility_tracks_migration_and_rollback(
    database_schema, candidate, previous, migration, rollback, can_update
):
    result = assess_update(
        current_schema=database_schema,
        database_type="postgresql",
        candidate=candidate,
        previous=previous,
    )

    assert result["migration_required"] is migration
    assert result["rollback_compatible"] is rollback
    assert result["can_update"] is can_update
    if not rollback:
        assert result["rollback_warning"] == (
            "Rollback warning: database migration to 20261006_0002 will make previous release v0.9.2 incompatible."
        )


def test_schema_compatibility_blocks_database_newer_than_candidate():
    result = assess_update(
        current_schema="20261007_0001",
        database_type="postgresql",
        candidate=_release("1.0.0", "20261006_0002", "20260926_0001", "20261006_0002"),
        previous=_release("0.9.2", "20261005_0001", "20260926_0001", "20261006_0002"),
    )
    assert result["can_update"] is False
    assert "newer than this candidate" in result["reason"]


@pytest.mark.parametrize("database_type,current", [("sqlite", "unknown"), ("postgresql", "not-a-revision")])
def test_schema_compatibility_fails_closed_for_unknown_metadata(database_type, current):
    result = assess_update(
        current_schema=current,
        database_type=database_type,
        candidate=_release("1.0.0", "20261006_0002", "20260926_0001", "20261006_0002"),
        previous=_release("0.9.2", "20261005_0001", "20260926_0001", "20261006_0002"),
    )
    assert result["can_update"] is False
    assert result["rollback_warning"] == ""


def test_schema_compatibility_can_override_only_rollback_warning():
    result = assess_update(
        current_schema="20261005_0001",
        database_type="sqlite",
        candidate=_release("1.0.0", "20261006_0002", "20260926_0001", "20261006_0002"),
        previous=_release("0.9.2", "20261005_0001", "20260926_0001", "20261005_0001"),
        allow_incompatible_rollback=True,
    )
    assert result["candidate_can_migrate"] is True
    assert result["can_update"] is True
    assert result["pre_migration_rollback_compatible"] is True
    assert result["rollback_compatible"] is False


def test_sqlite_legacy_migration_keeps_pre_migration_rollback_safe():
    result = assess_update(
        current_schema="legacy/unmarked",
        database_type="sqlite",
        candidate=_release("1.0.0", "20261006_0002", "20260926_0001", "20261006_0002"),
        previous=_release("0.9.2", "20261005_0001", "20261005_0001", "20261005_0001"),
    )
    assert result["pre_migration_rollback_compatible"] is True
    assert result["rollback_compatible"] is False


@pytest.mark.parametrize("candidate", [False, True])
def test_release_schema_requires_explicit_candidate_metadata_but_reads_legacy_previous(candidate, tmp_path: Path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "database.py").write_text(
        'CURRENT_SCHEMA_REVISION = "20261005_0001"\n', encoding="utf-8"
    )
    release = read_release_schema(tmp_path, candidate=candidate)
    assert (release is None) is candidate
    if release is not None:
        assert release.metadata_complete is False
        assert release.minimum == release.maximum == "20261005_0001"


def test_release_schema_rejects_partial_or_invalid_explicit_metadata(tmp_path: Path):
    (tmp_path / "RELEASE_SCHEMA_REVISION").write_text("not-a-revision", encoding="utf-8")
    (tmp_path / "RELEASE_MINIMUM_SCHEMA_REVISION").write_text("20260926_0001", encoding="utf-8")
    (tmp_path / "RELEASE_MAXIMUM_SCHEMA_REVISION").write_text("20261005_0001", encoding="utf-8")
    assert read_release_schema(tmp_path, candidate=True) is None
