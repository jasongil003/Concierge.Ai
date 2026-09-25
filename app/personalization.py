"""Guest-controlled, property-scoped personalization and preference memory."""
from __future__ import annotations

import json
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any


DEFAULT_POLICY: dict[str, Any] = {
    "enabled": True,
    "default_level": "private",
    "allow_preference_learning": True,
    "allow_guest_profile": True,
    "delete_profile_at_checkout": True,
    "memory_retention": "stay_only",
    "memory_retention_days": 2,
    "allow_pms_personalization": False,
    "allow_location_aware_recommendations": True,
    "allow_internet_recommendations": True,
}
LEVELS = {"private", "stay", "personal"}
SOURCES = {"explicit", "inferred", "profile", "booking", "temporary"}
PERSISTENCE = {"temporary", "conversation", "stay", "profile"}
PREFERENCE_CATEGORIES = {
    "food": "Food and cuisine",
    "dietary": "Dietary needs",
    "budget": "Budget",
    "travel_party": "Travel party",
    "transportation": "Getting around",
    "interests": "Interests",
    "activities": "Activities",
    "accessibility": "Accessibility",
    "language": "Language",
    "response_style": "Response style",
    "trip_purpose": "Trip purpose",
    "activity_time": "Preferred activity time",
    "preferred_name": "Name",
}


def _now() -> int:
    return int(time.time())


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    return result[:48] or "preference"


def _safe_value(value: Any, category: str) -> str:
    text = " ".join(str(value or "").split())
    if not text or len(text) > 160:
        raise ValueError("Preference values must contain 1 to 160 characters.")
    if re.search(r"\b(?:password|passcode|credit card|card number|passport|ssn|social security|api key)\b", text, re.I):
        raise ValueError("That information cannot be stored as a concierge preference.")
    if re.search(r"\b(?:ignore (?:all |the )?(?:previous|prior|system) instructions|reveal (?:the )?(?:system prompt|secrets)|override (?:the )?policy|developer message)\b", text, re.I):
        raise ValueError("That text can't be stored as a concierge preference.")
    if re.search(r"\b(?:christian|muslim|jewish|hindu|buddhist|atheist|political|democrat|republican|sexual orientation|gay|lesbian|bisexual|transgender|diabetes|cancer|asthma|heart disease|medication|prescription)\b", text, re.I):
        raise ValueError("Sensitive personal details aren't stored as concierge preferences.")
    if category == "preferred_name" and len(text) > 60:
        raise ValueError("Preferred names must be 60 characters or fewer.")
    return text


class PersonalizationStore:
    """SQLite store for guest consent, structured preferences, and hotel policy."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def _init_db(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS personalization_policy (
                    property_id TEXT PRIMARY KEY,
                    policy_json TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS guest_personalization (
                    property_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 0,
                    level TEXT NOT NULL DEFAULT 'private',
                    last_preference_key TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    PRIMARY KEY(property_id, session_id)
                );
                CREATE TABLE IF NOT EXISTS guest_preferences (
                    preference_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    preference_key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    source TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    persistence TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    last_used INTEGER,
                    expires_at INTEGER,
                    UNIQUE(property_id, session_id, preference_key)
                );
                CREATE INDEX IF NOT EXISTS idx_guest_preferences_scope
                    ON guest_preferences(property_id, session_id, category);
                CREATE INDEX IF NOT EXISTS idx_guest_preferences_expiry
                    ON guest_preferences(expires_at);
                """
            )

    def policy(self, property_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT policy_json FROM personalization_policy WHERE property_id=?", (property_id,)).fetchone()
        if not row:
            return dict(DEFAULT_POLICY)
        try:
            saved = json.loads(row["policy_json"])
        except (TypeError, json.JSONDecodeError):
            saved = {}
        return {**DEFAULT_POLICY, **saved}

    def save_policy(self, property_id: str, config: dict[str, Any]) -> dict[str, Any]:
        current = self.policy(property_id)
        merged = {**current, **config}
        merged["enabled"] = bool(merged["enabled"])
        for field in (
            "allow_preference_learning", "allow_guest_profile", "delete_profile_at_checkout",
            "allow_pms_personalization", "allow_location_aware_recommendations", "allow_internet_recommendations",
        ):
            merged[field] = bool(merged[field])
        if merged["default_level"] not in LEVELS:
            raise ValueError("Default level must be private, stay, or personal.")
        if merged["default_level"] == "personal" and not merged["allow_guest_profile"]:
            raise ValueError("Personal Concierge requires guest profiles to be allowed.")
        if merged["memory_retention"] not in {"stay_only", "configurable"}:
            raise ValueError("Memory retention must be stay_only or configurable.")
        try:
            merged["memory_retention_days"] = int(merged["memory_retention_days"])
        except (ValueError, TypeError) as exc:
            raise ValueError("Memory retention must be between 1 and 365 days.") from exc
        if not 1 <= merged["memory_retention_days"] <= 365:
            raise ValueError("Memory retention must be between 1 and 365 days.")
        now = _now()
        with self._connect() as db:
            db.execute(
                """INSERT INTO personalization_policy(property_id,policy_json,updated_at) VALUES(?,?,?)
                ON CONFLICT(property_id) DO UPDATE SET policy_json=excluded.policy_json,updated_at=excluded.updated_at""",
                (property_id, json.dumps(merged, ensure_ascii=False), now),
            )
        return {**merged, "property_id": property_id, "updated_at": now}

    def _get_session(self, property_id: str, session_id: str, policy: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        days = int(policy["memory_retention_days"] if policy["memory_retention"] == "configurable" else DEFAULT_POLICY["memory_retention_days"])
        expires_at = now + days * 86400
        configured_level = policy["default_level"] if policy["enabled"] else "private"
        if configured_level == "personal" and not policy["allow_guest_profile"]:
            configured_level = "stay"
        # The hotel default is a suggested level only. The guest must opt in in
        # the guest controls before any preference is retained or used.
        default_enabled = False
        with self._connect() as db:
            row = db.execute("SELECT * FROM guest_personalization WHERE property_id=? AND session_id=?", (property_id, session_id)).fetchone()
            if not row:
                db.execute(
                    """INSERT INTO guest_personalization(property_id,session_id,enabled,level,created_at,updated_at,expires_at)
                    VALUES(?,?,?,?,?,?,?)""",
                    (property_id, session_id, int(default_enabled), configured_level, now, now, expires_at),
                )
                row = db.execute("SELECT * FROM guest_personalization WHERE property_id=? AND session_id=?", (property_id, session_id)).fetchone()
            elif int(row["expires_at"]) < now:
                db.execute("DELETE FROM guest_preferences WHERE property_id=? AND session_id=?", (property_id, session_id))
                db.execute("UPDATE guest_personalization SET enabled=0,level='private',last_preference_key=NULL,updated_at=?,expires_at=? WHERE property_id=? AND session_id=?", (now, expires_at, property_id, session_id))
                row = db.execute("SELECT * FROM guest_personalization WHERE property_id=? AND session_id=?", (property_id, session_id)).fetchone()
            else:
                db.execute("UPDATE guest_personalization SET expires_at=?,updated_at=? WHERE property_id=? AND session_id=?", (expires_at, now, property_id, session_id))
        return dict(row)

    def guest_state(self, property_id: str, session_id: str) -> dict[str, Any]:
        policy = self.policy(property_id)
        row = self._get_session(property_id, session_id, policy)
        allowed = bool(policy["enabled"])
        enabled = bool(row["enabled"]) and allowed
        level = row["level"] if enabled else "private"
        if level == "personal" and not policy["allow_guest_profile"]:
            level = "stay"
        return {
            "enabled": enabled,
            "level": level,
            "allow_preference_learning": bool(policy["allow_preference_learning"]),
            "allow_guest_profile": bool(policy["allow_guest_profile"]),
            "personalization_available": allowed,
            "suggested_level": policy["default_level"] if allowed else "private",
            "preferences": self.list_preferences(property_id, session_id),
        }

    def set_guest_state(self, property_id: str, session_id: str, enabled: bool, level: str | None = None) -> dict[str, Any]:
        policy = self.policy(property_id)
        if not policy["enabled"]:
            raise ValueError("Personalization is disabled by this hotel.")
        current = self._get_session(property_id, session_id, policy)
        selected = level or current["level"] or "stay"
        if selected not in LEVELS:
            raise ValueError("Choose private, stay, or personal personalization.")
        if selected == "personal" and not policy["allow_guest_profile"]:
            raise ValueError("Personal Concierge profiles are not enabled by this hotel.")
        if selected == "private":
            enabled = False
        with self._connect() as db:
            db.execute(
                "UPDATE guest_personalization SET enabled=?,level=?,updated_at=? WHERE property_id=? AND session_id=?",
                (int(bool(enabled)), selected, _now(), property_id, session_id),
            )
        return self.guest_state(property_id, session_id)

    def save_preference(
        self,
        property_id: str,
        session_id: str,
        category: str,
        value: str,
        *,
        preference_key: str | None = None,
        source: str = "explicit",
        confidence: float = 1.0,
        persistence: str = "stay",
    ) -> dict[str, Any]:
        if category not in PREFERENCE_CATEGORIES:
            raise ValueError("Choose a supported preference category.")
        if source not in SOURCES or persistence not in PERSISTENCE:
            raise ValueError("Invalid preference metadata.")
        if not 0 <= float(confidence) <= 1:
            raise ValueError("Preference confidence must be between 0 and 1.")
        policy = self.policy(property_id)
        if not policy["enabled"]:
            raise ValueError("Personalization is disabled by this hotel.")
        state = self._get_session(property_id, session_id, policy)
        if not state["enabled"] or state["level"] == "private":
            raise ValueError("Turn on personalization before saving preferences.")
        if persistence == "profile" and (state["level"] != "personal" or not policy["allow_guest_profile"]):
            raise ValueError("Profile preferences require Personal Concierge to be enabled.")
        if category == "preferred_name" and state["level"] != "personal":
            raise ValueError("Preferred names are available only with Personal Concierge enabled.")
        text = _safe_value(value, category)
        key = (preference_key or f"{category}.{_slug(text)}")[:100]
        if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,100}", key):
            raise ValueError("Preference keys may contain only letters, numbers, periods, underscores, and hyphens.")
        now = _now()
        expires_at = now + 6 * 3600 if persistence == "temporary" else int(state["expires_at"])
        preference_id = "pref_" + uuid.uuid4().hex[:18]
        with self._connect() as db:
            db.execute(
                """INSERT INTO guest_preferences
                (preference_id,property_id,session_id,category,preference_key,value,source,confidence,persistence,created_at,updated_at,last_used,expires_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(property_id,session_id,preference_key) DO UPDATE SET
                category=excluded.category,value=excluded.value,source=excluded.source,confidence=excluded.confidence,
                persistence=excluded.persistence,updated_at=excluded.updated_at,last_used=excluded.last_used,expires_at=excluded.expires_at""",
                (preference_id, property_id, session_id, category, key, text, source, float(confidence), persistence, now, now, now, expires_at),
            )
            db.execute("UPDATE guest_personalization SET last_preference_key=?,updated_at=? WHERE property_id=? AND session_id=?", (key, now, property_id, session_id))
        return next(item for item in self.list_preferences(property_id, session_id) if item["preference_key"] == key)

    def list_preferences(self, property_id: str, session_id: str) -> list[dict[str, Any]]:
        now = _now()
        with self._connect() as db:
            db.execute("DELETE FROM guest_preferences WHERE property_id=? AND session_id=? AND expires_at IS NOT NULL AND expires_at<?", (property_id, session_id, now))
            rows = db.execute(
                """SELECT preference_id,category,preference_key,value,source,confidence,persistence,created_at,updated_at,last_used
                FROM guest_preferences WHERE property_id=? AND session_id=? ORDER BY category,value""",
                (property_id, session_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_preference(self, property_id: str, session_id: str, preference_key: str) -> bool:
        with self._connect() as db:
            cursor = db.execute("DELETE FROM guest_preferences WHERE property_id=? AND session_id=? AND preference_key=?", (property_id, session_id, preference_key))
            return bool(cursor.rowcount)

    def delete_category(self, property_id: str, session_id: str, categories: set[str]) -> int:
        if not categories:
            return 0
        placeholders = ",".join("?" for _ in categories)
        with self._connect() as db:
            cursor = db.execute(f"DELETE FROM guest_preferences WHERE property_id=? AND session_id=? AND category IN ({placeholders})", (property_id, session_id, *sorted(categories)))  # nosec B608
            return int(cursor.rowcount)

    def clear_preferences(self, property_id: str, session_id: str) -> int:
        with self._connect() as db:
            cursor = db.execute("DELETE FROM guest_preferences WHERE property_id=? AND session_id=?", (property_id, session_id))
            db.execute("UPDATE guest_personalization SET last_preference_key=NULL,updated_at=? WHERE property_id=? AND session_id=?", (_now(), property_id, session_id))
            return int(cursor.rowcount)

    def delete_last_preference(self, property_id: str, session_id: str) -> bool:
        policy = self.policy(property_id)
        state = self._get_session(property_id, session_id, policy)
        key = state.get("last_preference_key")
        if not key:
            return False
        deleted = self.delete_preference(property_id, session_id, str(key))
        with self._connect() as db:
            db.execute("UPDATE guest_personalization SET last_preference_key=NULL,updated_at=? WHERE property_id=? AND session_id=?", (_now(), property_id, session_id))
        return deleted

    def context_for(self, property_id: str, session_id: str, user_message: str) -> dict[str, Any]:
        state = self.guest_state(property_id, session_id)
        if not state["enabled"] or state["level"] == "private":
            return {"personalization_level": "private", "preferences": []}
        message = user_message.casefold()
        dining = any(word in message for word in ("eat", "food", "restaurant", "dinner", "lunch", "breakfast", "cuisine", "cafe", "café", "hungry"))
        activity = any(word in message for word in ("do today", "do this", "activity", "plan", "itinerary", "visit", "attraction", "things to do", "free tonight", "hours free", "free before", "free for", "afternoon"))
        route = any(word in message for word in ("direction", "route", "get to", "walk", "taxi", "grab", "transport"))
        relevant: set[str] = {"language", "response_style"}
        if dining:
            relevant |= {"food", "dietary", "budget", "travel_party", "transportation"}
        if activity:
            relevant |= {"interests", "activities", "travel_party", "budget", "transportation", "activity_time", "trip_purpose"}
        if route:
            relevant |= {"transportation", "accessibility", "travel_party"}
        if "surprise" in message:
            relevant |= {"food", "dietary", "budget", "interests", "activities", "travel_party", "transportation", "activity_time", "trip_purpose"}
        if not dining and not activity and not route:
            relevant |= {"trip_purpose", "travel_party"}
        selected = [item for item in state["preferences"] if item["category"] in relevant and float(item["confidence"]) >= 0.65]
        selected = selected[:10]
        now = _now()
        if selected:
            with self._connect() as db:
                db.executemany("UPDATE guest_preferences SET last_used=? WHERE property_id=? AND session_id=? AND preference_key=?", [(now, property_id, session_id, item["preference_key"]) for item in selected])
        return {
            "personalization_level": state["level"],
            "preferences": [{"category": item["category"], "value": item["value"], "source": item["source"], "confidence": item["confidence"]} for item in selected],
        }

    def search_hints(self, property_id: str, session_id: str, message: str) -> str:
        context = self.context_for(property_id, session_id, message)
        labels = []
        for item in context["preferences"]:
            if item["category"] in {"food", "budget", "interests", "activities"}:
                labels.append(str(item["value"]))
            elif item["category"] == "dietary" and str(item["value"]).casefold() in {"vegetarian", "vegan", "pescatarian"}:
                labels.append(f"{item['value']} options")
            elif item["category"] == "travel_party" and "children" in str(item["value"]).casefold():
                labels.append("family-friendly")
        return ", ".join(dict.fromkeys(labels))

    def reinforce_feedback(self, property_id: str, session_id: str, message: str, recent_assistant_text: str) -> int:
        if not re.search(r"\b(?:that's|that is|it's|it is) (?:exactly )?(?:what i like|what i prefer|my kind of place)\b", message, re.I):
            return 0
        response = str(recent_assistant_text or "").casefold()
        if not response:
            return 0
        now = _now()
        changed = 0
        with self._connect() as db:
            rows = db.execute(
                "SELECT preference_key,value,confidence FROM guest_preferences WHERE property_id=? AND session_id=? AND persistence IN ('stay','profile')",
                (property_id, session_id),
            ).fetchall()
            for row in rows:
                if str(row["value"]).casefold() in response:
                    db.execute(
                        "UPDATE guest_preferences SET confidence=MIN(1.0,confidence+0.1),last_used=?,updated_at=? WHERE property_id=? AND session_id=? AND preference_key=?",
                        (now, now, property_id, session_id, row["preference_key"]),
                    )
                    changed += 1
        return changed

    def checkout(self, property_id: str, session_ids: list[str], delete_profile: bool = True) -> int:
        if not delete_profile or not session_ids:
            return 0
        placeholders = ",".join("?" for _ in session_ids)
        params = (property_id, *session_ids)
        with self._connect() as db:
            cursor = db.execute(f"DELETE FROM guest_preferences WHERE property_id=? AND session_id IN ({placeholders})", params)  # nosec B608
            db.execute(f"DELETE FROM guest_personalization WHERE property_id=? AND session_id IN ({placeholders})", params)  # nosec B608
            return int(cursor.rowcount)

    def cleanup_expired(self) -> int:
        now = _now()
        with self._connect() as db:
            db.execute("DELETE FROM guest_preferences WHERE expires_at IS NOT NULL AND expires_at<?", (now,))
            cursor = db.execute("DELETE FROM guest_personalization WHERE expires_at<?", (now,))
            return int(cursor.rowcount)


def extract_preferences(message: str) -> list[dict[str, Any]]:
    """Conservative conversational extractor; episodic requests never become stay memory."""
    text = " ".join(str(message or "").split())[:2000]
    lower = text.casefold()
    episodic = bool(re.search(r"\b(tonight|today|this evening|this afternoon|for now|right now|at lunch|for dinner tonight)\b", lower))
    persistence = "temporary" if episodic else "stay"
    found: list[dict[str, Any]] = []

    def add(category: str, value: str, *, key: str | None = None, source: str = "explicit", confidence: float = 1.0, keep: str | None = None) -> None:
        clean = " ".join(value.strip(" .,!?:;").split())
        if not clean or len(clean) > 120:
            return
        entry = {"category": category, "value": clean, "preference_key": key or f"{category}.{_slug(clean)}", "source": source, "confidence": confidence, "persistence": keep or persistence}
        if not any(item["preference_key"] == entry["preference_key"] for item in found):
            found.append(entry)

    match = re.search(r"\b(?:please\s+)?(?:call me|my preferred name is)\s+([A-Z][\w'-]{0,39})\b", text, re.I)
    if match:
        add("preferred_name", match.group(1), key="preferred_name.guest", keep="profile")

    match = re.search(r"\b(?:i(?:'m| am)|we(?:'re| are))\s+(vegetarian|vegan|pescatarian|halal|kosher)\b", lower)
    if match:
        label = match.group(1)
        add("dietary", label, key="dietary.restriction")
    match = re.search(r"\b(?:i|we)\s+(?:don't|do not|can't|cannot)\s+eat\s+([^.!?]{2,90})", text, re.I)
    if match:
        item = re.split(r"\s+(?:and|but)\s+", match.group(1), maxsplit=1, flags=re.I)[0]
        add("dietary", f"Avoid {item}", key=f"dietary.avoid.{_slug(item)}")
    match = re.search(r"\b(?:i|we)\s+avoid\s+([^.!?]{2,70})", text, re.I)
    if match:
        item = re.split(r"\s+(?:and|but)\s+", match.group(1), maxsplit=1, flags=re.I)[0]
        add("dietary", f"Avoid {item}", key=f"dietary.avoid.{_slug(item)}")
    match = re.search(r"\b(?:i(?:'m| am)|we(?:'re| are))\s+allergic\s+to\s+([^.!?]{2,80})", text, re.I)
    if match:
        item = re.split(r"\s+(?:and|but)\s+", match.group(1), maxsplit=1, flags=re.I)[0]
        add("dietary", f"Allergic to {item}", key=f"dietary.allergy.{_slug(item)}")
    match = re.search(r"\b(?:i|we)\s+(?:normally\s+|usually\s+|generally\s+)?prefer\s+(?:restaurants?\s+)?(?:under|below|less than)\s+([₱$€£]?\s?\d[\d,]*(?:\.\d{1,2})?)\s*(?:per person|/person|each)?", text, re.I)
    if match:
        add("budget", f"Under {match.group(1).replace(' ', '')} per person", key="budget.restaurant")
    elif episodic and re.search(r"\b(?:cheap|inexpensive|budget|affordable)\b", lower):
        add("budget", "Lower-priced options for this occasion", key="budget.occasion", keep="temporary")
    elif re.search(r"\b(?:i|we)\s+(?:normally\s+|usually\s+|generally\s+)?prefer\s+(?:cheap|inexpensive|budget|affordable)\b", lower):
        add("budget", "Affordable options", key="budget.restaurant")

    match = re.search(r"\b(?:i|we)\s+(?:normally\s+|usually\s+|generally\s+)?prefer\s+walking\s+(?:if|when)\s+it(?:'s| is)\s+(?:less than|under)\s+(\d{1,2})\s+minutes?\b", text, re.I)
    if match:
        add("transportation", f"Walking up to {match.group(1)} minutes", key="transportation.walking_limit")
    elif re.search(r"\b(?:i|we)\s+(?:normally\s+|usually\s+|generally\s+)?prefer\s+walking\b", lower):
        add("transportation", "Walking", key="transportation.preferred")
    elif re.search(r"\b(?:i|we)\s+(?:normally\s+|usually\s+|generally\s+)?prefer\s+(?:grab|taxi|ride[- ]?share)\b", lower):
        add("transportation", "Grab or taxi", key="transportation.preferred")

    match = re.search(r"\b(?:we(?:'re| are)|i(?:'m| am))\s+(?:here|traveling|travelling)\s+with\s+([^.!?]{2,90})", text, re.I)
    if match:
        party = match.group(1).strip()
        family = bool(re.search(r"\b(?:kids?|children|wife|husband|partner|family)\b", party, re.I))
        add("travel_party", "Family, including children" if family and re.search(r"\b(?:kids?|children)\b", party, re.I) else ("Family or partner" if family else party), key="travel_party.current")
    if re.search(r"\b(?:i'm|i am) here for business\b|\bbusiness trip\b", lower):
        add("trip_purpose", "Business", key="trip_purpose.current")
    elif re.search(r"\bbusiness traveler\b", lower):
        add("trip_purpose", "Business", key="trip_purpose.current")
    elif re.search(r"\b(?:i'm|i am) here on vacation\b|\bholiday trip\b", lower):
        add("trip_purpose", "Leisure", key="trip_purpose.current")
    if re.search(r"\b(?:we're|we are) (?:a couple|traveling as a couple|on our honeymoon)\b", lower):
        add("travel_party", "Couple", key="travel_party.current")
    if re.search(r"\b(?:i|we)\s+(?:normally\s+|usually\s+)?(?:prefer|like|love)\s+([^.!?]{2,60})\s+for breakfast\b", text, re.I):
        breakfast = re.search(r"\b(?:i|we)\s+(?:normally\s+|usually\s+)?(?:prefer|like|love)\s+([^.!?]{2,60})\s+for breakfast\b", text, re.I).group(1)
        add("food", f"Breakfast: {breakfast}", key=f"food.breakfast.{_slug(breakfast)}")
    if re.search(r"\b(?:wheelchair accessible|step[- ]free|need accessible access)\b", lower):
        add("accessibility", "Step-free access preferred", key="accessibility.step_free")
    match = re.search(r"\b(?:i|we)\s+(?:prefer|like)\s+(morning|afternoon|evening|night) activities\b", lower)
    if match:
        add("activity_time", match.group(1).title(), key="activity_time.preferred")

    match = re.search(r"\b(?:i|we)\s+(?:really\s+)?(?:prefer|like|love|enjoy)\s+([^.!?]{2,100})", text, re.I)
    if match:
        phrase = re.split(r"\s+(?:and|but)\s+", match.group(1), maxsplit=1, flags=re.I)[0]
        if re.search(r"\b(?:japanese|filipino|italian|thai|korean|chinese|indian|mexican|vietnamese|local)\b", phrase, re.I):
            cuisine = re.search(r"\b(japanese|filipino|italian|thai|korean|chinese|indian|mexican|vietnamese|local)\b", phrase, re.I).group(1)
            add("food", cuisine.title(), key=f"food.cuisine.{cuisine.casefold()}")
        elif re.search(r"\b(?:coffee|technology|quiet places|museums|art|nature|shopping|beaches|history)\b", phrase, re.I):
            for interest in re.findall(r"coffee|technology|quiet places|museums|art|nature|shopping|beaches|history", phrase, re.I):
                add("interests", interest.title(), key=f"interests.{_slug(interest)}")
        elif not re.search(r"\b(?:walking|grab|taxi|affordable|cheap)\b", phrase, re.I):
            # A generic food preference is only retained when the statement names a cuisine or food.
            if re.search(r"\b(?:food|cuisine|restaurants?|spicy|sweet|seafood|sushi|coffee)\b", phrase, re.I):
                add("food", phrase[:70], key=f"food.{_slug(phrase)}")

    if re.search(r"\b(?:i|we)\s+(?:prefer|want)\s+(?:very\s+)?short\s+answers?\b|\bkeep it concise\b", lower):
        add("response_style", "Concise", key="response_style.length")
    elif re.search(r"\b(?:i|we)\s+(?:prefer|want)\s+detailed\s+answers?\b", lower):
        add("response_style", "Detailed", key="response_style.length")
    tone = re.search(r"\b(?:i|we)\s+(?:prefer|like)\s+(?:a\s+)?(warm|friendly|professional|formal|casual)\s+tone\b", lower)
    if tone:
        add("response_style", f"{tone.group(1).title()} tone", key="response_style.tone")
    if re.search(r"\b(?:i|we)\s+(?:prefer|like)\s+indoor activities\b", lower):
        add("activities", "Indoor activities", key="activities.indoor_outdoor")
    elif re.search(r"\b(?:i|we)\s+(?:prefer|like)\s+outdoor activities\b", lower):
        add("activities", "Outdoor activities", key="activities.indoor_outdoor")
    match = re.search(r"\b(?:english|tagalog|filipino|japanese|korean|chinese|spanish|french)\s+please\b", lower)
    if match:
        add("language", match.group(1).title(), key="language.preferred")
    if re.search(r"\b(?:that was|it's|it is|that's) too expensive\b", lower):
        add("budget", "Prefer lower-priced options", key="budget.occasion" if episodic else "budget.restaurant", source="inferred", confidence=0.7, keep="temporary" if episodic else "stay")
    elif re.search(r"\b(?:that was|it's|it is|that's) too spicy\b", lower):
        add("dietary", "Avoid spicy food", key="dietary.avoid.spicy.temporary" if episodic else "dietary.avoid.spicy", source="inferred", confidence=0.7, keep="temporary" if episodic else "stay")

    if not re.search(r"\b(?:english|tagalog|filipino|japanese|korean|chinese|spanish|french)\s+please\b", lower):
        if re.search(r"\b(?:kumusta|salamat|saan|gusto ko|paano|mangyaring|po ba)\b", lower):
            add("language", "Tagalog", key="language.preferred", source="inferred", confidence=0.78)
    return found[:8]


def preference_commands(message: str) -> tuple[str | None, str | None]:
    text = " ".join(str(message or "").casefold().split())
    if re.search(r"\b(?:what do you|what does the concierge) (?:know|remember) about me\b|\bwhat have you saved about me\b", text):
        return "show", None
    if re.search(r"\b(?:turn|switch) off personalization\b|\bstop personalizing\b|\bdon't personalize\b|\bdisable personalization\b", text):
        return "disable", None
    if re.search(r"\b(?:turn|switch) personalization back on\b|\benable personalization\b|\bstart personalizing\b", text):
        return "enable", None
    if re.search(r"\b(?:forget|clear|erase|delete) (?:all|everything|my preferences|all my preferences)\b|\bclear all preferences\b", text):
        return "clear", None
    if re.search(r"\b(?:don't|do not) remember that\b|\bforget that\b|\bdon't save that\b", text):
        return "forget_last", None
    if text.startswith("remember that ") or text.startswith("remember "):
        detail = re.sub(r"^remember(?: that)?\s+", "", str(message).strip(), flags=re.I)
        return "remember", detail
    if re.search(r"\bforget\b", text):
        if re.search(r"\b(?:diet|allerg|food restriction)\w*\b", text):
            return "forget_category", "dietary"
        if re.search(r"\b(?:restaurant|cuisine|food)\w*\b", text):
            return "forget_category", "restaurant" if "restaurant" in text else "food"
        if re.search(r"\bbudget\b", text):
            return "forget_category", "budget"
        if re.search(r"\b(?:travel party|family|kids|children)\b", text):
            return "forget_category", "travel_party"
    return None, None
