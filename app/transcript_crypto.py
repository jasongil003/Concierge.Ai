"""Versioned encryption for stored guest transcripts.

The legacy credential secret remains the reader for existing ``fernet:v1``
messages and untagged guest-turn ciphertext. New transcript writes use a
versioned key identifier so keys can be staged and rotated explicitly.
"""

from __future__ import annotations

import hmac
import json
import os
import re
from collections.abc import Mapping
from hashlib import sha256

from .ai_providers import SecretBox


_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,47}$")
_V1_PREFIX = "fernet:v1:"
_V2_PREFIX = "fernet:v2:"


class TranscriptKeyRing:
    """Read old and staged keys while writing with one explicit active key."""

    def __init__(
        self,
        legacy_secret: str,
        keys: Mapping[str, str] | None = None,
        active_key_id: str | None = None,
    ) -> None:
        self._boxes: dict[str, SecretBox] = {"legacy": SecretBox(legacy_secret)}
        self.versioned_writes = bool(keys)
        for key_id, secret in (keys or {}).items():
            if key_id == "legacy" or not _KEY_ID.fullmatch(str(key_id)):
                raise ValueError("Transcript encryption key identifiers are invalid.")
            self._boxes[str(key_id)] = SecretBox(str(secret))

        selected = active_key_id or (next(iter(keys)) if keys else "legacy")
        if selected not in self._boxes:
            raise ValueError("The active transcript encryption key is not present in the key ring.")
        self.active_key_id = selected

    @classmethod
    def from_environment(cls, legacy_secret: str) -> "TranscriptKeyRing":
        raw_keys = os.getenv("CONVERSATION_ENCRYPTION_KEYS", "").strip()
        active_key_id = os.getenv("CONVERSATION_ENCRYPTION_ACTIVE_KEY_ID", "").strip() or None
        if not raw_keys:
            if active_key_id:
                raise ValueError("A transcript active key ID requires CONVERSATION_ENCRYPTION_KEYS.")
            return cls(legacy_secret)
        try:
            keys = json.loads(raw_keys)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("CONVERSATION_ENCRYPTION_KEYS must be a JSON object of key IDs to secrets.") from exc
        if not isinstance(keys, dict) or not keys or any(not isinstance(value, str) for value in keys.values()):
            raise ValueError("CONVERSATION_ENCRYPTION_KEYS must be a nonempty JSON object of string values.")
        if not active_key_id:
            raise ValueError("CONVERSATION_ENCRYPTION_ACTIVE_KEY_ID is required when a transcript key ring is configured.")
        return cls(legacy_secret, keys, active_key_id)

    def encrypt(self, value: str, *, key_id: str | None = None) -> str:
        if not value:
            return ""
        selected = key_id or self.active_key_id
        try:
            box = self._boxes[selected]
        except KeyError as exc:
            raise ValueError("The requested transcript encryption key is not available.") from exc
        return f"{_V2_PREFIX}{selected}:{box.encrypt(value)}"

    def encrypt_message(self, value: str) -> str:
        """Encrypt a conversation message, retaining v1 until a ring is staged."""
        if not value:
            return ""
        if not self.versioned_writes:
            return _V1_PREFIX + self._boxes["legacy"].encrypt(value)
        return self.encrypt(value)

    def encrypt_turn_ciphertext(self, value: str) -> str:
        """Encrypt a guest UI turn using its historical untagged legacy format."""
        if not value:
            return ""
        if not self.versioned_writes:
            return self._boxes["legacy"].encrypt(value)
        return self.encrypt(value)

    def encrypt_for_key(self, value: str, key_id: str, *, untagged_legacy: bool = False) -> str:
        """Encrypt for rotation or rollback, preserving pre-key-ring formats."""
        if not value:
            return ""
        if key_id == "legacy":
            encrypted = self._boxes["legacy"].encrypt(value)
            return encrypted if untagged_legacy else _V1_PREFIX + encrypted
        return self.encrypt(value, key_id=key_id)

    def require_key(self, key_id: str) -> None:
        if key_id not in self._boxes:
            raise ValueError("The requested transcript encryption key is not available.")

    def new_inventory_fingerprint(self):
        """Create a keyed digest so low-entropy legacy text is not hashable offline."""
        return hmac.new(self._boxes["legacy"].secret.encode("utf-8"), digestmod=sha256)

    def decrypt(self, value: str) -> str:
        """Decrypt versioned message fields and preserve historical plaintext."""
        if not value:
            return ""
        if value.startswith(_V2_PREFIX):
            return self._decrypt_v2(value)
        if value.startswith(_V1_PREFIX):
            return self._boxes["legacy"].decrypt(value.removeprefix(_V1_PREFIX))
        if value.startswith("fernet:"):
            raise ValueError("Transcript ciphertext uses an unsupported format.")
        # Rows written before transcript encryption are intentionally readable.
        return value

    def decrypt_ciphertext(self, value: str) -> str:
        """Decrypt guest-turn ciphertext, including its historical untagged form."""
        if not value:
            return ""
        if value.startswith(_V2_PREFIX):
            return self._decrypt_v2(value)
        if value.startswith(_V1_PREFIX):
            return self._boxes["legacy"].decrypt(value.removeprefix(_V1_PREFIX))
        return self._boxes["legacy"].decrypt(value)

    def format_id(self, value: str, *, untagged_is_ciphertext: bool = False) -> str:
        if not value:
            return "empty"
        if value.startswith(_V2_PREFIX):
            return value[len(_V2_PREFIX):].split(":", 1)[0]
        if value.startswith(_V1_PREFIX):
            return "v1"
        if value.startswith("fernet:"):
            return "unknown-version"
        return "legacy-untagged" if untagged_is_ciphertext else "plaintext"

    def _decrypt_v2(self, value: str) -> str:
        _, _, key_id, token = value.split(":", 3)
        try:
            box = self._boxes[key_id]
        except KeyError as exc:
            raise ValueError("Transcript ciphertext requires an unavailable key.") from exc
        return box.decrypt(token)
