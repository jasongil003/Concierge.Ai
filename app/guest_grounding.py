"""Helpers for evidence-backed guest answers.

Source IDs are provenance references only. A syntactically valid reference is
not evidence that a record exists, is guest-visible, or entails any text. The
request handler resolves references against the current property records, and
factual response text is rendered from those records rather than provider prose.
"""

from __future__ import annotations

import re
import unicodedata


_SOURCE_SEGMENT = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")

# An unrecognized property question must not be sent to free-form model
# generation. Known facts are answered from records before this guard runs;
# unknown requests fall back to an explicit verification message. Include
# common guest terms in English, Spanish, French, and Filipino so a language
# switch cannot turn a hotel-fact request into a model-answer bypass.
_GUEST_FACT_TERMS = (
    "hotel", "property", "room", "my stay", "our stay", "your hotel", "your property",
    "front desk", "frontdesk", "concierge", "check-in", "check in", "checkin",
    "checkout", "check-out", "check out", "pool", "swimming", "piscina",
    "gym", "fitness", "gimnasio", "spa", "sauna", "restaurant", "restaurante",
    "restawran", "dining", "breakfast", "desayuno", "agahan", "petit dejeuner",
    "brunch", "lunch", "almuerzo", "tanghalian", "dinner", "supper", "cena", "hapunan",
    "cafe", "café", "menu", "menu", "menu", "food", "comida", "wifi", "wi-fi",
    "internet", "hours", "horario", "heures", "price", "precio", "tarif", "cost",
    "fee", "policy", "policies", "politica", "politique", "pet", "pets", "mascotas",
    "dog", "cat", "housekeeping", "limpieza", "extra pillow", "pillow", "almohada",
    "unan", "towel", "toalla", "tuwalya", "parking", "shuttle", "airport transfer",
    "laundry", "room service", "availability", "available", "open now", "map",
    "directions", "facility", "facilities", "amenity", "amenities", "attraction",
    "nearby", "near me", "local places", "where to eat", "what to do",
    "crib", "cot", "baby bed", "extra bed", "rollaway", "minibar", "mini bar",
    "luggage", "baggage", "bag storage", "late checkout", "late check-out", "early check-in",
    "late check in", "tip", "tipping", "gratuity", "butler", "bellhop", "porter",
    "elevator", "lift", "smoking", "non-smoking", "air conditioning", "aircon", "a/c",
    "room key", "key card", "lost and found", "accessible room", "wheelchair", "baby chair",
    "extra blanket", "blanket", "iron", "hair dryer", "hairdryer", "adapter", "charger",
    "saan matutulog", "kuwarto", "silid", "habitación", "habitacion", "cuna", "equipaje",
    "ascensor", "elevador", "propina", "equipement", "lit bebe", "bagages", "pourboire",
)


def source_id(property_id: str, record_type: str, record_id: str, field: str = "") -> str:
    """Create a bounded, property-scoped reference for a current guest record."""
    parts = [str(property_id), str(record_type), str(record_id)]
    if field:
        parts.append(str(field))
    # Colons are reserved as separators. Replacing them also makes a source
    # reference unambiguous when it is resolved against the owning property.
    clean = [re.sub(r"[^A-Za-z0-9_.-]", "_", part.strip())[:80] for part in parts]
    return "guest:" + ":".join(clean)


def parse_source_id(value: str) -> tuple[str, str, str, str] | None:
    """Parse only the reference shape; callers must still resolve the record."""
    if not isinstance(value, str) or len(value) > 256:
        return None
    parts = value.split(":")
    if len(parts) not in {4, 5} or parts[0] != "guest":
        return None
    property_id, record_type, record_id = parts[1:4]
    field = parts[4] if len(parts) == 5 else ""
    if not all(_SOURCE_SEGMENT.fullmatch(item) for item in (property_id, record_type, record_id)):
        return None
    if field and not _SOURCE_SEGMENT.fullmatch(field):
        return None
    return property_id, record_type, record_id, field


def normalize_guest_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or "")).casefold()
    return " ".join("".join(ch for ch in decomposed if not unicodedata.combining(ch)).split())


def requires_verified_guest_answer(message: str) -> bool:
    """Return True for likely property, service, dining, or local fact requests.

    This is a routing guard, not a claim verifier. It ensures that questions
    about hotel facts reach deterministic evidence rendering or a safe fallback
    before free-form provider text can be returned.
    """
    raw = str(message or "")
    normalized = normalize_guest_text(raw)
    if not normalized:
        return False
    if any(term in normalized for term in _GUEST_FACT_TERMS):
        return True
    return False
