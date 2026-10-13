"""Deterministic evidence checks for guest-visible hotel facts.

Hotel answers may be phrased by an AI provider, but property details must come
from guest-visible records. This module supplies stable per-property references
and a conservative last-mile check for high-risk hospitality claims.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
import unicodedata


_PROPERTY_FEATURES = (
    "swimming pool", "pool", "gym", "fitness center", "fitness centre", "spa",
    "sauna", "steam room", "restaurant", "dining", "breakfast", "brunch", "lunch", "dinner",
    "cafe", "café", "bar", "lounge", "rooftop", "terrace", "garden", "view deck",
    "room service", "housekeeping", "turndown service", "bell service", "luggage storage",
    "baggage storage", "airport transfer", "wake-up call", "ice machine", "crib", "rollaway bed",
    "extra pillow", "pillow", "towel", "laundry", "dry cleaning", "parking", "valet", "shuttle",
    "airport transfer", "business center", "business centre", "wifi", "wi-fi",
    "internet", "concierge", "front desk", "check-in", "checkout", "check out",
    "meeting room", "conference room", "conference center", "conference centre",
    "kids club", "childcare", "babysitting", "pet service", "bicycle rental", "bike rental",
    "electric vehicle charging", "ev charging", "private beach", "beach access", "room upgrade",
    "late checkout", "early check-in", "cooking class", "yoga class", "fitness class",
)
_MONEY = re.compile(
    r"(?i)(?:(?P<symbol>[$€£₱])\s*(?P<symbol_amount>\d+(?:[,.]\d{1,2})?)|"
    r"(?P<code>USD|PHP|EUR|GBP|AUD|CAD|JPY)\s*(?P<code_amount>\d+(?:[,.]\d{1,2})?)|"
    r"(?P<amount>\d+(?:[,.]\d{1,2})?)\s*(?P<word>USD|PHP|EUR|GBP|dollars?|pesos?|euros?|pounds?))"
)
_TIME = re.compile(
    r"(?i)(?<![\w])(?P<hour>\d{1,2})(?::(?P<minute>[0-5]\d))?\s*"
    r"(?P<ampm>a\.?m\.?|p\.?m\.?)(?![\w])"
)
_CLAIM_VERB = re.compile(
    r"(?i)(?:\b(?:is|are|has|have|offers?|provides?|features?|includes?|serves?|costs?|charges?|"
    r"is located|are located|is on|are on|located on|is open|are open|opens?|closes?|"
    r"is available|are available|can arrange|can book|arranges?|books?|bring|send|deliver|provide)\b|"
    r"\bthere['’]s\b)"
)
_AVAILABILITY_TERMS = ("open", "closed", "available", "unavailable", "at capacity", "fully booked", "sold out")
_RECOMMENDATION_ENTITY = re.compile(
    r"(?i:\b(?:try|visit|go to|head to|check out|eat at|dine at|book at|order from))\s+"
    r"(?:(?i:the)\s+)?(?P<entity>[A-Z][A-Za-z0-9&'’-]*(?:\s+[A-Z][A-Za-z0-9&'’-]*){0,3})"
)


def source_id(property_id: str, record_type: str, record_id: str, field: str = "") -> str:
    """Create a bounded reference that cannot point across property scope."""
    parts = [str(property_id), str(record_type), str(record_id)]
    if field:
        parts.append(str(field))
    clean = [re.sub(r"[^A-Za-z0-9_.:-]", "_", part.strip())[:80] for part in parts]
    return "guest:" + ":".join(clean)


def _normal(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or "")).casefold()
    return " ".join("".join(ch for ch in decomposed if not unicodedata.combining(ch)).split())


def _money_values(value: str) -> set[tuple[str, Decimal]]:
    found: set[tuple[str, Decimal]] = set()
    for match in _MONEY.finditer(value):
        currency = match.group("symbol") or match.group("code") or match.group("word") or ""
        amount = match.group("symbol_amount") or match.group("code_amount") or match.group("amount")
        try:
            numeric = Decimal(amount.replace(",", ""))
        except (InvalidOperation, AttributeError):
            continue
        code = {"$": "usd", "€": "eur", "£": "gbp", "₱": "php"}.get(currency, currency.casefold())
        if code in {"dollar", "dollars"}:
            code = "usd"
        if code == "peso" or code == "pesos":
            code = "php"
        if code == "euro" or code == "euros":
            code = "eur"
        if code == "pound" or code == "pounds":
            code = "gbp"
        found.add((code, numeric.normalize()))
    return found


def _times(value: str) -> set[tuple[int, int]]:
    found: set[tuple[int, int]] = set()
    for match in _TIME.finditer(value):
        hour = int(match.group("hour"))
        minute = int(match.group("minute") or 0)
        meridiem = match.group("ampm").replace(".", "").casefold()
        if hour < 1 or hour > 12:
            continue
        hour = hour % 12 + (12 if meridiem == "pm" else 0)
        found.add((hour, minute))
    if re.search(r"(?i)\b24\s*(?:hours?|/\s*7)\b", value):
        found.add((24, 0))
    return found


def unsupported_hotel_claim(answer: str, evidence: str) -> bool:
    """Return True when an AI answer makes an unsupported hotel-domain claim.

    Structured hotel answers are generated from exact records elsewhere. This
    guard is deliberately conservative for free-form model output: unsupported
    property topics, amounts, operating times, and availability language cause
    the caller to use its verified-information fallback.
    """
    response = _normal(answer)
    source = _normal(evidence)
    if not response.strip():
        return False

    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", answer) if part.strip()]
    for topic in _PROPERTY_FEATURES:
        normalized_topic = _normal(topic)
        if any(
            re.search(rf"(?<!\w){re.escape(normalized_topic)}(?!\w)", _normal(sentence))
            and _CLAIM_VERB.search(sentence)
            for sentence in sentences
        ):
            # A domain noun is not itself a hotel fact. Reject property claims
            # in free-form output; verified claims are rendered from records
            # with source IDs by the structured response adapter.
            return True

    if not _money_values(answer).issubset(_money_values(evidence)):
        return True
    if not _times(answer).issubset(_times(evidence)):
        return True
    for sentence in sentences:
        mentions_feature = any(
            re.search(rf"(?<!\w){re.escape(_normal(topic))}(?!\w)", _normal(sentence))
            for topic in _PROPERTY_FEATURES
        )
        if mentions_feature:
            for status in _AVAILABILITY_TERMS:
                if re.search(rf"(?<!\w){re.escape(status)}(?!\w)", _normal(sentence)) and not re.search(
                    rf"(?<!\w){re.escape(status)}(?!\w)", source
                ):
                    return True

    for match in _RECOMMENDATION_ENTITY.finditer(answer):
        if _normal(match.group("entity")) not in source:
            return True

    if _CLAIM_VERB.search(answer) and re.search(r"(?i)\b(?:the|our|this)\s+(?:hotel|property)\b", answer):
        # Generic property-level claims are only released when the exact claim
        # occurs in guest-visible evidence. Exact approved knowledge remains
        # usable, while model paraphrases of hotel policy are fail-closed.
        normalized_answer = _normal(answer).strip(" .!?\n")
        if normalized_answer not in source:
            return True
    return False
