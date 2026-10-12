"""Auditable, resumable transcript key rotation for operator-controlled use.

The default CLI action is a read-only inventory. Re-encryption requires an
explicit ``--apply`` flag and commits bounded, verified batches.
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
from collections import Counter
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from .config import settings
from .database import connect_database, database_url_configured
from .transcript_crypto import TranscriptKeyRing


logger = logging.getLogger("concierge.transcript_rotation")
ConnectionFactory = Callable[[], Any]


_SPECS = (
    ("conversation_messages", "content", ("property_id", "session_id", "message_id"), False),
    ("guest_ui_turns", "encrypted_message", ("property_id", "session_id", "turn_id"), True),
    ("guest_ui_turns", "encrypted_response", ("property_id", "session_id", "turn_id"), True),
)


def _default_connection_factory() -> Any:
    return connect_database(settings.db_path)


def _select_statement(
    db: Any,
    table: str,
    column: str,
    identity_columns: tuple[str, ...],
    limit: int | None = None,
    target_key_id: str | None = None,
    untagged_is_ciphertext: bool = False,
) -> tuple[str, tuple[Any, ...]]:
    identity_select = ",".join(identity_columns)
    sql = f"SELECT {identity_select},{column} AS encrypted_value FROM {table} WHERE {column}<>''"  # nosec B608: identifiers come only from _SPECS.
    parameters: tuple[Any, ...] = ()
    if target_key_id is not None:
        if target_key_id == "legacy" and untagged_is_ciphertext:
            # Historical turn ciphertext is already untagged Fernet. Only
            # version-marked rows need conversion for an old-release rollback.
            sql += " AND substr(" + column + ",1,8)='fernet:v'"
        else:
            target_prefix = "fernet:v1:" if target_key_id == "legacy" else f"fernet:v2:{target_key_id}:"
            sql += " AND substr(" + column + ",1,?)<>?"
            parameters = (len(target_prefix), target_prefix)
    order = ",".join(identity_columns)
    sql += f" ORDER BY {order}"  # nosec B608: identifiers come only from _SPECS.
    if limit is not None:
        sql += " LIMIT ?"
        parameters += (limit,)
    return sql, parameters


def _select_rows(
    db: Any,
    table: str,
    column: str,
    identity_columns: tuple[str, ...],
    limit: int | None = None,
    target_key_id: str | None = None,
    untagged_is_ciphertext: bool = False,
) -> list[Any]:
    sql, parameters = _select_statement(
        db,
        table,
        column,
        identity_columns,
        limit=limit,
        target_key_id=target_key_id,
        untagged_is_ciphertext=untagged_is_ciphertext,
    )
    return db.execute(sql, parameters).fetchall()


def _identity(row: Any, identity_columns: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(str(row[name]) for name in identity_columns)


def _decrypt_value(
    ring: TranscriptKeyRing,
    value: str,
    untagged_is_ciphertext: bool,
) -> str:
    return ring.decrypt_ciphertext(value) if untagged_is_ciphertext else ring.decrypt(value)


def inventory_transcripts(
    key_ring: TranscriptKeyRing,
    *,
    connection_factory: ConnectionFactory | None = None,
) -> dict[str, Any]:
    """Return aggregate key-format counts and a stable, non-content fingerprint."""
    connect = connection_factory or _default_connection_factory
    counts: Counter[str] = Counter()
    unreadable = 0
    fingerprint = key_ring.new_inventory_fingerprint()
    with connect() as db:
        for table, column, identity_columns, untagged_is_ciphertext in _SPECS:
            sql, parameters = _select_statement(db, table, column, identity_columns)
            for row in db.execute(sql, parameters):
                value = str(row["encrypted_value"])
                format_id = key_ring.format_id(value, untagged_is_ciphertext=untagged_is_ciphertext)
                counts[f"{table}.{column}:{format_id}"] += 1
                try:
                    _decrypt_value(key_ring, value, untagged_is_ciphertext)
                except Exception:
                    unreadable += 1
                stable_identity = (*_identity(row, identity_columns), table, column, format_id, str(len(value)))
                fingerprint.update("\x1f".join(stable_identity).encode("utf-8"))
                fingerprint.update(value.encode("utf-8"))
                fingerprint.update(b"\n")
    return {
        "records": sum(counts.values()),
        "counts": dict(sorted(counts.items())),
        "unreadable": unreadable,
        "fingerprint": fingerprint.hexdigest(),
        "active_key_id": key_ring.active_key_id,
    }


def rotate_transcripts(
    key_ring: TranscriptKeyRing,
    target_key_id: str,
    *,
    batch_size: int = 100,
    connection_factory: ConnectionFactory | None = None,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Re-encrypt all non-target transcript cells in atomic verified batches.

    Successful batches remain committed if a later batch fails. Re-running the
    operation skips target-key rows, so an interruption is safe to resume.
    """
    if batch_size < 1 or batch_size > 5000:
        raise ValueError("Transcript rotation batch size must be between 1 and 5000.")
    # Fail before opening the database if the requested target key is missing
    # or any stored row cannot currently be recovered.
    key_ring.require_key(target_key_id)
    connect = connection_factory or _default_connection_factory
    before = inventory_transcripts(key_ring, connection_factory=connect)
    if before["unreadable"]:
        raise RuntimeError(f"Transcript rotation stopped: {before['unreadable']} records cannot be decrypted with the configured key ring.")
    changed_total = 0
    batches = 0

    while True:
        batch: list[tuple[str, str, tuple[str, ...], bool, Any]] = []
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                for table, column, identity_columns, untagged_is_ciphertext in _SPECS:
                    remaining = batch_size - len(batch)
                    if remaining <= 0:
                        break
                    rows = _select_rows(
                        db,
                        table,
                        column,
                        identity_columns,
                        limit=remaining,
                        target_key_id=target_key_id,
                        untagged_is_ciphertext=untagged_is_ciphertext,
                    )
                    batch.extend(
                        (table, column, identity_columns, untagged_is_ciphertext, row)
                        for row in rows
                    )
                if not batch:
                    db.commit()
                    break

                for table, column, identity_columns, untagged_is_ciphertext, row in batch:
                    current = str(row["encrypted_value"])
                    plaintext = _decrypt_value(key_ring, current, untagged_is_ciphertext)
                    encrypted = key_ring.encrypt_for_key(
                        plaintext,
                        target_key_id,
                        untagged_legacy=untagged_is_ciphertext,
                    )
                    verified = _decrypt_value(key_ring, encrypted, untagged_is_ciphertext)
                    if verified != plaintext:
                        raise RuntimeError("Transcript rotation verification failed.")
                    identity_where = " AND ".join(f"{name}=?" for name in identity_columns)
                    update = f"UPDATE {table} SET {column}=? WHERE {identity_where} AND {column}=?"  # nosec B608: identifiers come only from _SPECS.
                    cursor = db.execute(
                        update,
                        (encrypted, *_identity(row, identity_columns), current),
                    )
                    if cursor.rowcount != 1:
                        raise RuntimeError("Transcript changed during rotation; the current batch was rolled back.")
                db.commit()
            except BaseException:
                db.rollback()
                raise

        batches += 1
        changed_total += len(batch)
        report = {"batch": batches, "updated": len(batch), "total_updated": changed_total, "target_key_id": target_key_id}
        logger.info("Transcript key rotation batch committed: %s", json.dumps(report, sort_keys=True))
        if progress:
            progress(report)

    return {"updated": changed_total, "batches": batches, "target_key_id": target_key_id}


def _connection_factory_for_cli(database: Path | None) -> ConnectionFactory:
    if database_url_configured():
        if database is not None:
            raise ValueError("Specify either DATABASE_URL or --database, not both.")
        return _default_connection_factory
    if database is None:
        raise ValueError("--database is required when DATABASE_URL is not configured.")
    resolved = database.expanduser().resolve()
    if not resolved.is_file():
        raise ValueError("The selected SQLite database must already exist; rotation never creates a database.")

    def connect() -> sqlite3.Connection:
        connection = sqlite3.connect(resolved, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    return connect


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventory or explicitly rotate encrypted guest transcripts.")
    parser.add_argument("--database", type=Path, help="Existing SQLite database; omit only when DATABASE_URL selects PostgreSQL.")
    parser.add_argument("--target-key-id", help="Key ID to write; defaults to the configured active key.")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--apply", action="store_true", help="Perform bounded re-encryption. Default is read-only inventory.")
    parser.add_argument("--allow-production", action="store_true", help="Explicitly authorize an operator-run production rotation.")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        ring = TranscriptKeyRing.from_environment(settings.credential_encryption_secret)
        connect = _connection_factory_for_cli(args.database)
        target = args.target_key_id or ring.active_key_id
        if args.apply and settings.app_environment in {"production", "prod"} and not args.allow_production:
            raise ValueError("Production rotation requires the separate --allow-production operator confirmation.")
        if args.allow_production and settings.app_environment not in {"production", "prod"}:
            raise ValueError("--allow-production is valid only when APP_ENVIRONMENT is production.")
        if args.apply:
            result = rotate_transcripts(ring, target, batch_size=args.batch_size, connection_factory=connect)
            inventory = inventory_transcripts(ring, connection_factory=connect)
            result["inventory"] = inventory
            if inventory["unreadable"]:
                print(json.dumps(result, sort_keys=True))
                return 2
        else:
            result = inventory_transcripts(ring, connection_factory=connect)
            result["target_key_id"] = target
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, RuntimeError, sqlite3.Error) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    raise SystemExit(main())
