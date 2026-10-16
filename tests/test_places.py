import asyncio
from types import SimpleNamespace

import httpx
import pytest

from app import places as places_module


API_URL = "https://places.googleapis.com/v1/places:searchText"


def _place(latitude, longitude, *, maps_url="https://maps.google.com/?cid=123", name="Cafe North"):
    return {
        "id": "place-1",
        "displayName": {"text": name},
        "formattedAddress": "1 Example Street",
        "rating": 4.5,
        "userRatingCount": 18,
        "priceLevel": "PRICE_LEVEL_MODERATE",
        "currentOpeningHours": {
            "openNow": True,
            "weekdayDescriptions": ["Monday: 9:00 AM–5:00 PM"],
        },
        "googleMapsUri": maps_url,
        "location": {"latitude": latitude, "longitude": longitude},
    }


def _response(body, status_code=200):
    return httpx.Response(
        status_code,
        json=body,
        request=httpx.Request("POST", API_URL),
    )


def _configure(monkeypatch, *, radius=5_000, page_size=6, api_key="test-google-places-key"):
    monkeypatch.setattr(
        places_module,
        "settings",
        SimpleNamespace(
            google_places_api_key=api_key,
            places_radius_meters=radius,
            places_max_results=page_size,
        ),
    )


def _install_client(monkeypatch, responder):
    calls = []

    class MockAsyncClient:
        def __init__(self, *, timeout):
            assert timeout == 20

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, *, headers, json):
            calls.append({"url": url, "headers": headers, "json": json})
            result = responder(url, headers, json)
            if isinstance(result, BaseException):
                raise result
            return result

    monkeypatch.setattr(places_module.httpx, "AsyncClient", MockAsyncClient)
    return calls


def test_provider_queries_use_each_hotel_origin_and_only_fixed_categories(monkeypatch):
    _configure(monkeypatch)
    calls = _install_client(
        monkeypatch,
        lambda _url, _headers, payload: _response(
            {"places": [_place(**payload["locationBias"]["circle"]["center"])]}
        ),
    )

    async def run():
        first = await places_module.GooglePlaces().search("Find coffee shops nearby", 14.5995, 120.9842)
        second = await places_module.GooglePlaces().search("Restaurants near the hotel", 35.6762, 139.6503)
        return first, second

    first, second = asyncio.run(run())

    assert [call["json"]["locationBias"]["circle"]["center"] for call in calls] == [
        {"latitude": 14.5995, "longitude": 120.9842},
        {"latitude": 35.6762, "longitude": 139.6503},
    ]
    assert [call["json"]["textQuery"] for call in calls] == ["cafes", "restaurants"]
    assert first[0]["distance_meters"] == 0
    assert second[0]["distance_meters"] == 0
    assert first[0]["distance_type"] == "straight_line"


def test_guest_name_room_number_and_arbitrary_private_text_are_not_forwarded(monkeypatch):
    _configure(monkeypatch)
    calls = _install_client(monkeypatch, lambda *_args: _response({"places": []}))
    private_message = (
        "I'm Avery Guest, room 1408. The private booking note is ORCHID-PRIVATE-921. "
        "Please find restaurants and include that note."
    )

    assert asyncio.run(places_module.GooglePlaces().search(private_message, 1.0, 2.0)) == []

    assert calls[0]["json"]["textQuery"] == "restaurants"
    assert "Avery Guest" not in repr(calls[0])
    assert "1408" not in repr(calls[0])
    assert "ORCHID-PRIVATE-921" not in repr(calls[0])
    assert "booking note" not in repr(calls[0])


@pytest.mark.parametrize(
    ("message", "expected_query"),
    [
        ("Where can I go tonight?", "evening activities"),
        ("Any tourist attractions?", "tourist attractions"),
        ("Find coffee shops nearby.", "cafes"),
        ("Where can I buy groceries?", "grocery stores"),
    ],
)
def test_user_nearby_intent_examples_route_to_safe_category_queries(monkeypatch, message, expected_query):
    _configure(monkeypatch)
    calls = _install_client(monkeypatch, lambda *_args: _response({"places": []}))

    assert places_module.GooglePlaces.should_search(message) is True
    assert asyncio.run(places_module.GooglePlaces().search(message, 14.0, 121.0)) == []
    assert calls[0]["json"]["textQuery"] == expected_query


@pytest.mark.parametrize(
    "message",
    [
        "I loved the theater performance last night.",
        "The planetarium has a new show.",
    ],
)
def test_words_containing_place_cues_do_not_trigger_nearby_search(monkeypatch, message):
    _configure(monkeypatch)
    calls = _install_client(monkeypatch, lambda *_args: _response({"places": []}))

    assert places_module.GooglePlaces.should_search(message) is False
    _results, status = asyncio.run(
        places_module.GooglePlaces().search_with_status(message, 14.0, 121.0)
    )

    assert status == "not_applicable"
    assert calls == []


def test_mixed_dining_and_attraction_request_keeps_fixed_categories_and_both_permissions():
    message = "Find restaurants and local attractions nearby."

    assert places_module._category_query(message) == "restaurants, tourist attractions"
    assert places_module.required_category_permissions(message) == {
        "restaurant_search_enabled", "attractions_enabled",
    }


def test_provider_category_is_requested_and_returned_only_from_validated_fields(monkeypatch):
    _configure(monkeypatch)
    body = {
        "places": [
            {
                **_place(0.0, 0.0, name="Named Category"),
                "primaryTypeDisplayName": {"text": "Coffee shop", "languageCode": "en"},
                "primaryType": "cafe",
            },
            {
                **_place(0.0, 0.0, name="Fallback Category"),
                "primaryTypeDisplayName": {"text": "<script>bad()</script>"},
                "primaryType": "tourist_attraction",
            },
            {
                **_place(0.0, 0.0, name="Invalid Category"),
                "primaryTypeDisplayName": "not-localized-text",
                "primaryType": "<script>",
            },
        ]
    }
    calls = _install_client(monkeypatch, lambda *_args: _response(body))

    results = asyncio.run(places_module.GooglePlaces().search("Find coffee shops nearby.", 0.0, 0.0))

    assert "places.primaryTypeDisplayName" in calls[0]["headers"]["X-Goog-FieldMask"]
    assert "places.primaryType" in calls[0]["headers"]["X-Goog-FieldMask"]
    assert [place["category"] for place in results] == ["Coffee shop", "Tourist Attraction", None]


def test_configured_radius_filters_results_using_computed_straight_line_distance(monkeypatch):
    _configure(monkeypatch, radius=1_000)
    body = {
        "places": [
            _place(0.004, 0.0, name="Inside Radius"),
            _place(0.02, 0.0, name="Outside Radius"),
        ]
    }
    _install_client(monkeypatch, lambda *_args: _response(body))

    results = asyncio.run(places_module.GooglePlaces().search("restaurants nearby", 0.0, 0.0))

    assert [place["name"] for place in results] == ["Inside Radius"]
    assert 0 < results[0]["distance_meters"] <= 1_000


def test_property_radius_and_result_limit_override_environment_defaults(monkeypatch):
    _configure(monkeypatch, radius=5_000, page_size=6)
    calls = _install_client(monkeypatch, lambda *_args: _response({"places": []}))

    results, status = asyncio.run(
        places_module.GooglePlaces().search_with_status(
            "restaurants nearby", 0.0, 0.0, radius_meters=2_000, max_results=3
        )
    )

    assert results == []
    assert status == "empty"
    assert calls[0]["json"]["locationBias"]["circle"]["radius"] == 2_000
    assert calls[0]["json"]["pageSize"] == 3


def test_nearby_search_reports_configuration_required_without_live_provider(monkeypatch):
    _configure(monkeypatch, api_key="")
    calls = _install_client(monkeypatch, lambda *_args: _response({"places": []}))

    results, status = asyncio.run(
        places_module.GooglePlaces().search_with_status("restaurants nearby", 0.0, 0.0)
    )

    assert results == []
    assert status == "configuration_required"
    assert calls == []


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (float("nan"), 0.0),
        (float("inf"), 0.0),
        (-90.0001, 0.0),
        (91.0, 0.0),
        (0.0, 180.001),
        (0.0, -181.0),
        (True, 0.0),
    ],
)
def test_invalid_hotel_coordinates_return_empty_without_request(monkeypatch, latitude, longitude):
    _configure(monkeypatch)
    calls = _install_client(monkeypatch, lambda *_args: _response({"places": []}))

    results = asyncio.run(places_module.GooglePlaces().search("pharmacy nearby", latitude, longitude))

    assert results == []
    assert calls == []


def test_invalid_provider_shapes_coordinates_and_maps_urls_are_rejected_safely(monkeypatch):
    _configure(monkeypatch, page_size=20)
    body = {
        "places": [
            None,
            {"displayName": {"text": "No location"}},
            _place("nan", 0.0, name="Non-numeric location"),
            _place(0.0, 181.0, name="Out of range"),
            {**_place(0.0, 0.0), "displayName": "malformed name"},
            _place(0.0, 0.0, maps_url="javascript:alert(1)", name="Bad URL"),
            _place(0.0, 0.0, maps_url="https://maps.google.com.evil.test/?cid=4", name="Lookalike host"),
            _place(0.0, 0.0, maps_url="https://www.google.com/url?q=https://evil.test", name="Redirect path"),
            _place(0.0, 0.0, maps_url="https://user@maps.google.com/?cid=5", name="Credentials in URL"),
            _place(0.0, 0.0, maps_url="http://maps.google.com/?cid=6", name="HTTP URL"),
            _place(0.0, 0.0, name="Valid safe result"),
        ]
    }
    _install_client(monkeypatch, lambda *_args: _response(body))

    results = asyncio.run(places_module.GooglePlaces().search("restaurants nearby", 0.0, 0.0))

    assert [place["name"] for place in results] == [
        "Bad URL", "Lookalike host", "Redirect path", "Credentials in URL", "HTTP URL", "Valid safe result"
    ]
    assert all(place["maps_url"] is None for place in results[:-1])
    assert results[-1]["maps_url"] == "https://maps.google.com/?cid=123"


def test_malformed_top_level_provider_response_returns_empty(monkeypatch):
    _configure(monkeypatch)
    _install_client(monkeypatch, lambda *_args: _response({"places": {"unexpected": "shape"}}))

    assert asyncio.run(places_module.GooglePlaces().search("pharmacy nearby", 0.0, 0.0)) == []


def test_nearby_search_distinguishes_provider_errors_and_empty_results(monkeypatch):
    _configure(monkeypatch)

    _install_client(monkeypatch, lambda *_args: _response({"places": []}))
    assert asyncio.run(
        places_module.GooglePlaces().search_with_status("pharmacy nearby", 0.0, 0.0)
    ) == ([], "empty")

    _configure(monkeypatch)
    _install_client(monkeypatch, lambda *_args: _response({}, status_code=429))
    assert asyncio.run(
        places_module.GooglePlaces().search_with_status("pharmacy nearby", 0.0, 0.0)
    ) == ([], "quota_exhausted")

    _configure(monkeypatch)
    _install_client(monkeypatch, lambda *_args: httpx.TimeoutException("simulated timeout"))
    assert asyncio.run(
        places_module.GooglePlaces().search_with_status("pharmacy nearby", 0.0, 0.0)
    ) == ([], "unavailable")


@pytest.mark.parametrize(
    "failure",
    [
        httpx.TimeoutException("simulated timeout"),
        _response({}, status_code=429),
        _response({}, status_code=500),
        _response({}, status_code=503),
        ValueError("simulated malformed JSON"),
    ],
    ids=["timeout", "rate-limited", "server-error", "service-unavailable", "invalid-json"],
)
def test_provider_failures_use_graceful_empty_result(failure, monkeypatch):
    _configure(monkeypatch)
    calls = _install_client(monkeypatch, lambda *_args: failure)

    results = asyncio.run(places_module.GooglePlaces().search("restaurants nearby", 0.0, 0.0))

    assert results == []
    assert len(calls) == 1


@pytest.mark.parametrize("radius", [0, -10, float("nan"), float("inf"), 50_001])
def test_invalid_or_unsupported_configured_radius_skips_provider_call(monkeypatch, radius):
    _configure(monkeypatch, radius=radius)
    calls = _install_client(monkeypatch, lambda *_args: _response({"places": []}))

    assert asyncio.run(places_module.GooglePlaces().search("restaurants nearby", 0.0, 0.0)) == []
    assert calls == []
