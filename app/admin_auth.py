import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .database import connect_database


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
SESSION_COOKIE = "concierge_admin_session"

PERMISSIONS: dict[str, str] = {
    "dashboard.view": "View dashboard",
    "properties.all": "Access every property",
    "properties.view": "View property configuration",
    "properties.edit": "Edit property configuration",
    "users.view": "View users",
    "users.create": "Create users",
    "users.edit": "Edit users",
    "users.delete": "Delete users",
    "roles.view": "View roles and permissions",
    "roles.manage": "Create and edit custom roles",
    "knowledge.view": "View knowledge",
    "knowledge.edit": "Manage knowledge",
    "knowledge.publish": "Approve and publish hotel knowledge",
    "knowledge.delete": "Delete hotel knowledge and source files",
    "concierge.view": "View concierge configuration",
    "concierge.edit": "Edit concierge configuration",
    "conversations.view": "View guest conversations",
    "conversations.takeover": "Accept an escalated guest conversation",
    "conversations.reply": "Reply to guest conversations",
    "conversations.assign": "Assign and reassign guest conversations",
    "conversations.resolve": "Resolve guest conversations",
    "conversations.return_to_ai": "Return guest conversations to AI",
    "guest_sessions.view": "View guest session and stay records",
    "guest_sessions.manage": "Manage guest sessions and stay records",
    "restaurant.view": "View assigned restaurants and guest-facing information",
    "restaurant.manage": "Manage assigned restaurant configuration",
    "restaurant.analytics.view": "View assigned restaurant analytics",
    "restaurant.menu.view": "View restaurant menus",
    "restaurant.menu.edit": "Edit restaurant menus and menu items",
    "restaurant.menu.approve": "Approve and publish restaurant menus",
    "restaurant.hours.view": "View restaurant hours",
    "restaurant.hours.edit": "Manage restaurant operating hours",
    "restaurant.promotions.view": "View restaurant promotions",
    "restaurant.promotions.edit": "Create and edit restaurant promotions",
    "restaurant.promotions.approve": "Approve and publish restaurant promotions",
    "requests.view": "View guest requests",
    "requests.manage": "Manage guest requests",
    "analytics.view": "View analytics",
    "assistant.use": "Use the operations assistant",
    "diagnostics.view": "Run property diagnostics",
    "infrastructure.view": "View host and database telemetry",
    "reports.export": "Export operational reports",
    "ai.view": "View AI configuration",
    "ai.configure": "Configure AI providers and behavior",
    "integrations.view": "View integrations",
    "integrations.configure": "Configure integrations",
    "domains.view": "View domain and deployment settings",
    "domains.configure": "Configure domains and deployment",
    "security.view": "View security settings",
    "security.configure": "Configure security and sessions",
    "audit.view": "View audit logs",
    "system.configure": "Configure platform settings",
}

DEFAULT_ROLES: dict[str, dict[str, Any]] = {
    "super-admin": {
        "name": "Super Admin",
        "description": "Platform owner with access to every property and system capability.",
        "permissions": list(PERMISSIONS),
    },
    "property-administrator": {
        "name": "Property Administrator",
        "description": "Full administration for one assigned hotel property.",
        "permissions": [key for key in PERMISSIONS if key not in {"properties.all", "system.configure"}],
    },
    "property-manager": {
        "name": "Property Manager",
        "description": "Hotel operations, content, requests, conversations, knowledge, and analytics.",
        "permissions": [
            "dashboard.view", "properties.view", "properties.edit", "knowledge.view", "knowledge.edit", "knowledge.publish",
            "concierge.view", "concierge.edit", "conversations.view", "conversations.takeover", "conversations.reply",
            "conversations.assign", "conversations.resolve", "conversations.return_to_ai",
            "guest_sessions.view", "guest_sessions.manage",
            "restaurant.view", "restaurant.manage", "restaurant.menu.view", "restaurant.menu.edit", "restaurant.menu.approve",
            "restaurant.hours.view", "restaurant.hours.edit", "restaurant.promotions.view", "restaurant.promotions.edit",
            "restaurant.promotions.approve",
            "requests.view", "requests.manage", "analytics.view", "assistant.use", "diagnostics.view",
            "reports.export", "ai.view", "integrations.view",
            "domains.view",
        ],
    },
    "department-manager": {
        "name": "Department Manager",
        "description": "Operational reporting and request management for one assigned hotel department.",
        "permissions": [
            "dashboard.view", "properties.view", "requests.view", "requests.manage", "analytics.view",
            "assistant.use", "diagnostics.view", "reports.export", "guest_sessions.view", "guest_sessions.manage",
        ],
    },
    "restaurant-manager": {
        "name": "Restaurant Manager",
        "description": "Manage assigned restaurant details, menus, hours, promotions, and guest conversations.",
        "permissions": [
            "properties.view", "restaurant.view", "restaurant.manage", "restaurant.analytics.view", "assistant.use", "diagnostics.view",
            "restaurant.menu.view", "restaurant.menu.edit", "restaurant.menu.approve",
            "restaurant.hours.view", "restaurant.hours.edit",
            "restaurant.promotions.view", "restaurant.promotions.edit", "restaurant.promotions.approve",
            "conversations.view", "conversations.takeover", "conversations.reply", "conversations.assign",
            "conversations.resolve", "conversations.return_to_ai",
        ],
    },
    "restaurant-staff": {
        "name": "Restaurant Staff",
        "description": "View assigned restaurant information and handle escalated guest conversations.",
        "permissions": [
            "properties.view", "restaurant.view", "restaurant.analytics.view", "assistant.use", "diagnostics.view", "restaurant.menu.view",
            "restaurant.hours.view", "restaurant.promotions.view", "conversations.view",
            "conversations.takeover", "conversations.reply", "conversations.resolve", "conversations.return_to_ai",
        ],
    },
    "concierge-front-desk": {
        "name": "Concierge / Front Desk",
        "description": "Guest conversations and request operations without system configuration.",
        "permissions": [
            "dashboard.view", "properties.view", "knowledge.view", "concierge.view",
            "conversations.view", "conversations.takeover", "conversations.reply", "conversations.resolve", "conversations.return_to_ai", "guest_sessions.view",
            "restaurant.view", "restaurant.menu.view",
            "restaurant.hours.view", "restaurant.promotions.view", "requests.view", "requests.manage", "assistant.use",
        ],
    },
    "content-manager": {
        "name": "Content Manager",
        "description": "Hotel content, knowledge, facilities, dining, and concierge responses.",
        "permissions": [
            "dashboard.view", "properties.view", "properties.edit", "knowledge.view", "knowledge.edit", "knowledge.publish",
            "concierge.view", "concierge.edit", "restaurant.view", "restaurant.manage",
            "restaurant.menu.view", "restaurant.menu.edit", "restaurant.menu.approve",
            "restaurant.hours.view", "restaurant.hours.edit",
            "restaurant.promotions.view", "restaurant.promotions.edit", "restaurant.promotions.approve",
            "analytics.view", "assistant.use", "reports.export",
        ],
    },
    "viewer-auditor": {
        "name": "Viewer / Auditor",
        "description": "Read-only reporting, analytics, and audit access.",
        "permissions": [
            "dashboard.view", "properties.view", "knowledge.view", "concierge.view",
            "conversations.view", "guest_sessions.view", "requests.view", "analytics.view", "ai.view", "integrations.view",
            "restaurant.view", "restaurant.menu.view", "restaurant.hours.view", "restaurant.promotions.view",
            "domains.view", "security.view", "audit.view", "roles.view", "users.view",
            "assistant.use", "diagnostics.view", "reports.export",
        ],
    },
}


class AuthenticationError(ValueError):
    pass


class AccountLockedError(AuthenticationError):
    pass


@dataclass(frozen=True)
class AdminPrincipal:
    user_id: str
    username: str
    display_name: str
    email: str | None
    role_id: str
    role_name: str
    role_slug: str
    property_id: str | None
    department_id: str | None
    status: str
    permissions: frozenset[str]
    session_id: str
    csrf_token: str
    force_password_change: bool
    expires_at: int

    def can(self, permission: str) -> bool:
        return permission in self.permissions

    def can_access_property(self, property_id: str) -> bool:
        return self.can("properties.all") or self.property_id == property_id

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.user_id,
            "username": self.username,
            "display_name": self.display_name,
            "email": self.email,
            "role": {"id": self.role_id, "name": self.role_name, "slug": self.role_slug},
            "property_id": self.property_id,
            "department_id": self.department_id,
            "status": self.status,
            "permissions": sorted(self.permissions),
            "csrf_token": self.csrf_token,
            "force_password_change": self.force_password_change,
            "session_expires_at": self.expires_at,
        }


def normalize_username(username: str) -> str:
    value = username.strip()
    if not 3 <= len(value) <= 64:
        raise ValueError("Username must be between 3 and 64 characters.")
    if not USERNAME_PATTERN.fullmatch(value):
        raise ValueError("Username may contain only letters, numbers, periods, underscores, and hyphens.")
    return value.casefold()


def validate_password(password: str) -> None:
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters.")
    if not re.search(r"[a-z]", password) or not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain upper- and lowercase letters.")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one number.")
    if not re.search(r"[^A-Za-z0-9]", password):
        raise ValueError("Password must contain at least one symbol.")


def hash_password(password: str) -> str:
    validate_password(password)
    salt = secrets.token_bytes(16)
    n, r, p = 2**14, 8, 1
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32)
    return f"scrypt${n}${r}${p}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=32,
        )
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


class AdminAuthStore:
    def __init__(
        self,
        path: Path,
        session_ttl_minutes: int = 480,
        lockout_attempts: int = 5,
        lockout_minutes: int = 15,
    ) -> None:
        self.path = path
        self.session_ttl_minutes = max(5, session_ttl_minutes)
        self.lockout_attempts = max(3, lockout_attempts)
        self.lockout_minutes = max(1, lockout_minutes)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = connect_database(self.path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _init_db(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS admin_roles (
                    role_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    slug TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    property_id TEXT,
                    is_system INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    UNIQUE(slug, property_id)
                );

                CREATE TABLE IF NOT EXISTS admin_schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS admin_role_permissions (
                    role_id TEXT NOT NULL,
                    permission TEXT NOT NULL,
                    PRIMARY KEY (role_id, permission),
                    FOREIGN KEY (role_id) REFERENCES admin_roles(role_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS admin_users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    normalized_username TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    email TEXT,
                    password_hash TEXT NOT NULL,
                    role_id TEXT NOT NULL,
                    property_id TEXT,
                    department_id TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    failed_login_count INTEGER NOT NULL DEFAULT 0,
                    locked_until INTEGER,
                    force_password_change INTEGER NOT NULL DEFAULT 0,
                    last_login_at INTEGER,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    FOREIGN KEY (role_id) REFERENCES admin_roles(role_id)
                );

                CREATE TABLE IF NOT EXISTS admin_sessions (
                    session_id TEXT PRIMARY KEY,
                    token_hash TEXT NOT NULL UNIQUE,
                    user_id TEXT NOT NULL,
                    csrf_token TEXT NOT NULL,
                    ip_address TEXT NOT NULL DEFAULT '',
                    user_agent TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    last_seen_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    revoked_at INTEGER,
                    FOREIGN KEY (user_id) REFERENCES admin_users(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS admin_user_identities (
                    identity_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    provider_subject TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    UNIQUE(provider, provider_subject),
                    FOREIGN KEY (user_id) REFERENCES admin_users(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS admin_password_resets (
                    reset_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    expires_at INTEGER NOT NULL,
                    used_at INTEGER,
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES admin_users(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS admin_login_attempts (
                    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip_address TEXT NOT NULL,
                    attempted_at INTEGER NOT NULL,
                    success INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS admin_audit_logs (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp INTEGER NOT NULL,
                    user_id TEXT,
                    username TEXT NOT NULL DEFAULT '',
                    display_name TEXT NOT NULL DEFAULT '',
                    role_name TEXT NOT NULL DEFAULT '',
                    property_id TEXT,
                    action TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    resource_id TEXT NOT NULL DEFAULT '',
                    ip_address TEXT NOT NULL DEFAULT '',
                    session_id TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_admin_sessions_user ON admin_sessions(user_id, expires_at);
                CREATE INDEX IF NOT EXISTS idx_admin_audit_timestamp ON admin_audit_logs(timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_admin_audit_property ON admin_audit_logs(property_id, timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_admin_login_attempt_ip ON admin_login_attempts(ip_address, attempted_at DESC);
                """
            )
            db.execute(
                "INSERT OR IGNORE INTO admin_schema_migrations (version, name, applied_at) VALUES (1, 'username_auth_rbac', ?)",
                (int(time.time()),),
            )
            columns = {row[1] for row in db.execute("PRAGMA table_info(admin_users)").fetchall()}
            if "department_id" not in columns:
                db.execute("ALTER TABLE admin_users ADD COLUMN department_id TEXT")
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS user_restaurants (
                    user_id TEXT NOT NULL,
                    property_id TEXT NOT NULL,
                    restaurant_id TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    created_by TEXT,
                    PRIMARY KEY (user_id, restaurant_id),
                    FOREIGN KEY (user_id) REFERENCES admin_users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (property_id, restaurant_id)
                        REFERENCES restaurants(property_id, restaurant_id) ON DELETE CASCADE
                )
                """
            )
            db.execute("CREATE INDEX IF NOT EXISTS idx_user_restaurants_property_restaurant ON user_restaurants(property_id, restaurant_id)")
            db.execute(
                """
                INSERT OR IGNORE INTO admin_user_identities (identity_id, user_id, provider, provider_subject, created_at)
                SELECT 'local-' || user_id, user_id, 'local', normalized_username, created_at FROM admin_users
                """
            )
        self._seed_default_roles()

    def _seed_default_roles(self) -> None:
        now = int(time.time())
        with self._connect() as db:
            for slug, definition in DEFAULT_ROLES.items():
                role_id = f"role-{slug}"
                db.execute(
                    """
                    INSERT INTO admin_roles (role_id, name, slug, description, property_id, is_system, created_at, updated_at)
                    VALUES (?, ?, ?, ?, NULL, 1, ?, ?)
                    ON CONFLICT(role_id) DO UPDATE SET
                        name = excluded.name, description = excluded.description, updated_at = excluded.updated_at
                    """,
                    (role_id, definition["name"], slug, definition["description"], now, now),
                )
                db.execute("DELETE FROM admin_role_permissions WHERE role_id = ?", (role_id,))
                db.executemany(
                    "INSERT INTO admin_role_permissions (role_id, permission) VALUES (?, ?)",
                    [(role_id, permission) for permission in definition["permissions"]],
                )

    def ensure_bootstrap_admin(self, username: str, password: str, display_name: str = "Platform Administrator") -> None:
        normalized = normalize_username(username)
        with self._connect() as db:
            exists = db.execute(
                "SELECT 1 FROM admin_users WHERE normalized_username = ?", (normalized,)
            ).fetchone()
        if exists:
            return
        self.create_user(
            {
                "username": username,
                "display_name": display_name,
                "email": None,
                "password": password,
                "role_id": "role-super-admin",
                "property_id": None,
                "status": "active",
                "force_password_change": False,
            },
            actor=None,
        )

    def login(self, username: str, password: str, ip_address: str, user_agent: str) -> tuple[str, AdminPrincipal]:
        normalized = normalize_username(username)
        now = int(time.time())
        if self._login_rate_limited(ip_address, now):
            self.audit(None, "auth.login_throttled", "session", normalized, ip_address=ip_address)
            raise AccountLockedError("Too many sign-in attempts. Try again later.")
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM admin_users WHERE normalized_username = ?", (normalized,)
            ).fetchone()
            if row is None:
                self._record_login_attempt(ip_address, False, now)
                self.audit(None, "auth.login_failed", "session", normalized, ip_address=ip_address, metadata={"reason": "unknown_username"})
                raise AuthenticationError("Invalid username or password.")
            if row["status"] == "disabled":
                self._record_login_attempt(ip_address, False, now)
                self.audit_row(row, "auth.login_failed", "session", row["user_id"], ip_address, metadata={"reason": "disabled"})
                raise AuthenticationError("Invalid username or password.")
            if row["status"] == "locked" and row["locked_until"] is None:
                self._record_login_attempt(ip_address, False, now)
                self.audit_row(row, "auth.login_blocked", "session", row["user_id"], ip_address, metadata={"reason": "manual_lock"})
                raise AccountLockedError("Account is locked. Contact an administrator.")
            if row["locked_until"] and row["locked_until"] > now:
                self._record_login_attempt(ip_address, False, now)
                self.audit_row(row, "auth.login_blocked", "session", row["user_id"], ip_address, metadata={"reason": "locked"})
                raise AccountLockedError("Account is temporarily locked. Try again later or contact an administrator.")
            if not verify_password(password, row["password_hash"]):
                failures = int(row["failed_login_count"]) + 1
                locked_until = now + self.lockout_minutes * 60 if failures >= self.lockout_attempts else None
                status = "locked" if locked_until else row["status"]
                db.execute(
                    "UPDATE admin_users SET failed_login_count = ?, locked_until = ?, status = ?, updated_at = ? WHERE user_id = ?",
                    (failures, locked_until, status, now, row["user_id"]),
                )
                db.commit()
                self._record_login_attempt(ip_address, False, now)
                self.audit_row(row, "auth.login_failed", "session", row["user_id"], ip_address, metadata={"attempt": failures})
                if locked_until:
                    raise AccountLockedError("Account is temporarily locked. Try again later or contact an administrator.")
                raise AuthenticationError("Invalid username or password.")

            db.execute(
                "UPDATE admin_users SET failed_login_count = 0, locked_until = NULL, status = 'active', last_login_at = ?, updated_at = ? WHERE user_id = ?",
                (now, now, row["user_id"]),
            )
        self._record_login_attempt(ip_address, True, now)

        token = secrets.token_urlsafe(48)
        token_hash = self._token_hash(token)
        session_id = str(uuid.uuid4())
        csrf_token = secrets.token_urlsafe(32)
        expires_at = now + self.session_ttl_minutes * 60
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO admin_sessions
                (session_id, token_hash, user_id, csrf_token, ip_address, user_agent, created_at, last_seen_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, token_hash, row["user_id"], csrf_token, ip_address[:120], user_agent[:500], now, now, expires_at),
            )
        principal = self.authenticate(token, touch=False)
        if principal is None:
            raise AuthenticationError("Unable to create an administrator session.")
        self.audit(principal, "auth.login_succeeded", "session", session_id, ip_address=ip_address)
        return token, principal

    def authenticate(self, token: str | None, touch: bool = True) -> AdminPrincipal | None:
        if not token:
            return None
        now = int(time.time())
        with self._connect() as db:
            row = db.execute(
                """
                SELECT s.*, u.username, u.display_name, u.email, u.role_id, u.property_id, u.department_id, u.status,
                       u.force_password_change, r.name AS role_name, r.slug AS role_slug
                FROM admin_sessions s
                JOIN admin_users u ON u.user_id = s.user_id
                JOIN admin_roles r ON r.role_id = u.role_id
                WHERE s.token_hash = ?
                """,
                (self._token_hash(token),),
            ).fetchone()
            if row is None or row["revoked_at"] is not None or row["expires_at"] <= now or row["status"] != "active":
                return None
            permissions = {
                item["permission"]
                for item in db.execute(
                    "SELECT permission FROM admin_role_permissions WHERE role_id = ?", (row["role_id"],)
                ).fetchall()
            }
            if touch and now - row["last_seen_at"] >= 60:
                db.execute("UPDATE admin_sessions SET last_seen_at = ? WHERE session_id = ?", (now, row["session_id"]))
        return AdminPrincipal(
            user_id=row["user_id"],
            username=row["username"],
            display_name=row["display_name"],
            email=row["email"],
            role_id=row["role_id"],
            role_name=row["role_name"],
            role_slug=row["role_slug"],
            property_id=row["property_id"],
            department_id=row["department_id"],
            status=row["status"],
            permissions=frozenset(permissions),
            session_id=row["session_id"],
            csrf_token=row["csrf_token"],
            force_password_change=bool(row["force_password_change"]),
            expires_at=row["expires_at"],
        )

    def logout(self, principal: AdminPrincipal) -> None:
        with self._connect() as db:
            db.execute("UPDATE admin_sessions SET revoked_at = ? WHERE session_id = ?", (int(time.time()), principal.session_id))
        self.audit(principal, "auth.logout", "session", principal.session_id)

    def list_users(self, principal: AdminPrincipal) -> list[dict[str, Any]]:
        if principal.can("properties.all"):
            query = """
                SELECT u.*, r.name AS role_name, r.slug AS role_slug,
                       (SELECT COUNT(*) FROM admin_sessions s WHERE s.user_id = u.user_id AND s.revoked_at IS NULL AND s.expires_at > ?) AS active_sessions
                FROM admin_users u JOIN admin_roles r ON r.role_id = u.role_id
                ORDER BY u.created_at DESC
            """
            params: tuple[Any, ...] = (int(time.time()),)
        else:
            query = """
                SELECT u.*, r.name AS role_name, r.slug AS role_slug,
                       (SELECT COUNT(*) FROM admin_sessions s WHERE s.user_id = u.user_id AND s.revoked_at IS NULL AND s.expires_at > ?) AS active_sessions
                FROM admin_users u JOIN admin_roles r ON r.role_id = u.role_id
                WHERE u.property_id = ?
                ORDER BY u.created_at DESC
            """
            params = (int(time.time()), principal.property_id)
        with self._connect() as db:
            rows = db.execute(query, params).fetchall()
        return [self._serialize_user(row) | {"restaurant_ids": self._restaurant_ids_for_user(row["user_id"])} for row in rows]

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT u.*, r.name AS role_name, r.slug AS role_slug FROM admin_users u JOIN admin_roles r ON r.role_id = u.role_id WHERE u.user_id = ?",
                (user_id,),
            ).fetchone()
        return (self._serialize_user(row) | {"restaurant_ids": self._restaurant_ids_for_user(user_id)}) if row else None

    def create_user(self, payload: dict[str, Any], actor: AdminPrincipal | None) -> dict[str, Any]:
        username = str(payload.get("username", "")).strip()
        normalized = normalize_username(username)
        display_name = str(payload.get("display_name", "")).strip()
        if not display_name or len(display_name) > 120:
            raise ValueError("Display name is required and must be 120 characters or fewer.")
        email = str(payload.get("email") or "").strip().lower() or None
        if email and (len(email) > 254 or "@" not in email):
            raise ValueError("Enter a valid optional email address.")
        role = self.get_role(str(payload.get("role_id", "")))
        if role is None:
            raise ValueError("Choose a valid role.")
        property_id = str(payload.get("property_id") or "").strip() or None
        department_id = str(payload.get("department_id") or "").strip() or None
        if actor and not actor.can("properties.all"):
            if property_id != actor.property_id:
                raise PermissionError("You can create users only for your assigned property.")
        if actor:
            self.assert_role_assignment_allowed(actor, role, property_id)
        if role["slug"] != "super-admin" and not property_id:
            raise ValueError("A property is required for this role.")
        if role["slug"] == "department-manager" and not department_id:
            raise ValueError("A department is required for the Department Manager role.")
        if role["slug"] == "department-manager" and not self._department_belongs(property_id, department_id):
            raise ValueError("The Department Manager assignment must reference a department in the user's property.")
        if role["slug"] != "department-manager":
            department_id = None
        status = str(payload.get("status", "active")).strip().lower()
        if status not in {"active", "disabled", "locked"}:
            raise ValueError("Status must be active, disabled, or locked.")
        password_hash = hash_password(str(payload.get("password", "")))
        user_id = str(uuid.uuid4())
        now = int(time.time())
        try:
            with self._connect() as db:
                db.execute(
                    """
                    INSERT INTO admin_users
                    (user_id, username, normalized_username, display_name, email, password_hash, role_id,
                     property_id, department_id, status, force_password_change, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id, username, normalized, display_name, email, password_hash, role["role_id"],
                        property_id, department_id, status, 1 if payload.get("force_password_change") else 0, now, now,
                    ),
                )
                db.execute(
                    "INSERT INTO admin_user_identities (identity_id, user_id, provider, provider_subject, created_at) VALUES (?, ?, 'local', ?, ?)",
                    (str(uuid.uuid4()), user_id, normalized, now),
                )
                restaurant_ids = self._set_restaurant_assignments(
                    db, user_id, property_id, payload.get("restaurant_ids", []),
                    actor, role,
                )
                self._record_restaurant_assignment_audit(db, user_id, property_id, set(), restaurant_ids, actor)
        except sqlite3.IntegrityError as exc:
            raise ValueError("That username is already in use.") from exc
        user = self.get_user(user_id)
        self.audit(actor, "users.created", "user", user_id, property_id=property_id, metadata={"username": username, "role": role["name"]})
        return user or {}

    def update_user(self, user_id: str, payload: dict[str, Any], actor: AdminPrincipal) -> dict[str, Any]:
        current = self.get_user(user_id)
        if current is None:
            raise KeyError("User not found.")
        self._assert_user_scope(current, actor)
        display_name = str(payload.get("display_name", current["display_name"])).strip()
        email_value = payload.get("email", current["email"])
        email = str(email_value or "").strip().lower() or None
        role_id = str(payload.get("role_id", current["role_id"]))
        role = self.get_role(role_id)
        if role is None:
            raise ValueError("Choose a valid role.")
        property_id = str(payload.get("property_id", current["property_id"]) or "").strip() or None
        department_id = str(payload.get("department_id", current.get("department_id")) or "").strip() or None
        if not actor.can("properties.all"):
            if property_id != actor.property_id:
                raise PermissionError("You cannot assign this property or role.")
        self.assert_role_assignment_allowed(actor, role, property_id)
        if role["slug"] == "department-manager" and not department_id:
            raise ValueError("A department is required for the Department Manager role.")
        if role["slug"] == "department-manager" and not self._department_belongs(property_id, department_id):
            raise ValueError("The Department Manager assignment must reference a department in the user's property.")
        if role["slug"] != "department-manager":
            department_id = None
        status = str(payload.get("status", current["status"])).lower()
        if status not in {"active", "disabled", "locked"}:
            raise ValueError("Unsupported account status.")
        now = int(time.time())
        with self._connect() as db:
            db.execute(
                """
                UPDATE admin_users SET display_name = ?, email = ?, role_id = ?, property_id = ?, department_id = ?, status = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (display_name, email, role_id, property_id, department_id, status, now, user_id),
            )
            if status == "active":
                db.execute("UPDATE admin_users SET locked_until = NULL, failed_login_count = 0 WHERE user_id = ?", (user_id,))
            elif status == "locked":
                db.execute("UPDATE admin_users SET locked_until = NULL WHERE user_id = ?", (user_id,))
            if status == "disabled":
                db.execute("UPDATE admin_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL", (now, user_id))
            if "restaurant_ids" in payload or property_id != current["property_id"] or not self._role_has_restaurant_access(role):
                assignments = payload.get("restaurant_ids", current.get("restaurant_ids", []) if property_id == current["property_id"] else [])
                restaurant_ids = self._set_restaurant_assignments(
                    db, user_id, property_id, assignments,
                    actor, role,
                )
                previous_ids = set(current.get("restaurant_ids", []))
                if property_id != current["property_id"]:
                    self._record_restaurant_assignment_audit(db, user_id, current["property_id"], previous_ids, set(), actor)
                    self._record_restaurant_assignment_audit(db, user_id, property_id, set(), restaurant_ids, actor)
                else:
                    self._record_restaurant_assignment_audit(db, user_id, property_id, previous_ids, restaurant_ids, actor)
        self.audit(actor, "users.updated", "user", user_id, property_id=property_id, metadata={"username": current["username"], "role": role["name"], "status": status})
        return self.get_user(user_id) or {}

    def delete_user(self, user_id: str, actor: AdminPrincipal) -> None:
        current = self.get_user(user_id)
        if current is None:
            raise KeyError("User not found.")
        self._assert_user_scope(current, actor)
        if user_id == actor.user_id:
            raise ValueError("You cannot delete your own account.")
        with self._connect() as db:
            db.execute("DELETE FROM admin_users WHERE user_id = ?", (user_id,))
        self.audit(actor, "users.deleted", "user", user_id, property_id=current["property_id"], metadata={"username": current["username"]})

    def reset_password(self, user_id: str, password: str, force_change: bool, actor: AdminPrincipal) -> None:
        current = self.get_user(user_id)
        if current is None:
            raise KeyError("User not found.")
        self._assert_user_scope(current, actor)
        encoded = hash_password(password)
        now = int(time.time())
        with self._connect() as db:
            db.execute(
                """
                UPDATE admin_users SET password_hash = ?, force_password_change = ?, failed_login_count = 0,
                    locked_until = NULL, status = 'active', updated_at = ? WHERE user_id = ?
                """,
                (encoded, 1 if force_change else 0, now, user_id),
            )
            db.execute("UPDATE admin_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL", (now, user_id))
        self.audit(actor, "users.password_reset", "user", user_id, property_id=current["property_id"], metadata={"username": current["username"], "force_change": force_change})

    def create_password_reset(self, username: str, ttl_minutes: int = 30) -> dict[str, Any] | None:
        try:
            normalized = normalize_username(username)
        except ValueError:
            return None
        with self._connect() as db:
            user = db.execute(
                "SELECT user_id, username, display_name, email, status FROM admin_users WHERE normalized_username = ?",
                (normalized,),
            ).fetchone()
            if user is None or user["status"] != "active" or not user["email"]:
                return None
            token = secrets.token_urlsafe(32)
            now = int(time.time())
            db.execute(
                "UPDATE admin_password_resets SET used_at = ? WHERE user_id = ? AND used_at IS NULL",
                (now, user["user_id"]),
            )
            db.execute(
                "INSERT INTO admin_password_resets(reset_id, user_id, token_hash, expires_at, used_at, created_at) VALUES (?, ?, ?, ?, NULL, ?)",
                (str(uuid.uuid4()), user["user_id"], self._token_hash(token), now + ttl_minutes * 60, now),
            )
        return {"token": token, "email": user["email"], "display_name": user["display_name"], "username": user["username"]}

    def consume_password_reset(self, token: str, new_password: str) -> None:
        encoded = hash_password(new_password)
        now = int(time.time())
        with self._connect() as db:
            row = db.execute(
                """
                SELECT reset_id, user_id FROM admin_password_resets
                WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?
                """,
                (self._token_hash(token), now),
            ).fetchone()
            if row is None:
                raise AuthenticationError("Reset link is invalid or has expired.")
            db.execute(
                "UPDATE admin_users SET password_hash = ?, force_password_change = 0, failed_login_count = 0, locked_until = NULL, status = 'active', updated_at = ? WHERE user_id = ?",
                (encoded, now, row["user_id"]),
            )
            db.execute("UPDATE admin_password_resets SET used_at = ? WHERE reset_id = ?", (now, row["reset_id"]))
            db.execute("UPDATE admin_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL", (now, row["user_id"]))
        self.audit(None, "auth.password_reset_completed", "user", row["user_id"])

    def change_password(self, principal: AdminPrincipal, current_password: str, new_password: str) -> None:
        with self._connect() as db:
            row = db.execute("SELECT password_hash FROM admin_users WHERE user_id = ?", (principal.user_id,)).fetchone()
            if row is None or not verify_password(current_password, row["password_hash"]):
                raise AuthenticationError("Current password is incorrect.")
            encoded = hash_password(new_password)
            now = int(time.time())
            db.execute(
                "UPDATE admin_users SET password_hash = ?, force_password_change = 0, updated_at = ? WHERE user_id = ?",
                (encoded, now, principal.user_id),
            )
            db.execute(
                "UPDATE admin_sessions SET revoked_at = ? WHERE user_id = ? AND session_id != ? AND revoked_at IS NULL",
                (now, principal.user_id, principal.session_id),
            )
        self.audit(principal, "auth.password_changed", "user", principal.user_id)

    def revoke_sessions(self, user_id: str, actor: AdminPrincipal, keep_session_id: str | None = None) -> int:
        current = self.get_user(user_id)
        if current is None:
            raise KeyError("User not found.")
        self._assert_user_scope(current, actor)
        now = int(time.time())
        with self._connect() as db:
            if keep_session_id:
                cursor = db.execute(
                    "UPDATE admin_sessions SET revoked_at = ? WHERE user_id = ? AND session_id != ? AND revoked_at IS NULL",
                    (now, user_id, keep_session_id),
                )
            else:
                cursor = db.execute(
                    "UPDATE admin_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL", (now, user_id)
                )
        self.audit(actor, "users.sessions_revoked", "user", user_id, property_id=current["property_id"], metadata={"count": cursor.rowcount})
        return cursor.rowcount

    def list_roles(self, principal: AdminPrincipal) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT r.*, COUNT(DISTINCT u.user_id) AS user_count
                FROM admin_roles r LEFT JOIN admin_users u ON u.role_id = r.role_id
                WHERE r.property_id IS NULL OR r.property_id = ? OR ? = 1
                GROUP BY r.role_id ORDER BY r.is_system DESC, r.name
                """,
                (principal.property_id, 1 if principal.can("properties.all") else 0),
            ).fetchall()
        return [self._serialize_role(row) for row in rows]

    def get_role(self, role_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM admin_roles WHERE role_id = ?", (role_id,)).fetchone()
        return self._serialize_role(row) if row else None

    def save_role(self, payload: dict[str, Any], principal: AdminPrincipal, role_id: str | None = None) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        if not 2 <= len(name) <= 80:
            raise ValueError("Role name must be between 2 and 80 characters.")
        slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
        permissions = sorted(set(payload.get("permissions") or []))
        unknown = [permission for permission in permissions if permission not in PERMISSIONS]
        if unknown:
            raise ValueError(f"Unknown permission: {unknown[0]}")
        self.assert_permissions_delegatable(principal, permissions)
        property_id = str(payload.get("property_id") or principal.property_id or "").strip() or None
        if not principal.can("properties.all") and property_id != principal.property_id:
            raise PermissionError("Custom roles must belong to your assigned property.")
        now = int(time.time())
        if role_id:
            current = self.get_role(role_id)
            if current is None:
                raise KeyError("Role not found.")
            if current["is_system"]:
                raise ValueError("System roles cannot be modified.")
            if not principal.can("properties.all") and current["property_id"] != principal.property_id:
                raise PermissionError("You cannot modify this role.")
        else:
            role_id = str(uuid.uuid4())
        try:
            with self._connect() as db:
                db.execute(
                    """
                    INSERT INTO admin_roles (role_id, name, slug, description, property_id, is_system, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 0, ?, ?)
                    ON CONFLICT(role_id) DO UPDATE SET
                        name = excluded.name, slug = excluded.slug, description = excluded.description,
                        property_id = excluded.property_id, updated_at = excluded.updated_at
                    """,
                    (role_id, name, slug, str(payload.get("description", ""))[:500], property_id, now, now),
                )
                db.execute("DELETE FROM admin_role_permissions WHERE role_id = ?", (role_id,))
                db.executemany(
                    "INSERT INTO admin_role_permissions (role_id, permission) VALUES (?, ?)",
                    [(role_id, permission) for permission in permissions],
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("A role with that name already exists in this property.") from exc
        self.audit(principal, "roles.saved", "role", role_id, property_id=property_id, metadata={"name": name, "permissions": permissions})
        return self.get_role(role_id) or {}

    @staticmethod
    def assert_permissions_delegatable(principal: AdminPrincipal, permissions: list[str] | set[str] | tuple[str, ...]) -> None:
        """Prevent an administrator from granting permissions they do not hold."""
        requested = set(permissions)
        if principal.can("properties.all"):
            return
        denied = sorted(requested - set(principal.permissions))
        if denied:
            raise PermissionError(f"You cannot delegate permissions you do not hold: {', '.join(denied)}.")

    @classmethod
    def assert_role_assignment_allowed(
        cls, principal: AdminPrincipal, role: dict[str, Any], property_id: str | None
    ) -> None:
        if not principal.can("properties.all"):
            if property_id != principal.property_id:
                raise PermissionError("You cannot assign a role outside your property.")
            cls.assert_permissions_delegatable(principal, role.get("permissions") or [])
        role_property_id = role.get("property_id")
        if role_property_id is not None and role_property_id != property_id:
            raise PermissionError("A property role can only be assigned within its own property.")

    @staticmethod
    def _role_has_restaurant_access(role: dict[str, Any]) -> bool:
        return bool({"restaurant.view", "restaurant.manage"} & set(role.get("permissions") or []))

    def _department_belongs(self, property_id: str | None, department_id: str | None) -> bool:
        if not property_id or not department_id:
            return False
        with self._connect() as db:
            table = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='departments'"
            ).fetchone()
            if table is None:
                return False
            row = db.execute(
                "SELECT 1 FROM departments WHERE property_id=? AND department_id=?",
                (property_id, department_id),
            ).fetchone()
        return row is not None

    def _set_restaurant_assignments(
        self,
        db: sqlite3.Connection,
        user_id: str,
        property_id: str | None,
        restaurant_ids: Any,
        actor: AdminPrincipal | None,
        role: dict[str, Any],
    ) -> set[str]:
        if restaurant_ids is None:
            restaurant_ids = []
        if not isinstance(restaurant_ids, list):
            raise ValueError("Restaurant assignments must be a list of restaurant IDs.")
        ids = list(dict.fromkeys(str(value).strip() for value in restaurant_ids if str(value).strip()))
        if len(ids) > 100:
            raise ValueError("A user can be assigned to at most 100 restaurants.")
        restaurant_table = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='restaurants'"
        ).fetchone()
        if not restaurant_table:
            if ids:
                raise ValueError("Restaurants must be initialized before assigning restaurant access.")
            return set()
        db.execute("DELETE FROM user_restaurants WHERE user_id = ?", (user_id,))
        if ids and not self._role_has_restaurant_access(role):
            raise PermissionError("Restaurant assignments require a restaurant access role.")
        if ids and not property_id:
            raise ValueError("Restaurant assignments require a property.")
        if not ids:
            return set()
        found = {
            row["restaurant_id"]
            for row in db.execute(
                f"SELECT restaurant_id FROM restaurants WHERE property_id=? AND restaurant_id IN ({','.join('?' for _ in ids)})",  # nosec B608
                (property_id, *ids),
            ).fetchall()
        }
        missing = sorted(set(ids) - found)
        if missing:
            raise PermissionError("Restaurant assignments must reference restaurants in the user's property.")
        if actor and not (actor.can("properties.all") or actor.can("properties.edit")):
            allowed = {
                row["restaurant_id"]
                for row in db.execute(
                    "SELECT restaurant_id FROM user_restaurants WHERE user_id=? AND property_id=?",
                    (actor.user_id, property_id),
                ).fetchall()
            }
            if not set(ids) <= allowed:
                raise PermissionError("You can assign users only to restaurants assigned to you.")
        now = int(time.time())
        db.executemany(
            "INSERT INTO user_restaurants(user_id,property_id,restaurant_id,created_at,created_by) VALUES(?,?,?,?,?)",
            [(user_id, property_id, restaurant_id, now, actor.user_id if actor else None) for restaurant_id in ids],
        )
        return set(ids)

    @staticmethod
    def _record_restaurant_assignment_audit(
        db: sqlite3.Connection,
        user_id: str,
        property_id: str | None,
        before: set[str],
        after: set[str],
        actor: AdminPrincipal | None,
    ) -> None:
        if not property_id or not (before ^ after):
            return
        exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='restaurant_audit_events'"
        ).fetchone()
        if not exists:
            return
        now = int(time.time())
        for restaurant_id in sorted(after - before):
            db.execute(
                """INSERT INTO restaurant_audit_events
                (event_id,property_id,restaurant_id,actor_user_id,resource_type,resource_id,action,metadata,created_at)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (uuid.uuid4().hex, property_id, restaurant_id, actor.user_id if actor else None, "user", user_id, "restaurant_user_assigned", "{}", now),
            )
        for restaurant_id in sorted(before - after):
            db.execute(
                """INSERT INTO restaurant_audit_events
                (event_id,property_id,restaurant_id,actor_user_id,resource_type,resource_id,action,metadata,created_at)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (uuid.uuid4().hex, property_id, restaurant_id, actor.user_id if actor else None, "user", user_id, "restaurant_user_removed", "{}", now),
            )

    def _restaurant_ids_for_user(self, user_id: str) -> list[str]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT restaurant_id FROM user_restaurants WHERE user_id=? ORDER BY restaurant_id",
                (user_id,),
            ).fetchall()
        return [row["restaurant_id"] for row in rows]

    def delete_role(self, role_id: str, principal: AdminPrincipal) -> None:
        role = self.get_role(role_id)
        if role is None:
            raise KeyError("Role not found.")
        if role["is_system"]:
            raise ValueError("System roles cannot be deleted.")
        if not principal.can("properties.all") and role["property_id"] != principal.property_id:
            raise PermissionError("You cannot delete this role.")
        with self._connect() as db:
            in_use = db.execute("SELECT 1 FROM admin_users WHERE role_id = ? LIMIT 1", (role_id,)).fetchone()
            if in_use:
                raise ValueError("Move users to another role before deleting this role.")
            db.execute("DELETE FROM admin_roles WHERE role_id = ?", (role_id,))
        self.audit(principal, "roles.deleted", "role", role_id, property_id=role["property_id"], metadata={"name": role["name"]})

    def list_audit(self, principal: AdminPrincipal, filters: dict[str, Any], limit: int = 100) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if not principal.can("properties.all"):
            clauses.append("property_id = ?")
            params.append(principal.property_id)
        for field in ("username", "property_id", "role_name", "action", "resource"):
            value = str(filters.get(field) or "").strip()
            if value:
                clauses.append(f"{field} = ?")
                params.append(value)
        if filters.get("start_at"):
            clauses.append("timestamp >= ?")
            params.append(int(filters["start_at"]))
        if filters.get("end_at"):
            clauses.append("timestamp <= ?")
            params.append(int(filters["end_at"]))
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(max(1, min(limit, 500)))
        with self._connect() as db:
            rows = db.execute(
                f"SELECT * FROM admin_audit_logs {where} ORDER BY timestamp DESC, audit_id DESC LIMIT ?", params  # nosec B608
            ).fetchall()
        return [
            {
                "audit_id": row["audit_id"], "timestamp": row["timestamp"], "username": row["username"],
                "display_name": row["display_name"], "role": row["role_name"], "property_id": row["property_id"],
                "action": row["action"], "resource": row["resource"], "resource_id": row["resource_id"],
                "ip_address": row["ip_address"], "session_id": row["session_id"],
                "metadata": json.loads(row["metadata_json"] or "{}"),
            }
            for row in rows
        ]

    def audit(
        self,
        principal: AdminPrincipal | None,
        action: str,
        resource: str,
        resource_id: str = "",
        *,
        property_id: str | None = None,
        ip_address: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO admin_audit_logs
                (timestamp, user_id, username, display_name, role_name, property_id, action, resource,
                 resource_id, ip_address, session_id, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(time.time()), principal.user_id if principal else None, principal.username if principal else "",
                    principal.display_name if principal else "", principal.role_name if principal else "",
                    property_id if property_id is not None else (principal.property_id if principal else None),
                    action, resource, resource_id, ip_address,
                    principal.session_id if principal else "", json.dumps(metadata or {}, separators=(",", ":")),
                ),
            )

    def audit_row(
        self,
        row: sqlite3.Row,
        action: str,
        resource: str,
        resource_id: str,
        ip_address: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as db:
            role = db.execute("SELECT name FROM admin_roles WHERE role_id = ?", (row["role_id"],)).fetchone()
            db.execute(
                """
                INSERT INTO admin_audit_logs
                (timestamp, user_id, username, display_name, role_name, property_id, action, resource, resource_id, ip_address, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(time.time()), row["user_id"], row["username"], row["display_name"],
                    role["name"] if role else "", row["property_id"], action, resource, resource_id,
                    ip_address, json.dumps(metadata or {}, separators=(",", ":")),
                ),
            )

    def _assert_user_scope(self, user: dict[str, Any], principal: AdminPrincipal) -> None:
        if not principal.can("properties.all") and user["property_id"] != principal.property_id:
            raise PermissionError("You cannot manage a user outside your assigned property.")

    def _login_rate_limited(self, ip_address: str, now: int) -> bool:
        if not ip_address:
            return False
        with self._connect() as db:
            row = db.execute(
                "SELECT COUNT(*) AS failures FROM admin_login_attempts WHERE ip_address = ? AND success = 0 AND attempted_at >= ?",
                (ip_address[:120], now - 300),
            ).fetchone()
        return bool(row and row["failures"] >= 20)

    def _record_login_attempt(self, ip_address: str, success: bool, now: int) -> None:
        if not ip_address:
            return
        with self._connect() as db:
            db.execute(
                "INSERT INTO admin_login_attempts (ip_address, attempted_at, success) VALUES (?, ?, ?)",
                (ip_address[:120], now, 1 if success else 0),
            )
            db.execute("DELETE FROM admin_login_attempts WHERE attempted_at < ?", (now - 86400,))

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _serialize_role(self, row: sqlite3.Row) -> dict[str, Any]:
        with self._connect() as db:
            permissions = [
                item["permission"]
                for item in db.execute(
                    "SELECT permission FROM admin_role_permissions WHERE role_id = ? ORDER BY permission",
                    (row["role_id"],),
                ).fetchall()
            ]
        payload = {
            "role_id": row["role_id"], "name": row["name"], "slug": row["slug"],
            "description": row["description"], "property_id": row["property_id"],
            "is_system": bool(row["is_system"]), "permissions": permissions,
            "created_at": row["created_at"], "updated_at": row["updated_at"],
        }
        if "user_count" in row.keys():
            payload["user_count"] = row["user_count"]
        return payload

    @staticmethod
    def _serialize_user(row: sqlite3.Row) -> dict[str, Any]:
        payload = {
            "id": row["user_id"], "username": row["username"], "display_name": row["display_name"],
            "email": row["email"], "role_id": row["role_id"], "role": row["role_name"],
            "role_slug": row["role_slug"], "property_id": row["property_id"],
            "department_id": row["department_id"] if "department_id" in row.keys() else None,
            "status": row["status"],
            "failed_login_count": row["failed_login_count"], "locked_until": row["locked_until"],
            "force_password_change": bool(row["force_password_change"]), "last_login": row["last_login_at"],
            "created": row["created_at"], "updated": row["updated_at"],
        }
        if "active_sessions" in row.keys():
            payload["active_sessions"] = row["active_sessions"]
        return payload
