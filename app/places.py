from typing import Any

import httpx

from .config import settings


PLACE_HINTS = {
    "restaurant", "restaurants", "eat", "food", "cafe", "coffee", "bar",
    "pharmacy", "mall", "shopping", "attraction", "nearby", "near me",
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
            "openNow": True,
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
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": settings.google_places_api_key,
            "X-Goog-FieldMask": (
                "places.id,places.displayName,places.formattedAddress,"
                "places.rating,places.userRatingCount,places.priceLevel,"
                "places.currentOpeningHours,places.googleMapsUri"
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
            results.append(
                {
                    "name": place.get("displayName", {}).get("text"),
                    "address": place.get("formattedAddress"),
                    "rating": place.get("rating"),
                    "reviews": place.get("userRatingCount"),
                    "price_level": place.get("priceLevel"),
                    "open_now": place.get("currentOpeningHours", {}).get("openNow"),
                    "maps_url": place.get("googleMapsUri"),
                }
            )
        return results


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
        if place.get("maps_url"):
            details.append(f"map: {place['maps_url']}")
        lines.append("- " + " | ".join(details))
    return "\n".join(lines)
