"""Allowlisted, permission-checked configuration actions for Admin AI.

The registry stores only pending proposals. Executors are supplied by the app
and call the same service methods as the existing Admin API routes.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import secrets
import time
from pathlib import Path
from typing import Any, Callable

from .database import connect_database


class ActionDenied(PermissionError):
    """Raised when an action is unknown or unavailable to the principal."""


class ActionValidationError(ValueError):
    """Raised when an action payload does not match its server schema."""


@dataclass(frozen=True)
class ActionContext:
    principal: Any
    property_id: str
    request: Any
    conversation_id: str
    request_id: str
    services: dict[str, Any]


@dataclass(frozen=True)
class ConfigurationAction:
    name: str
    description: str
    required_permission: str
    accepted_input_schema: dict[str, Any]
    validator: Callable[[ActionContext, dict[str, Any]], dict[str, Any]]
    executor: Callable[[ActionContext, dict[str, Any]], Any]
    preview: Callable[[ActionContext, dict[str, Any]], dict[str, Any]]
    risk_level: str = "LOW"
    confirmation_requirement: str = "normal"
    allowed_roles: frozenset[str] = frozenset()
    property_scope: str = "property"
    restaurant_scope: bool = False
    audit_event: str = "assistant.action.executed"
    rollback: Callable[[ActionContext, dict[str, Any], Any], Any] | None = None

    def public_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "required_permission": self.required_permission,
            "property_scope": self.property_scope,
            "restaurant_scope": self.restaurant_scope,
            "input_schema": self.accepted_input_schema,
            "risk_level": self.risk_level,
            "confirmation_requirement": self.confirmation_requirement,
        }


def _validate_schema(value: Any, schema: dict[str, Any], path: str = "parameters") -> None:
    expected = schema.get("type")
    type_ok = {
        "object": lambda v: isinstance(v, dict),
        "array": lambda v: isinstance(v, list),
        "string": lambda v: isinstance(v, str),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "boolean": lambda v: isinstance(v, bool),
    }
    if expected in type_ok and not type_ok[expected](value):
        raise ActionValidationError(f"{path} must be {expected}.")
    if "enum" in schema and value not in schema["enum"]:
        raise ActionValidationError(f"{path} must be one of the allowed values.")
    if expected == "string":
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", 1000000):
            raise ActionValidationError(f"{path} has an invalid length.")
        if "pattern" in schema:
            import re
            if not re.fullmatch(schema["pattern"], value):
                raise ActionValidationError(f"{path} has an invalid format.")
    if expected in {"integer", "number"}:
        if "minimum" in schema and value < schema["minimum"]:
            raise ActionValidationError(f"{path} is below the minimum.")
        if "maximum" in schema and value > schema["maximum"]:
            raise ActionValidationError(f"{path} is above the maximum.")
    if expected == "array":
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", 1000000):
            raise ActionValidationError(f"{path} has an invalid number of items.")
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(value):
                _validate_schema(item, item_schema, f"{path}[{index}]")
    if expected == "object":
        properties = schema.get("properties", {})
        missing = [key for key in schema.get("required", []) if key not in value]
        if missing:
            raise ActionValidationError(f"{path}.{missing[0]} is required.")
        if schema.get("additionalProperties", False) is False:
            unknown = sorted(set(value) - set(properties))
            if unknown:
                raise ActionValidationError(f"{path}.{unknown[0]} is not an accepted field.")
        for key, item in value.items():
            if key in properties:
                _validate_schema(item, properties[key], f"{path}.{key}")


def _validate_payload_complexity(value: Any, depth: int = 0) -> None:
    if depth > 12:
        raise ActionValidationError("Action parameters are nested too deeply.")
    if isinstance(value, dict):
        if len(value) > 100:
            raise ActionValidationError("Action parameters contain too many fields.")
        for key, item in value.items():
            if len(str(key)) > 120:
                raise ActionValidationError("An action parameter name is too long.")
            _validate_payload_complexity(item, depth + 1)
    elif isinstance(value, list):
        if len(value) > 100:
            raise ActionValidationError("Action parameters contain too many items.")
        for item in value:
            _validate_payload_complexity(item, depth + 1)
    elif isinstance(value, str) and len(value) > 8000:
        raise ActionValidationError("An action parameter value is too long.")


class ConfigurationActionRegistry:
    """Server allowlist; all permission, scope and schema checks happen here."""

    def __init__(self) -> None:
        self._actions: dict[str, ConfigurationAction] = {}

    def register(self, action: ConfigurationAction) -> None:
        if action.name in self._actions:
            raise ValueError(f"Configuration action already registered: {action.name}")
        if action.risk_level not in {"LOW", "MEDIUM", "HIGH", "RESTRICTED"}:
            raise ValueError("Unknown action risk level.")
        if action.confirmation_requirement not in {"normal", "strong", "none"}:
            raise ValueError("Unknown action confirmation requirement.")
        if action.risk_level in {"HIGH", "RESTRICTED"}:
            raise ValueError("High-risk or restricted actions cannot be registered for AI execution.")
        self._actions[action.name] = action

    def get(self, name: str) -> ConfigurationAction | None:
        return self._actions.get(name)

    @property
    def names(self) -> list[str]:
        return sorted(self._actions)

    def available(self, principal: Any, property_id: str) -> list[ConfigurationAction]:
        if not principal.can_access_property(property_id):
            return []
        return [
            action for action in self._actions.values()
            if principal.can(action.required_permission)
            and (not action.allowed_roles or principal.role_slug in action.allowed_roles)
            and not (action.restaurant_scope and not principal.can("properties.all") and not principal.can("properties.edit") and not _has_restaurant_assignment(principal, property_id))
        ]

    def prepare(self, name: str, parameters: Any, context: ActionContext) -> tuple[ConfigurationAction, dict[str, Any], dict[str, Any]]:
        action = self._actions.get(name)
        if action is None:
            raise ActionDenied("This configuration action is not available.")
        if not context.principal.can_access_property(context.property_id):
            raise ActionDenied("Property access denied.")
        if not context.principal.can(action.required_permission):
            raise ActionDenied(f"Permission required: {action.required_permission}")
        if action.allowed_roles and context.principal.role_slug not in action.allowed_roles:
            raise ActionDenied("This action is not available to your role.")
        if action.property_scope == "installation" and not context.principal.can("properties.all"):
            raise ActionDenied("This installation-wide action is not available to your role.")
        if action.risk_level in {"HIGH", "RESTRICTED"}:
            raise ActionDenied("This action is restricted from Admin AI.")
        if not isinstance(parameters, dict):
            raise ActionValidationError("parameters must be an object.")
        _validate_payload_complexity(parameters)
        if len(encode_json(parameters).encode("utf-8")) > 100_000:
            raise ActionValidationError("Action parameters are too large.")
        _validate_schema(parameters, action.accepted_input_schema)
        validated = action.validator(context, dict(parameters))
        if not isinstance(validated, dict):
            raise ActionValidationError("Action validation did not return a parameter object.")
        preview = action.preview(context, validated)
        if not isinstance(preview, dict):
            raise ActionValidationError("Action preview is unavailable.")
        return action, validated, preview

    async def execute(self, action: ConfigurationAction, context: ActionContext, parameters: dict[str, Any]) -> Any:
        result = action.executor(context, parameters)
        if hasattr(result, "__await__"):
            result = await result
        return result


def _has_restaurant_assignment(principal: Any, property_id: str) -> bool:
    """Only controls planner visibility. Every selected restaurant is checked again at prepare/confirm."""
    try:
        from .main import _assigned_restaurant_ids
        return bool(_assigned_restaurant_ids(principal, property_id))
    except Exception:
        return False


class AssistantActionProposalStore:
    """Short-lived, single-use proposals; never stores credentials or source documents."""

    TTL_SECONDS = 600

    def __init__(self, path: Path) -> None:
        self.path = path
        with connect_database(self.path) as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS assistant_action_proposals (
                    proposal_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    role_slug TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    action_name TEXT NOT NULL,
                    parameters_json TEXT NOT NULL,
                    current_json TEXT NOT NULL,
                    proposed_json TEXT NOT NULL,
                    impact TEXT NOT NULL,
                    permission_used TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    confirmation_requirement TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT NOT NULL DEFAULT '{}',
                    created_at BIGINT NOT NULL,
                    expires_at BIGINT NOT NULL,
                    confirmed_at BIGINT
                )"""
            )
            db.execute("CREATE INDEX IF NOT EXISTS idx_assistant_action_proposals_owner ON assistant_action_proposals(user_id,property_id,status,expires_at)")

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = int(time.time())
        proposal_id = secrets.token_urlsafe(24)
        row = {
            **payload,
            "proposal_id": proposal_id,
            "status": "proposed",
            "result_json": "{}",
            "created_at": now,
            "expires_at": now + self.TTL_SECONDS,
            "confirmed_at": None,
        }
        with connect_database(self.path) as db:
            db.execute(
                """INSERT INTO assistant_action_proposals
                (proposal_id,property_id,user_id,role_slug,conversation_id,action_name,parameters_json,current_json,
                 proposed_json,impact,permission_used,risk_level,confirmation_requirement,request_id,status,result_json,
                 created_at,expires_at,confirmed_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                tuple(row[key] for key in (
                    "proposal_id", "property_id", "user_id", "role_slug", "conversation_id", "action_name",
                    "parameters_json", "current_json", "proposed_json", "impact", "permission_used", "risk_level",
                    "confirmation_requirement", "request_id", "status", "result_json", "created_at", "expires_at", "confirmed_at",
                )),
            )
        return row

    def get(self, proposal_id: str, user_id: str, property_id: str) -> dict[str, Any] | None:
        with connect_database(self.path) as db:
            row = db.execute(
                "SELECT * FROM assistant_action_proposals WHERE proposal_id=? AND user_id=? AND property_id=?",
                (proposal_id, user_id, property_id),
            ).fetchone()
        return dict(row) if row else None

    def claim(self, proposal_id: str, user_id: str, property_id: str, now: int | None = None) -> dict[str, Any] | None:
        timestamp = int(now if now is not None else time.time())
        with connect_database(self.path) as db:
            cursor = db.execute(
                "UPDATE assistant_action_proposals SET status='executing' WHERE proposal_id=? AND user_id=? AND property_id=? AND status='proposed' AND expires_at>?",
                (proposal_id, user_id, property_id, timestamp),
            )
            if cursor.rowcount != 1:
                db.execute(
                    "UPDATE assistant_action_proposals SET status='expired' WHERE proposal_id=? AND user_id=? AND property_id=? AND status='proposed' AND expires_at<=?",
                    (proposal_id, user_id, property_id, timestamp),
                )
                return None
            row = db.execute(
                "SELECT * FROM assistant_action_proposals WHERE proposal_id=? AND user_id=? AND property_id=?",
                (proposal_id, user_id, property_id),
            ).fetchone()
        return dict(row) if row else None

    def finish(self, proposal_id: str, status: str, result: Any = None, confirmed_at: int | None = None) -> None:
        if status not in {"executed", "failed", "cancelled", "stale"}:
            raise ValueError("Invalid proposal status.")
        with connect_database(self.path) as db:
            db.execute(
                "UPDATE assistant_action_proposals SET status=?,result_json=?,confirmed_at=? WHERE proposal_id=? AND status='executing'",
                (status, json.dumps(result or {}, default=str, separators=(",", ":")), confirmed_at, proposal_id),
            )

    def cancel(self, proposal_id: str, user_id: str, property_id: str) -> bool:
        with connect_database(self.path) as db:
            cursor = db.execute(
                "UPDATE assistant_action_proposals SET status='cancelled' WHERE proposal_id=? AND user_id=? AND property_id=? AND status='proposed'",
                (proposal_id, user_id, property_id),
            )
        return cursor.rowcount == 1


def encode_json(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
