import math
import re
from typing import Any, Iterable
from urllib.parse import urlsplit

import httpx

from .config import settings


PLACE_HINTS = {
    "restaurant", "restaurants", "eat", "food", "cafe", "cafes", "café", "cafés",
    "coffee", "bar", "bars", "pharmacy", "pharmacies", "mall", "malls", "shopping",
    "attraction", "attractions", "tourist", "sightseeing", "nearby", "near me",
    "things to do", "activity", "activities", "plan", "visit", "tour", "tours",
    "tonight", "grocery", "groceries", "supermarket", "supermarkets",
}

_DINING_INTENT_CUES = (
    "restaurant", "restaurants", "dining", "eat", "hungry", "starving",
    "something to eat", "food", "foods", "dinner", "lunch", "breakfast",
    "cafe", "cafes", "café", "cafés", "coffee", "coffee shop", "coffee shops",
)
_ACTIVITY_INTENT_CUES = (
    "activity", "activities", "things to do", "plan", "attraction", "attractions",
    "tourist", "sightseeing", "tour", "tours", "visit", "surprise", "do this",
    "do today", "afternoon", "tonight", "free tonight", "hours free", "free before",
    "free for", "what should i do", "where can i go", "places to go",
)
_PROXIMITY_CUES = (
    "nearby", "near me", "near the hotel", "around here", "where can i go",
)

_CATEGORY_CUES = (
    ("restaurants", (
        "restaurant", "restaurants", "dining", "eat", "food", "foods", "hungry",
        "starving", "something to eat", "dinner", "lunch", "breakfast",
    )),
    ("cafes", ("cafe", "cafes", "café", "cafés", "coffee", "coffee shop", "coffee shops")),
    ("bars and nightlife", ("bar", "bars", "pub", "pubs", "nightlife")),
    ("evening activities", ("tonight",)),
    ("pharmacies", ("pharmacy", "pharmacies", "chemist", "chemists", "drugstore", "drugstores")),
    ("shopping malls and shops", ("mall", "malls", "shopping", "shopping center", "shopping centres", "store", "stores")),
    ("grocery stores", ("grocery", "groceries", "supermarket", "supermarkets")),
)
_GENERIC_PLACE_CUES = (
    "nearby", "near me", "things to do", "activity", "activities", "attraction",
    "attractions", "tourist", "visit", "sightseeing", "tour", "tours", "plan",
)
_PRICE_LEVELS = {
    "PRICE_LEVEL_FREE",
    "PRICE_LEVEL_INEXPENSIVE",
    "PRICE_LEVEL_MODERATE",
    "PRICE_LEVEL_EXPENSIVE",
    "PRICE_LEVEL_VERY_EXPENSIVE",
}
_MAX_GOOGLE_RADIUS_METERS = 50_000
_MAX_GOOGLE_RESULTS = 20


def _contains_phrase(text: str, phrase: str) -> bool:
    return re.search(r"(?<![\w])" + re.escape(phrase) + r"(?![\w])", text) is not None


def contains_any_phrase(message: str, phrases: Iterable[str]) -> bool:
    """Match complete words and phrases so cue fragments do not trigger intent."""
    if not isinstance(message, str):
        return False
    text = message.casefold()
    return any(_contains_phrase(text, phrase.casefold()) for phrase in phrases)


def has_dining_intent(message: str) -> bool:
    return contains_any_phrase(message, _DINING_INTENT_CUES)


def has_activity_intent(message: str) -> bool:
    if contains_any_phrase(message, _ACTIVITY_INTENT_CUES):
        return True
    # A generic location request means attractions only when it is not attached
    # to a more specific dining request such as “restaurants nearby”.
    return not has_dining_intent(message) and contains_any_phrase(message, _PROXIMITY_CUES)


def _matched_categories(text: str) -> list[str]:
    return [
        category
        for category, cues in _CATEGORY_CUES
        if any(_contains_phrase(text, cue) for cue in cues)
    ]


def _categories_for_message(message: str) -> list[str]:
    text = message.casefold() if isinstance(message, str) else ""
    categories = _matched_categories(text)
    activity_requested = contains_any_phrase(text, _ACTIVITY_INTENT_CUES)
    has_activity_category = "evening activities" in categories
    if activity_requested and not has_activity_category:
        categories.append("tourist attractions")
    elif not categories and any(_contains_phrase(text, cue) for cue in _GENERIC_PLACE_CUES):
        categories.append("tourist attractions")
    return categories


def required_category_permissions(message: str) -> set[str]:
    """Return only category-specific permissions required by the fixed query."""
    categories = set(_categories_for_message(message))
    permissions: set[str] = set()
    if categories.intersection({"restaurants", "cafes", "bars and nightlife"}):
        permissions.add("restaurant_search_enabled")
    if categories.intersection({"evening activities", "tourist attractions"}):
        permissions.add("attractions_enabled")
    return permissions


def _category_query(message: str) -> str:
    """Return a fixed category query; never forward guest-authored text."""
    categories = _categories_for_message(message)
    if categories:
        return ", ".join(categories)
    return "local places"


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _coordinates(latitude: Any, longitude: Any) -> tuple[float, float] | None:
    lat = _finite_number(latitude)
    lon = _finite_number(longitude)
    if lat is None or lon is None or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None
    return lat, lon


def _safe_google_maps_url(value: Any) -> str | None:
    if not isinstance(value, str) or not value or len(value) > 2048 or value != value.strip():
        return None
    if any(ord(char) < 32 or char.isspace() for char in value):
        return None
    try:
        parsed = urlsplit(value)
        hostname = (parsed.hostname or "").casefold().rstrip(".")
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.casefold() != "https"
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
    ):
        return None
    path = parsed.path or "/"
    if hostname in {"google.com", "www.google.com"}:
        is_maps_path = path == "/maps" or path.startswith("/maps/")
    elif hostname == "maps.google.com":
        is_maps_path = path == "/" or path == "/maps" or path.startswith("/maps/")
    elif hostname == "maps.app.goo.gl":
        is_maps_path = path not in {"", "/"} and not path.startswith("//")
    else:
        is_maps_path = False
    return value if is_maps_path else None


def _safe_provider_category(place: dict[str, Any]) -> str | None:
    display_name = place.get("primaryTypeDisplayName")
    category = display_name.get("text") if isinstance(display_name, dict) else None
    if (
        isinstance(category, str)
        and category.strip()
        and len(category) <= 100
        and not any(ord(char) < 32 or char in "<>" for char in category)
    ):
        return category.strip()

    primary_type = place.get("primaryType")
    if isinstance(primary_type, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", primary_type):
        return primary_type.replace("_", " ").title()
    return None


def _valid_place(place: Any, origin: tuple[float, float], radius_meters: float) -> dict[str, Any] | None:
    if not isinstance(place, dict):
        return None
    point = place.get("location")
    if not isinstance(point, dict):
        return None
    coordinates = _coordinates(point.get("latitude"), point.get("longitude"))
    if coordinates is None:
        return None
    distance = _distance_meters(origin[0], origin[1], coordinates[0], coordinates[1])
    if distance > radius_meters:
        return None

    display_name = place.get("displayName")
    name = display_name.get("text") if isinstance(display_name, dict) else None
    if not isinstance(name, str) or not name.strip():
        return None

    address = place.get("formattedAddress")
    if not isinstance(address, str):
        address = None
    place_id = place.get("id")
    if not isinstance(place_id, str) or not place_id.strip():
        place_id = None

    rating = _finite_number(place.get("rating"))
    if rating is None or not 0 <= rating <= 5:
        rating = None
    reviews = place.get("userRatingCount")
    if isinstance(reviews, bool) or not isinstance(reviews, int) or reviews < 0:
        reviews = None
    price_level = place.get("priceLevel")
    if not isinstance(price_level, str) or price_level not in _PRICE_LEVELS:
        price_level = None

    hours = place.get("currentOpeningHours")
    if not isinstance(hours, dict):
        hours = {}
    open_now = hours.get("openNow")
    if not isinstance(open_now, bool):
        open_now = None
    weekday_descriptions = hours.get("weekdayDescriptions")
    if not isinstance(weekday_descriptions, list):
        weekday_descriptions = []
    opening_hours = [
        item[:200] for item in weekday_descriptions[:7]
        if isinstance(item, str)
    ]

    return {
        "place_id": place_id,
        "name": name.strip()[:300],
        "category": _safe_provider_category(place),
        "address": address[:500] if address is not None else None,
        "rating": rating,
        "reviews": reviews,
        "price_level": price_level,
        "open_now": open_now,
        "opening_hours": opening_hours,
        "distance_meters": round(distance),
        "distance_type": "straight_line",
        "maps_url": _safe_google_maps_url(place.get("googleMapsUri")),
    }


class GooglePlaces:
    @staticmethod
    def should_search(message: str) -> bool:
        return contains_any_phrase(message, PLACE_HINTS)

    async def search(
        self,
        message: str,
        latitude: float | None,
        longitude: float | None,
        open_now: bool = True,
        radius_meters: int | None = None,
        max_results: int | None = None,
    ) -> list[dict[str, Any]]:
        places, _ = await self.search_with_status(
            message,
            latitude,
            longitude,
            open_now=open_now,
            radius_meters=radius_meters,
            max_results=max_results,
        )
        return places

    async def search_with_status(
        self,
        message: str,
        latitude: float | None,
        longitude: float | None,
        open_now: bool = True,
        radius_meters: int | None = None,
        max_results: int | None = None,
    ) -> tuple[list[dict[str, Any]], str]:
        """Search live and report why no verified results were returned.

        Google Places content cannot be cached under the current provider policy,
        so this adapter deliberately makes a fresh request for each allowed search.
        """
        origin = _coordinates(latitude, longitude)
        radius = _finite_number(
            settings.places_radius_meters if radius_meters is None else radius_meters
        )
        result_limit = _result_limit(
            settings.places_max_results if max_results is None else max_results
        )
        if (
            not settings.google_places_api_key
            or origin is None
            or radius is None
            or not 0 < radius <= _MAX_GOOGLE_RADIUS_METERS
        ):
            return [], "configuration_required"
        if not self.should_search(message):
            return [], "not_applicable"

        payload = {
            "textQuery": _category_query(message),
            "pageSize": result_limit,
            "locationBias": {
                "circle": {
                    "center": {
                        "latitude": origin[0],
                        "longitude": origin[1],
                    },
                    "radius": radius,
                }
            },
        }
        if open_now:
            payload["openNow"] = True
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": settings.google_places_api_key,
            "X-Goog-FieldMask": (
                "places.id,places.displayName,places.formattedAddress,"
                "places.rating,places.userRatingCount,places.priceLevel,"
                "places.currentOpeningHours.openNow,places.currentOpeningHours.weekdayDescriptions,"
                "places.googleMapsUri,places.location,places.primaryTypeDisplayName,places.primaryType"
            ),
        }

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    "https://places.googleapis.com/v1/places:searchText",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                return [], "quota_exhausted"
            return [], "unavailable"
        except (httpx.HTTPError, ValueError, TypeError):
            return [], "unavailable"

        if not isinstance(body, dict):
            return [], "unavailable"
        provider_places = body.get("places", [])
        if not isinstance(provider_places, list):
            return [], "unavailable"
        places = [
            result
            for place in provider_places[:result_limit]
            if (result := _valid_place(place, origin, radius)) is not None
        ]
        return places, "available" if places else "empty"


def _result_limit(value: Any) -> int:
    if isinstance(value, bool):
        return 6
    try:
        return max(1, min(int(value), _MAX_GOOGLE_RESULTS))
    except (TypeError, ValueError, OverflowError):
        return 6


def _distance_meters(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    earth_radius = 6_371_000
    phi_a, phi_b = math.radians(lat_a), math.radians(lat_b)
    delta_phi, delta_lambda = math.radians(lat_b - lat_a), math.radians(lon_b - lon_a)
    value = math.sin(delta_phi / 2) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    return 2 * earth_radius * math.asin(min(1, math.sqrt(value)))


def rank_places(
    places: list[dict[str, Any]],
    preferences: list[dict[str, Any]] | None = None,
    recent_messages: list[dict[str, Any]] | None = None,
    prefer_open_now: bool = True,
) -> list[dict[str, Any]]:
    """Rank by verified, available place attributes and only confident preferences."""
    preferences = preferences or []
    recent_text = " ".join(str(item.get("content") or "") for item in (recent_messages or [])[-8:]).casefold()
    match_terms = [
        str(item.get("value") or "").casefold()
        for item in preferences
        if item.get("category") in {"food", "interests", "activities"} and float(item.get("confidence", 1)) >= 0.65
    ]
    match_terms.extend(
        str(item.get("value", "")).casefold()
        for item in preferences
        if item.get("category") == "dietary" and str(item.get("value", "")).casefold() in {"vegetarian", "vegan", "pescatarian"}
    )
    low_budget = any(
        item.get("category") == "budget" and float(item.get("confidence", 1)) >= 0.65
        and any(term in str(item.get("value", "")).casefold() for term in ("cheap", "affordable", "lower-priced", "under", "budget"))
        for item in preferences
    )
    price_rank = {"PRICE_LEVEL_INEXPENSIVE": 3, "PRICE_LEVEL_MODERATE": 2, "PRICE_LEVEL_EXPENSIVE": 1, "PRICE_LEVEL_VERY_EXPENSIVE": 0}

    def score(item: dict[str, Any], index: int) -> tuple[float, int]:
        name = str(item.get("name") or "").casefold()
        points = 0.0
        if prefer_open_now and item.get("open_now") is True:
            points += 4
        elif prefer_open_now and item.get("open_now") is False:
            points -= 8
        if item.get("distance_meters") is not None:
            points += max(0, 3 - float(item["distance_meters"]) / 1500)
        if item.get("rating") is not None:
            points += min(2, float(item["rating"]) * 0.4)
        if item.get("reviews") is not None:
            points += min(0.75, math.log1p(max(0, float(item["reviews"]))) / 12)
        for preference_term in match_terms:
            if preference_term and preference_term in name:
                points += 5
        if low_budget and item.get("price_level") in price_rank:
            points += price_rank[item["price_level"]]
        if name and name in recent_text:
            points -= 5
        return points, -index

    return [item for _, item in sorted(enumerate(places), key=lambda pair: score(pair[1], pair[0]), reverse=True)]


def format_places_for_ai(places: list[dict[str, Any]]) -> str:
    if not places:
        return ""
    lines = ["Live nearby place results:"]
    for place in places:
        details = [
            place.get("name") or "Unnamed place",
            place.get("address") or "address unavailable",
        ]
        if place.get("rating") is not None:
            details.append(f"rating {place['rating']} ({place.get('reviews', 0)} reviews)")
        if place.get("price_level"):
            details.append(str(place["price_level"]))
        if place.get("open_now") is not None:
            details.append("open now" if place["open_now"] else "currently closed")
        if place.get("opening_hours"):
            details.append("hours: " + "; ".join(str(item) for item in place["opening_hours"][:7]))
        if place.get("distance_meters") is not None:
            details.append(f"about {int(place['distance_meters'])} m away")
        if place.get("maps_url"):
            details.append(f"map: {place['maps_url']}")
        lines.append("- " + " | ".join(details))
    return "\n".join(lines)
