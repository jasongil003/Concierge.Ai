"""Print the persisted schema revision without exposing database errors."""

from __future__ import annotations


def main() -> int:
    try:
        from app.config import settings
        from app.database import persisted_schema_revision

        revision = persisted_schema_revision(settings.db_path)
    except Exception:
        print("unavailable")
        return 1
    value = str(revision or "unavailable")
    print(value)
    return 0 if value not in {"", "unavailable"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
