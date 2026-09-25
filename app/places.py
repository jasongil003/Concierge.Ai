import math
from typing import Any

import httpx

from .config import settings


PLACE_HINTS = {
    "restaurant", "restaurants", "eat", "food", "cafe", "coffee", "bar",
    "pharmacy", "mall", "shopping", "attraction", "nearby", "near me",
    "things to do", "activity", "activities", "plan", "visit", "tour",
}


class GooglePlaces:
    @staticmethod
    def should_search(message: str) -> bool:
        text = message.lower()
        return any(hint in text for hint in PLACE_HINTS)

    async def search(
        self,
        message: str,
        latitude: float | None,
        longitude: float | None,
        open_now: bool = True,
    ) -> list[dict[str, Any]]:
        if (
            not settings.google_places_api_key
            or latitude is None
            or longitude is None
            or not self.should_search(message)
        ):
            return []

        payload = {
            "textQuery": message,
            "pageSize": settings.places_max_results,
            "locationBias": {
                "circle": {
                    "center": {
                        "latitude": latitude,
                        "longitude": longitude,
                    },
                    "radius": settings.places_radius_meters,
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
                "places.currentOpeningHours.openNow,places.currentOpeningHours.weekdayDescriptions,places.googleMapsUri,places.location"
            ),
        }

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://places.googleapis.com/v1/places:searchText",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            body = response.json()

        results = []
        for place in body.get("places", []):
            point = place.get("location", {})
            distance_meters = None
            if isinstance(point, dict) and point.get("latitude") is not None and point.get("longitude") is not None:
                distance_meters = round(_distance_meters(latitude, longitude, float(point["latitude"]), float(point["longitude"])))
            results.append(
                {
                    "name": place.get("displayName", {}).get("text"),
                    "address": place.get("formattedAddress"),
                    "rating": place.get("rating"),
                    "reviews": place.get("userRatingCount"),
                    "price_level": place.get("priceLevel"),
                    "open_now": place.get("currentOpeningHours", {}).get("openNow"),
                    "opening_hours": place.get("currentOpeningHours", {}).get("weekdayDescriptions", [])[:7],
                    "distance_meters": distance_meters,
                    "maps_url": place.get("googleMapsUri"),
                }
            )
        return results


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
