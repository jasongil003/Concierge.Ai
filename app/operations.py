import base64
import binascii
import json
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from .database import connect_database
from urllib.parse import urlparse

from .ai_providers import SecretBox, redact_secret
from .config import settings


TEXT_DOCUMENT_TYPES = {
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "text/html",
}


class OperationsStore:
    """Property-scoped operational configuration that does not belong in hotel content rows."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.secrets = SecretBox(settings.credential_encryption_secret)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = connect_database(self.path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _init_db(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS knowledge_items (
                    item_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    question TEXT NOT NULL DEFAULT '',
                    answer TEXT NOT NULL DEFAULT '',
                    body TEXT NOT NULL DEFAULT '',
                    source_name TEXT NOT NULL DEFAULT '',
                    content_type TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'ready',
                    error TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_knowledge_property_kind
                    ON knowledge_items(property_id, kind, updated_at DESC);

                CREATE TABLE IF NOT EXISTS webhooks (
                    webhook_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    endpoint_url TEXT NOT NULL,
                    events_json TEXT NOT NULL DEFAULT '[]',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    secret_encrypted TEXT NOT NULL DEFAULT '',
                    last_status TEXT NOT NULL DEFAULT 'never_tested',
                    last_error TEXT NOT NULL DEFAULT '',
                    last_delivery_at INTEGER,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_webhooks_property
                    ON webhooks(property_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS webhook_deliveries (
                    delivery_id TEXT PRIMARY KEY,
                    webhook_id TEXT NOT NULL,
                    property_id TEXT NOT NULL,
                    event_name TEXT NOT NULL,
                    response_status INTEGER,
                    status TEXT NOT NULL,
                    error TEXT NOT NULL DEFAULT '',
                    attempted_at INTEGER NOT NULL,
                    FOREIGN KEY(webhook_id) REFERENCES webhooks(webhook_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_property
                    ON webhook_deliveries(property_id, attempted_at DESC);

                CREATE TABLE IF NOT EXISTS platform_settings (
                    setting_key TEXT PRIMARY KEY,
                    config_json TEXT NOT NULL DEFAULT '{}',
                    secret_encrypted TEXT NOT NULL DEFAULT '',
                    updated_at INTEGER NOT NULL
                );
                """
            )

    @staticmethod
    def _knowledge_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "item_id": row["item_id"],
            "property_id": row["property_id"],
            "kind": row["kind"],
            "title": row["title"],
            "question": row["question"],
            "answer": row["answer"],
            "body": row["body"],
            "source_name": row["source_name"],
            "content_type": row["content_type"],
            "status": row["status"],
            "error": row["error"],
            "enabled": bool(row["enabled"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_knowledge(self, property_id: str, kind: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as db:
            if kind:
                rows = db.execute(
                    "SELECT * FROM knowledge_items WHERE property_id = ? AND kind = ? ORDER BY updated_at DESC",
                    (property_id, kind),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM knowledge_items WHERE property_id = ? ORDER BY kind, updated_at DESC",
                    (property_id,),
                ).fetchall()
        return [self._knowledge_row(row) for row in rows]

    def save_knowledge(self, property_id: str, payload: dict[str, Any], item_id: str | None = None) -> dict[str, Any]:
        kind = str(payload.get("kind", "entry")).strip().lower()
        if kind not in {"entry", "faq"}:
            raise ValueError("Knowledge kind must be entry or faq.")
        title = str(payload.get("title", "")).strip()[:200]
        question = str(payload.get("question", "")).strip()[:500]
        answer = str(payload.get("answer", "")).strip()[:12000]
        body = str(payload.get("body", "")).strip()[:50000]
        if kind == "faq":
            title = title or question
            if not question or not answer:
                raise ValueError("FAQ question and answer are required.")
        elif not title or not body:
            raise ValueError("Knowledge title and content are required.")
        now = int(time.time())
        item_id = item_id or f"knowledge_{uuid.uuid4().hex}"
        with self._connect() as db:
            current = db.execute(
                "SELECT item_id FROM knowledge_items WHERE item_id = ? AND property_id = ?",
                (item_id, property_id),
            ).fetchone()
            if current is None and payload.get("item_id"):
                raise KeyError("Knowledge item not found.")
            db.execute(
                """
                INSERT INTO knowledge_items (
                    item_id, property_id, kind, title, question, answer, body, source_name,
                    content_type, status, error, enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, '', '', 'ready', '', ?, ?, ?)
                ON CONFLICT(item_id) DO UPDATE SET
                    title = excluded.title, question = excluded.question, answer = excluded.answer,
                    body = excluded.body, status = 'ready', error = '', enabled = excluded.enabled,
                    updated_at = excluded.updated_at
                """,
                (item_id, property_id, kind, title, question, answer, body, 1 if payload.get("enabled", True) else 0, now, now),
            )
            row = db.execute("SELECT * FROM knowledge_items WHERE item_id = ?", (item_id,)).fetchone()
        return self._knowledge_row(row)

    def upload_document(self, property_id: str, filename: str, content_type: str, content_base64: str) -> dict[str, Any]:
        try:
            content = base64.b64decode(content_base64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Document content is not valid base64.") from exc
        if len(content) > 8 * 1024 * 1024:
            raise ValueError("Document exceeds the 8 MB limit.")
        item_id = f"document_{uuid.uuid4().hex}"
        now = int(time.time())
        status = "ready"
        error = ""
        body = ""
        if content_type in TEXT_DOCUMENT_TYPES:
            try:
                body = content.decode("utf-8")
                if content_type == "text/html":
                    body = re.sub(r"<[^>]+>", " ", body)
                body = re.sub(r"\s+", " ", body).strip()[:250000]
                if not body:
                    raise ValueError("Document does not contain readable text.")
            except UnicodeDecodeError:
                status = "error"
                error = "The document is not valid UTF-8 text."
        else:
            status = "error"
            error = "No trusted extractor is configured for this file type. Upload TXT, Markdown, CSV, JSON, or HTML."
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO knowledge_items (
                    item_id, property_id, kind, title, body, source_name, content_type,
                    status, error, enabled, created_at, updated_at
                ) VALUES (?, ?, 'document', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (item_id, property_id, filename[:200], body, filename[:220], content_type[:120], status, error, 1 if status == "ready" else 0, now, now),
            )
            row = db.execute("SELECT * FROM knowledge_items WHERE item_id = ?", (item_id,)).fetchone()
        return self._knowledge_row(row)

    def delete_knowledge(self, property_id: str, item_id: str) -> bool:
        with self._connect() as db:
            cursor = db.execute(
                "DELETE FROM knowledge_items WHERE property_id = ? AND item_id = ?",
                (property_id, item_id),
            )
        return cursor.rowcount > 0

    def search_knowledge(self, property_id: str, query: str, limit: int = 5, *, include_documents: bool = True) -> list[dict[str, str]]:
        stop = {"the", "a", "an", "is", "are", "what", "when", "where", "how", "can", "i", "to", "of", "for"}
        terms = {term for term in re.findall(r"[a-z0-9]+", query.casefold()) if len(term) > 1 and term not in stop}
        if not terms:
            return []
        scored: list[tuple[int, dict[str, str]]] = []
        for item in self.list_knowledge(property_id):
            if item["kind"] == "document" and not include_documents:
                continue
            if not item["enabled"] or item["status"] != "ready":
                continue
            haystack = " ".join([item["title"], item["question"], item["answer"], item["body"]]).casefold()
            haystack_terms = set(re.findall(r"[a-z0-9]+", haystack))
            score = len(terms & haystack_terms)
            if score:
                answer = item["answer"] or item["body"][:1800]
                scored.append((score, {"title": item["title"], "answer": answer}))
        scored.sort(key=lambda value: value[0], reverse=True)
        return [value for _, value in scored[:limit]]

    @staticmethod
    def _validate_webhook_url(endpoint_url: str) -> str:
        parsed = urlparse(endpoint_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Webhook URL must be an absolute HTTP or HTTPS URL.")
        if settings.app_environment in {"production", "staging"} and parsed.scheme != "https":
            raise ValueError("Production webhooks must use HTTPS.")
        return endpoint_url

    def save_webhook(self, property_id: str, payload: dict[str, Any], webhook_id: str | None = None) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()[:120]
        endpoint_url = self._validate_webhook_url(str(payload.get("endpoint_url", "")).strip()[:1000])
        events = sorted({str(event).strip()[:120] for event in payload.get("events", []) if str(event).strip()})
        if not name or not events:
            raise ValueError("Webhook name and at least one event are required.")
        now = int(time.time())
        webhook_id = webhook_id or f"webhook_{uuid.uuid4().hex}"
        with self._connect() as db:
            current = db.execute(
                "SELECT secret_encrypted, created_at FROM webhooks WHERE webhook_id = ? AND property_id = ?",
                (webhook_id, property_id),
            ).fetchone()
            if payload.get("webhook_id") and current is None:
                raise KeyError("Webhook not found.")
            secret = str(payload.get("secret", ""))
            encrypted = self.secrets.encrypt(secret) if secret else (current["secret_encrypted"] if current else "")
            created_at = current["created_at"] if current else now
            db.execute(
                """
                INSERT INTO webhooks (
                    webhook_id, property_id, name, endpoint_url, events_json, enabled,
                    secret_encrypted, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(webhook_id) DO UPDATE SET
                    name = excluded.name, endpoint_url = excluded.endpoint_url,
                    events_json = excluded.events_json, enabled = excluded.enabled,
                    secret_encrypted = excluded.secret_encrypted, updated_at = excluded.updated_at
                """,
                (webhook_id, property_id, name, endpoint_url, json.dumps(events), 1 if payload.get("enabled", True) else 0, encrypted, created_at, now),
            )
        return self.get_webhook(property_id, webhook_id, include_secret=False) or {}

    def get_webhook(self, property_id: str, webhook_id: str, include_secret: bool = False) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM webhooks WHERE property_id = ? AND webhook_id = ?",
                (property_id, webhook_id),
            ).fetchone()
        if row is None:
            return None
        result = {
            "webhook_id": row["webhook_id"],
            "property_id": row["property_id"],
            "name": row["name"],
            "endpoint_url": row["endpoint_url"],
            "events": json.loads(row["events_json"] or "[]"),
            "enabled": bool(row["enabled"]),
            "secret_configured": bool(row["secret_encrypted"]),
            "last_status": row["last_status"],
            "last_error": row["last_error"],
            "last_delivery_at": row["last_delivery_at"],
            "updated_at": row["updated_at"],
        }
        if include_secret:
            result["secret"] = self.secrets.decrypt(row["secret_encrypted"])
        return result

    def list_webhooks(self, property_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT webhook_id FROM webhooks WHERE property_id = ? ORDER BY updated_at DESC",
                (property_id,),
            ).fetchall()
        return [self.get_webhook(property_id, row["webhook_id"]) for row in rows]

    def delete_webhook(self, property_id: str, webhook_id: str) -> bool:
        with self._connect() as db:
            cursor = db.execute(
                "DELETE FROM webhooks WHERE property_id = ? AND webhook_id = ?",
                (property_id, webhook_id),
            )
        return cursor.rowcount > 0

    def record_webhook_delivery(
        self,
        property_id: str,
        webhook_id: str,
        event_name: str,
        status: str,
        response_status: int | None = None,
        error: str = "",
    ) -> dict[str, Any]:
        now = int(time.time())
        delivery_id = f"delivery_{uuid.uuid4().hex}"
        with self._connect() as db:
            db.execute(
                "INSERT INTO webhook_deliveries VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (delivery_id, webhook_id, property_id, event_name, response_status, status, error[:1000], now),
            )
            db.execute(
                "UPDATE webhooks SET last_status = ?, last_error = ?, last_delivery_at = ?, updated_at = ? WHERE property_id = ? AND webhook_id = ?",
                (status, error[:1000], now, now, property_id, webhook_id),
            )
        return {"delivery_id": delivery_id, "status": status, "response_status": response_status, "error": error[:1000], "attempted_at": now}

    def list_webhook_deliveries(self, property_id: str, webhook_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as db:
            if webhook_id:
                rows = db.execute(
                    "SELECT * FROM webhook_deliveries WHERE property_id = ? AND webhook_id = ? ORDER BY attempted_at DESC LIMIT 100",
                    (property_id, webhook_id),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM webhook_deliveries WHERE property_id = ? ORDER BY attempted_at DESC LIMIT 100",
                    (property_id,),
                ).fetchall()
        return [dict(row) for row in rows]

    def get_email_settings(self, include_secret: bool = False) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM platform_settings WHERE setting_key = 'smtp'").fetchone()
        config = json.loads(row["config_json"] or "{}") if row else {}
        encrypted = row["secret_encrypted"] if row else ""
        result = {
            "host": config.get("host", ""),
            "port": int(config.get("port", 587)),
            "username": config.get("username", ""),
            "from_address": config.get("from_address", ""),
            "security": config.get("security", "starttls"),
            "enabled": bool(config.get("enabled", False)),
            "password_configured": bool(encrypted),
            "password_masked": redact_secret(self.secrets.decrypt(encrypted)) if encrypted else "",
            "updated_at": row["updated_at"] if row else None,
        }
        if include_secret:
            result["password"] = self.secrets.decrypt(encrypted) if encrypted else ""
        return result

    def save_email_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.get_email_settings(include_secret=True)
        host = str(payload.get("host", "")).strip()[:255]
        port = int(payload.get("port", 587))
        username = str(payload.get("username", "")).strip()[:255]
        from_address = str(payload.get("from_address", "")).strip()[:254]
        security = str(payload.get("security", "starttls")).strip().lower()
        enabled = bool(payload.get("enabled", False))
        if not 1 <= port <= 65535:
            raise ValueError("SMTP port must be between 1 and 65535.")
        if security not in {"starttls", "ssl", "none"}:
            raise ValueError("SMTP security must be starttls, ssl, or none.")
        if enabled and (not host or not from_address):
            raise ValueError("SMTP host and from address are required when email is enabled.")
        password = str(payload.get("password", "")) or current.get("password", "")
        config = {"host": host, "port": port, "username": username, "from_address": from_address, "security": security, "enabled": enabled}
        now = int(time.time())
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO platform_settings(setting_key, config_json, secret_encrypted, updated_at)
                VALUES ('smtp', ?, ?, ?)
                ON CONFLICT(setting_key) DO UPDATE SET
                    config_json = excluded.config_json, secret_encrypted = excluded.secret_encrypted,
                    updated_at = excluded.updated_at
                """,
                (json.dumps(config), self.secrets.encrypt(password), now),
            )
        return self.get_email_settings()
