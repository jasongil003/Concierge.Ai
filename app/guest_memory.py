"""Conservative, stay-scoped guest memory extraction."""
from __future__ import annotations

import re
from typing import Any


_PREFERENCE_PATTERNS = (
    (re.compile(r"\b(?:i|we)\s+(?:really\s+)?(?:prefer|like|love)\s+([^.!?]{2,100}?)(?=\s+and\s+(?:i|we)\b|[.!?]|$)", re.I), "prefers {}"),
    (re.compile(r"\b(?:i|we)\s+(?:don't|do not|cannot|can't)\s+(?:eat|like|want)\s+([^.!?]{2,100}?)(?=\s+and\s+(?:i|we)\b|[.!?]|$)", re.I), "avoids {}"),
    (re.compile(r"\b(?:i am|i'm|we are|we're)\s+allergic\s+to\s+([^.!?]{2,100}?)(?=\s+and\s+(?:i|we)\b|[.!?]|$)", re.I), "allergic to {}"),
)


def explicit_preferences(message: str) -> list[str]:
    """Extract only narrow first-person preference statements; never infer traits."""
    text = " ".join(str(message or "").split())[:1200]
    output: list[str] = []
    for pattern, template in _PREFERENCE_PATTERNS:
        for match in pattern.finditer(text):
            value = re.sub(r"\s+", " ", match.group(1)).strip(" ,;:")[:80]
            if value and not re.search(r"\b(?:ignore|override|system prompt|password|secret|policy)\b", value, re.I):
                item = template.format(value.lower())
                if item not in output:
                    output.append(item)
    return output[:5]


def merge_preference_memory(memory: dict[str, Any], message: str) -> dict[str, Any]:
    updated = dict(memory or {})
    existing = updated.get("preferences", [])
    existing = [str(item)[:120] for item in existing if isinstance(item, str)] if isinstance(existing, list) else []
    for preference in explicit_preferences(message):
        if preference not in existing:
            existing.append(preference)
    updated["preferences"] = existing[-20:]
    return updated
