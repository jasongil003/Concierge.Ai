from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.ai_providers import SecretBox
from app.session_store import SessionStore
from app.transcript_crypto import TranscriptKeyRing
from app.transcript_rotation import inventory_transcripts, rotate_transcripts


LEGACY_SECRET = "synthetic-legacy-transcript-key-0123456789"
KEY_A = "synthetic-transcript-key-a-0123456789abcdef"
KEY_B = "synthetic-transcript-key-b-0123456789abcdef"


def _legacy_ring() -> TranscriptKeyRing:
    return TranscriptKeyRing(LEGACY_SECRET)


def _staged_ring(active: str = "key-b") -> TranscriptKeyRing:
    return TranscriptKeyRing(
        LEGACY_SECRET,
        {"key-a": KEY_A, "key-b": KEY_B},
        active,
    )


def _store(path: Path, ring: TranscriptKeyRing | None = None) -> SessionStore:
    return SessionStore(path, transcript_keys=ring or _legacy_ring())


def _add_legacy_turn(store: SessionStore, turn_id: str, message: str, response: str) -> None:
    legacy_box = SecretBox(LEGACY_SECRET)
    with store._connect() as db:
        db.execute(
            """INSERT INTO guest_ui_turns
            (property_id,session_id,turn_id,request_hash,encrypted_message,encrypted_response,status,created_at)
            VALUES(?,?,?,?,?,?,'complete',?)""",
            (
                "hotel-a",
                "guest-a",
                turn_id,
                f"hash-{turn_id}",
                legacy_box.encrypt(message),
                legacy_box.encrypt(response),
                int(turn_id[-1]),
            ),
        )


def test_transcript_keyring_reads_legacy_and_mixed_key_versions_and_fails_closed():
    legacy_box = SecretBox(LEGACY_SECRET)
    old_ring = TranscriptKeyRing(LEGACY_SECRET, {"key-a": KEY_A}, "key-a")
    mixed_ring = _staged_ring("key-b")

    old_message = old_ring.encrypt_message("old versioned message")
    new_message = mixed_ring.encrypt_message("new versioned message")
    old_turn = old_ring.encrypt_turn_ciphertext("old guest turn")
    legacy_message = "fernet:v1:" + legacy_box.encrypt("pre-ring message")
    legacy_turn = legacy_box.encrypt("pre-ring turn")

    assert old_message.startswith("fernet:v2:key-a:")
    assert new_message.startswith("fernet:v2:key-b:")
    assert mixed_ring.decrypt(old_message) == "old versioned message"
    assert mixed_ring.decrypt(new_message) == "new versioned message"
    assert mixed_ring.decrypt(legacy_message) == "pre-ring message"
    assert mixed_ring.decrypt_ciphertext(old_turn) == "old guest turn"
    assert mixed_ring.decrypt_ciphertext(legacy_turn) == "pre-ring turn"
    assert mixed_ring.decrypt("historical plaintext") == "historical plaintext"

    with pytest.raises(ValueError, match="unavailable key"):
        TranscriptKeyRing(LEGACY_SECRET, {"key-b": KEY_B}, "key-b").decrypt(old_message)
    with pytest.raises(Exception):
        TranscriptKeyRing("wrong-legacy-secret-0123456789abcdef").decrypt(legacy_message)
    with pytest.raises(ValueError, match="unsupported format"):
        mixed_ring.decrypt("fernet:v99:unknown:token")


def test_environment_keyring_and_recovery_from_restricted_escrow_fixture(tmp_path: Path, monkeypatch):
    escrow = tmp_path / "synthetic-transcript-keys.json"
    escrow.write_text(json.dumps({"key-a": KEY_A, "key-b": KEY_B}), encoding="utf-8")
    escrow.chmod(0o600)
    monkeypatch.setenv("CONVERSATION_ENCRYPTION_KEYS", escrow.read_text(encoding="utf-8"))
    monkeypatch.setenv("CONVERSATION_ENCRYPTION_ACTIVE_KEY_ID", "key-b")

    recovered = TranscriptKeyRing.from_environment(LEGACY_SECRET)
    value = recovered.encrypt_message("synthetic escrow recovery record")
    assert recovered.decrypt(value) == "synthetic escrow recovery record"
    assert recovered.active_key_id == "key-b"
    assert escrow.stat().st_mode & 0o777 == 0o600

    monkeypatch.setenv("CONVERSATION_ENCRYPTION_ACTIVE_KEY_ID", "missing")
    with pytest.raises(ValueError, match="not present"):
        TranscriptKeyRing.from_environment(LEGACY_SECRET)


def test_rotation_is_bounded_resumable_verified_and_rolls_back_to_legacy_formats(tmp_path: Path):
    store = _store(tmp_path / "rotation.db")
    store.record_message("guest-a", "hotel-a", "guest", "legacy message one")
    store.record_message("guest-b", "hotel-b", "guest", "legacy message two")
    with store._connect() as db:
        db.execute(
            """INSERT INTO conversation_messages
            (message_id,property_id,session_id,role,content,created_at)
            VALUES('historic-plain','hotel-a','guest-a','guest','historical plaintext',1)"""
        )
    _add_legacy_turn(store, "turn-1", "synthetic guest question", '{"text":"synthetic answer"}')

    ring = _staged_ring("key-b")
    before = inventory_transcripts(ring, connection_factory=store._connect)
    assert before["unreadable"] == 0
    assert before["records"] == 5
    assert before["fingerprint"] == inventory_transcripts(ring, connection_factory=store._connect)["fingerprint"]

    class SimulatedInterruption(RuntimeError):
        pass

    def interrupt_after_commit(progress):
        if progress["batch"] == 1:
            raise SimulatedInterruption("synthetic process interruption")

    with pytest.raises(SimulatedInterruption):
        rotate_transcripts(
            ring,
            "key-b",
            batch_size=2,
            connection_factory=store._connect,
            progress=interrupt_after_commit,
        )
    partially_rotated = inventory_transcripts(ring, connection_factory=store._connect)
    assert partially_rotated["unreadable"] == 0
    assert sum(count for label, count in partially_rotated["counts"].items() if label.endswith(":key-b")) == 2

    resumed = rotate_transcripts(ring, "key-b", batch_size=2, connection_factory=store._connect)
    assert resumed["updated"] == 3
    assert resumed["batches"] == 2
    assert rotate_transcripts(ring, "key-b", batch_size=2, connection_factory=store._connect)["updated"] == 0
    assert inventory_transcripts(ring, connection_factory=store._connect)["unreadable"] == 0

    rotated_reader = _store(store.path, ring)
    assert rotated_reader.recent_messages("guest-a", "hotel-a")[-1]["content"] == "legacy message one"
    assert rotated_reader.recent_messages("guest-a", "hotel-b") == []
    turns = rotated_reader.recent_guest_ui_turns("guest-a", "hotel-a")
    assert turns[0]["message"] == "synthetic guest question"
    assert turns[0]["response"] == {"text": "synthetic answer"}

    rollback = rotate_transcripts(ring, "legacy", batch_size=1, connection_factory=store._connect)
    assert rollback["updated"] == 5
    assert inventory_transcripts(ring, connection_factory=store._connect)["unreadable"] == 0
    with store._connect() as db:
        message = db.execute(
            "SELECT content FROM conversation_messages WHERE message_id=?", ("historic-plain",)
        ).fetchone()["content"]
        turn = db.execute(
            "SELECT encrypted_message FROM guest_ui_turns WHERE turn_id=?", ("turn-1",)
        ).fetchone()["encrypted_message"]
        assert message.startswith("fernet:v1:")
        assert not turn.startswith("fernet:")
        assert db.execute("SELECT COUNT(*) FROM conversation_messages").fetchone()[0] == 3

    old_release_reader = _store(store.path)
    assert old_release_reader.recent_messages("guest-a", "hotel-a")[-1]["content"] == "legacy message one"
    assert old_release_reader.recent_guest_ui_turns("guest-a", "hotel-a")[0]["message"] == "synthetic guest question"
    assert rotate_transcripts(ring, "legacy", batch_size=1, connection_factory=store._connect)["updated"] == 0


def test_missing_or_wrong_keys_and_database_write_failure_preserve_rows(tmp_path: Path):
    store = _store(tmp_path / "failure.db")
    store.record_message("guest-a", "hotel-a", "guest", "must remain recoverable")
    wrong_ring = TranscriptKeyRing("different-legacy-secret-0123456789abcdef", {"key-b": KEY_B}, "key-b")
    with pytest.raises(RuntimeError, match="cannot be decrypted"):
        rotate_transcripts(wrong_ring, "key-b", connection_factory=store._connect)

    class FailingConnection:
        def __init__(self, connection):
            self.connection = connection

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return self.connection.__exit__(exc_type, exc, tb)

        def execute(self, sql, parameters=()):
            if sql.startswith("UPDATE conversation_messages"):
                raise sqlite3.OperationalError("synthetic disk write failure")
            return self.connection.execute(sql, parameters)

        def commit(self):
            return self.connection.commit()

        def rollback(self):
            return self.connection.rollback()

    def failed_factory():
        connection = sqlite3.connect(store.path)
        connection.row_factory = sqlite3.Row
        return FailingConnection(connection)

    with pytest.raises(sqlite3.OperationalError, match="synthetic disk write failure"):
        rotate_transcripts(_staged_ring(), "key-b", batch_size=1, connection_factory=failed_factory)
    with store._connect() as db:
        value = db.execute(
            "SELECT content FROM conversation_messages WHERE session_id=?", ("guest-a",)
        ).fetchone()["content"]
    assert value.startswith("fernet:v1:")
    assert _legacy_ring().decrypt(value) == "must remain recoverable"


def test_rotation_refuses_corrupted_ciphertext_without_modifying_any_rows(tmp_path: Path):
    store = _store(tmp_path / "corrupt-rotation.db")
    store.record_message("guest-a", "hotel-a", "guest", "valid synthetic transcript")
    with store._connect() as db:
        db.execute(
            "UPDATE conversation_messages SET content=? WHERE session_id=?",
            ("fernet:v1:not-a-valid-fernet-token", "guest-a"),
        )

    ring = _staged_ring()
    before = inventory_transcripts(ring, connection_factory=store._connect)
    assert before["unreadable"] == 1

    with pytest.raises(RuntimeError, match="records cannot be decrypted"):
        rotate_transcripts(ring, "key-b", connection_factory=store._connect)

    after = inventory_transcripts(ring, connection_factory=store._connect)
    assert after["fingerprint"] == before["fingerprint"]
    with store._connect() as db:
        value = db.execute(
            "SELECT content FROM conversation_messages WHERE session_id=?", ("guest-a",)
        ).fetchone()["content"]
    assert value == "fernet:v1:not-a-valid-fernet-token"


def test_large_synthetic_transcript_set_migrates_in_small_idempotent_batches(tmp_path: Path):
    store = _store(tmp_path / "large-rotation.db")
    legacy_box = SecretBox(LEGACY_SECRET)
    with store._connect() as db:
        db.executemany(
            """INSERT INTO conversation_messages
            (message_id,property_id,session_id,role,content,created_at)
            VALUES(?,?,?,'guest',?,?)""",
            [
                (f"message-{index:04d}", f"hotel-{index % 4}", f"guest-{index:04d}",
                 "fernet:v1:" + legacy_box.encrypt(f"synthetic transcript content {index}"), index)
                for index in range(240)
            ],
        )

    progress = []
    result = rotate_transcripts(
        _staged_ring(),
        "key-b",
        batch_size=37,
        connection_factory=store._connect,
        progress=progress.append,
    )
    assert result == {"updated": 240, "batches": 7, "target_key_id": "key-b"}
    assert len(progress) == 7
    assert max(item["updated"] for item in progress) <= 37
    assert inventory_transcripts(_staged_ring(), connection_factory=store._connect)["unreadable"] == 0


def test_concurrent_guest_writes_use_target_key_while_old_rows_rotate(tmp_path: Path):
    from concurrent.futures import ThreadPoolExecutor

    old_writer = _store(tmp_path / "concurrent-rotation.db")
    new_writer = _store(old_writer.path, _staged_ring())
    for index in range(20):
        old_writer.record_message(
            f"guest-{index % 4}", f"hotel-{index % 2}", "guest", f"old synthetic turn {index}"
        )

    def write_active_key_message(index: int) -> None:
        new_writer.record_message(
            f"guest-new-{index % 4}",
            f"hotel-{index % 2}",
            "guest",
            f"new synthetic turn {index}",
        )

    with ThreadPoolExecutor(max_workers=5) as pool:
        writes = [pool.submit(write_active_key_message, index) for index in range(20)]
        rotation = pool.submit(
            rotate_transcripts,
            _staged_ring(),
            "key-b",
            batch_size=5,
            connection_factory=old_writer._connect,
        )
        for write in writes:
            write.result(timeout=10)
        result = rotation.result(timeout=10)

    assert result["updated"] == 20
    assert inventory_transcripts(_staged_ring(), connection_factory=old_writer._connect)["unreadable"] == 0
    with old_writer._connect() as db:
        rows = db.execute("SELECT property_id,session_id,content FROM conversation_messages").fetchall()
    assert len(rows) == 40
    assert all(row["content"].startswith("fernet:v2:key-b:") for row in rows)
    assert {row["property_id"] for row in rows} == {"hotel-0", "hotel-1"}
