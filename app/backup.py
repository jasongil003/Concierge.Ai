"""Verified SQLite and PostgreSQL backup, verification, and restore commands."""

from __future__ import annotations

import argparse
from contextlib import closing, contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
import zipfile
from urllib.parse import unquote

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from sqlalchemy.engine import make_url

from .build_info import BUILD_IDENTITY
from .config import settings
from .database import CURRENT_SCHEMA_REVISION


FORMAT_VERSION = 2
SQLITE_MEMBER = "database.sqlite"
POSTGRES_MEMBER = "database.dump"
# Backwards-compatible name used by the existing SQLite archive format.
DATABASE_MEMBER = SQLITE_MEMBER
MANIFEST_MEMBER = "manifest.json"
PG_TOOL_TIMEOUT_SECONDS = 1800
MAX_ARCHIVE_MEMBER_BYTES = 16 * 1024 * 1024 * 1024
MAX_ARCHIVE_TOTAL_BYTES = 32 * 1024 * 1024 * 1024
MAX_ENCRYPTED_ARCHIVE_BYTES = MAX_ARCHIVE_TOTAL_BYTES + 64 * 1024 * 1024
ENCRYPTED_BACKUP_MAGIC = b"CONCIERGE.AI.ENCRYPTED.BACKUP\x00V1\n"
BACKUP_NONCE_BYTES = 12
BACKUP_TAG_BYTES = 16
SCHEMA_REVISION_RE = re.compile(r"^\d{8}_\d{4}$")
BUILD_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _backup_key_bytes(value: str | bytes | bytearray | None) -> bytes:
    if isinstance(value, (bytes, bytearray)):
        key = bytes(value)
        if len(key) == 32:
            return key
    elif isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{64}", value.strip()):
        return bytes.fromhex(value.strip())
    raise RuntimeError(
        "CONCIERGE_BACKUP_ENCRYPTION_KEY must be a separately escrowed 32-byte key encoded as 64 hexadecimal characters."
    )


def _encrypt_backup_archive(source: Path, destination: Path, key: bytes) -> None:
    nonce = os.urandom(BACKUP_NONCE_BYTES)
    header = ENCRYPTED_BACKUP_MAGIC + nonce
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(header)
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as encrypted, source.open("rb") as plaintext:
        encrypted.write(header)
        for block in iter(lambda: plaintext.read(1024 * 1024), b""):
            encrypted.write(encryptor.update(block))
        encrypted.write(encryptor.finalize())
        encrypted.write(encryptor.tag)
        encrypted.flush()
        os.fsync(encrypted.fileno())


def _decrypt_backup_archive(source: Path, destination: Path, key: bytes) -> None:
    source_size = source.stat().st_size
    header_size = len(ENCRYPTED_BACKUP_MAGIC) + BACKUP_NONCE_BYTES
    if source_size > MAX_ENCRYPTED_ARCHIVE_BYTES or source_size < header_size + BACKUP_TAG_BYTES:
        raise RuntimeError("Encrypted backup size is invalid or exceeds the configured limit.")
    with source.open("rb") as encrypted:
        header = encrypted.read(header_size)
        if len(header) != header_size or not header.startswith(ENCRYPTED_BACKUP_MAGIC):
            raise RuntimeError("Encrypted backup header is invalid.")
        nonce = header[len(ENCRYPTED_BACKUP_MAGIC):]
        encrypted.seek(-BACKUP_TAG_BYTES, os.SEEK_END)
        tag = encrypted.read(BACKUP_TAG_BYTES)
        ciphertext_bytes = source_size - header_size - BACKUP_TAG_BYTES
        encrypted.seek(header_size)
        decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
        decryptor.authenticate_additional_data(header)
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as plaintext:
                remaining = ciphertext_bytes
                while remaining:
                    block = encrypted.read(min(1024 * 1024, remaining))
                    if not block:
                        raise RuntimeError("Encrypted backup is truncated.")
                    remaining -= len(block)
                    plaintext.write(decryp