"""Guest and small admin workload for capacity tests against a test property."""

from __future__ import annotations

import os
import uuid
import json
from pathlib import Path

from locust import HttpUser, LoadTestShape, between, task


PROPERTY_ID = os.getenv("PROPERTY_ID", "load-test-property")
ADMIN_USERNAME = os.getenv("LOADTEST_ADMIN_USERNAME", "")
ADMIN_PASSWORD = os.getenv("LOADTEST_ADMIN_PASSWORD", "")
ADMIN_ENABLED = bool(ADMIN_USERNAME and ADMIN_PASSWORD)
STAFF_CONVERSATION_FLOW_ENABLED = os.getenv("LOADTEST_STAFF_CONVERSATION_FLOW", "").strip().lower() in {"1", "true", "yes"}


SHAPE_NAME = os.getenv("LOADTEST_SHAPE", "").strip()
if SHAPE_NAME:
    _profiles = json.loads((Path(__file__).with_name("profiles.json")).read_text(encoding="utf-8"))
    _profile = next(
        (
            item for item in _profiles["high_scale_profiles"]
            if item["name"] == SHAPE_NAME
        ),
        _profiles["spike_profile"] if _profiles["spike_profile"]["name"] == SHAPE_NAME else None,
    )
    if _profile is None and _profiles["soak_profile"]["name"] == SHAPE_NAME:
        _profile = _profiles["soak_profile"]
    if _profile is None:
        raise RuntimeError(f"Unknown load-test shape: {SHAPE_NAME}")

    class SelectedCapacityShape(LoadTestShape):
        """Apply a named high-scale, spike, or soak profile from profiles.json."""

        def tick(self):
            elapsed = self.get_run_time()
            if SHAPE_NAME == _profiles["spike_profile"]["name"]:
                profile = _profiles["spike_profile"]
                warmup = int(profile["warmup_duration_seconds"])
                if elapsed < warmup:
                    return int(profile["warmup_users"]), int(profile["warmup_spawn_rate_per_second"])
                if elapsed < warmup + int(profile["hold_duration_seconds"]):
                    return int(profile["users"]), int(profile["spawn_rate_per_second"])
                return None
            if elapsed < _duration_seconds(_profile["duration"]):
                return int(_profile["users"]), int(_profile["spawn_rate_per_second"])
            return None


def _duration_seconds(value: str) -> int:
    amount = int(value[:-1])
    unit = value[-1].casefold()
    return amount * {"s": 1, "m": 60, "h": 3600}[unit]


class GuestUser(HttpUser):
    weight = 99
    wait_time = between(0.4, 1.2)

    def on_start(self) -> None:
        self.client_id = "load-" + uuid.uuid4().hex
        self.session_id = ""
        self.session_headers = {}
        self.service_id = ""
        self.service_submitted = False
        self.restaurant_id = ""
        self.staff_conversation_active = False
        self._start_session()
        if STAFF_CONVERSATION_FLOW_ENABLED and self.session_id:
            self._start_staff_conversation_flow()

    def _start_session(self) -> None:
        with self.client.post(
            "/api/session/start",
            json={"client_id": self.client_id, "property_id": PROPERTY_ID},
            name="POST /api/session/start",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"session creation returned {response.status_code}")
                return
            self.session_id = response.json().get("session_id", "")
            if not self.session_id:
                response.failure("session creation returned no session_id")
                return
            self.session_headers = {"X-Concierge-Session": self.session_id}
        catalog = self.client.get(
            "/api/guest/service-catalog",
            params={"property_id": PROPERTY_ID},
            name="GET /api/guest/service-catalog",
        )
        services = catalog.json().get("services", []) if catalog.ok else []
        enabled = [item for item in services if item.get("enabled") and not item.get("archived")]
        if enabled:
            self.service_id = enabled[0].get("service_id", "")
        if STAFF_CONVERSATION_FLOW_ENABLED:
            facilities = self.client.get(
                "/api/guest/facilities",
                params={"property_id": PROPERTY_ID},
                name="GET /api/guest/facilities [staff-flow setup]",
            )
            restaurants = facilities.json().get("restaurants", []) if facilities.ok else []
            available = [item for item in restaurants if item.get("restaurant_id")]
            if available:
                self.restaurant_id = available[0]["restaurant_id"]

    def _read_staff_messages(self, expected_status: int, *, name: str) -> None:
        with self.client.get(
            f"/api/guest/conversations/{self.session_id}/staff-messages",
            headers=self.session_headers,
            name=name,
            catch_response=True,
        ) as response:
            if expected_status == 404 and response.status_code == 404:
                try:
                    body = response.json()
                    detail = body.get("detail") if isinstance(body, dict) else None
                except ValueError:
                    detail = None
                if detail == "Staff conversation not found.":
                    response.success()
                else:
                    response.failure("unexpected staff conversation 404")
            elif expected_status == 200 and response.status_code == 200:
                try:
                    body = response.json()
                    messages = body.get("messages") if isinstance(body, dict) else None
                except ValueError:
                    messages = None
                if isinstance(messages, list):
                    response.success()
                else:
                    response.failure("active staff conversation returned an invalid message list")
            else:
                response.failure(f"staff messages returned {response.status_code}, expected {expected_status}")

    def _start_staff_conversation_flow(self) -> None:
        # Record the valid no-conversation case before this virtual guest
        # creates its active restaurant conversation.
        self._read_staff_messages(
            404,
            name="GET /api/guest/conversations/{session_id}/staff-messages [no staff conversation]",
        )
        if not self.restaurant_id:
            return
        with self.client.post(
            f"/api/guest/conversations/{self.session_id}/escalate",
            json={"restaurant_id": self.restaurant_id, "reason": "Load-test guest requests restaurant staff."},
            headers=self.session_headers,
            name="POST /api/guest/conversations/{session_id}/escalate [guest escalation]",
            catch_response=True,
        ) as response:
            try:
                body = response.json()
                state = body.get("status") if isinstance(body, dict) else None
            except ValueError:
                state = None
            if response.status_code == 200 and state in {"waiting_for_staff", "assigned"}:
                response.success()
                self.staff_conversation_active = True
            else:
                response.failure(f"guest escalation returned {response.status_code}")
        if self.staff_conversation_active:
            self._read_staff_messages(
                200,
                name="GET /api/guest/conversations/{session_id}/staff-messages [active staff conversation]",
            )

    @task(10)
    def hotel_information(self) -> None:
        self.client.get("/api/hotel", name="GET /api/hotel")

    @task(4)
    def zones_and_facilities(self) -> None:
        self.client.get("/api/guest/zones", params={"property_id": PROPERTY_ID}, name="GET /api/guest/zones")
        self.client.get("/api/guest/facilities", params={"property_id": PROPERTY_ID}, name="GET /api/guest/facilities")

    @task(3)
    def menu_catalog_and_recommendations(self) -> None:
        self.client.get("/api/guest/service-catalog", params={"property_id": PROPERTY_ID}, name="GET /api/guest/service-catalog")
        self.client.get("/api/guest/recommendations", params={"property_id": PROPERTY_ID}, name="GET /api/guest/recommendations")

    @task(2)
    def resume_and_conversation_state(self) -> None:
        if not self.session_id:
            self._start_session()
            return
        self.client.post(
            "/api/session/resume",
            json={"client_id": self.client_id, "session_id": self.session_id},
            headers=self.session_headers,
            name="POST /api/session/resume",
        )

    @task(1)
    def poll_active_staff_conversation(self) -> None:
        if STAFF_CONVERSATION_FLOW_ENABLED and self.staff_conversation_active:
            self._read_staff_messages(
                200,
                name="GET /api/guest/conversations/{session_id}/staff-messages [active staff conversation]",
            )

    @task(2)
    def deterministic_ai_chat_and_knowledge_retrieval(self) -> None:
        if not self.session_id:
            return
        self.client.post(
            "/api/chat",
            json={
                "session_id": self.session_id,
                "message": "Compare the quiet guest areas and suggest a calm place to spend an afternoon.",
                "mode": "advanced",
            },
            headers=self.session_headers,
            name="POST /api/chat [deterministic provider]",
        )

    @task(1)
    def create_idempotent_service_request_once(self) -> None:
        if not self.session_id or not self.service_id or self.service_submitted:
            return
        with self.client.post(
            "/api/guest/service-requests",
            json={
                "session_id": self.session_id,
                "service_id": self.service_id,
                "description": "Load-test request; one stable idempotency key per virtual guest.",
                "client_request_id": f"load-{self.client_id}",
                "confirmed": True,
            },
            headers=self.session_headers,
            name="POST /api/guest/service-requests",
            catch_response=True,
        ) as response:
            if response.status_code in {200, 201}:
                self.service_submitted = True
            else:
                response.failure(f"service request returned {response.status_code}")


class AdminReadWriteUser(HttpUser):
    """One optional operator models occasional authenticated read/write traffic."""

    weight = 1 if ADMIN_ENABLED else 0
    fixed_count = 1 if ADMIN_ENABLED else 0
    wait_time = between(3, 7)

    def on_start(self) -> None:
        self.property_id = PROPERTY_ID
        response = self.client.post(
            "/api/admin/auth/login",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD, "remember_me": False},
            name="POST /api/admin/auth/login",
        )
        self.csrf_token = response.json().get("user", {}).get("csrf_token", "") if response.ok else ""
        if not self.csrf_token:
            self.environment.runner.quit()

    @task(8)
    def read_dashboard_and_restaurants(self) -> None:
        self.client.get(f"/api/admin/properties/{self.property_id}/dashboard", name="GET /api/admin/properties/{property_id}/dashboard")
        restaurants = self.client.get(
            f"/api/admin/properties/{self.property_id}/restaurants",
            name="GET /api/admin/properties/{property_id}/restaurants",
        )
        items = restaurants.json().get("restaurants", []) if restaurants.ok else []
        if items:
            restaurant_id = items[0].get("restaurant_id", "")
            if restaurant_id:
                self.client.get(
                    f"/api/admin/properties/{self.property_id}/restaurants/{restaurant_id}/menus",
                    name="GET /api/admin/properties/{property_id}/restaurants/{restaurant_id}/menus",
                )

    @task(1)
    def limited_reversible_admin_write(self) -> None:
        if not self.csrf_token:
            return
        self.client.put(
            f"/api/admin/properties/{self.property_id}/conversations/retention",
            headers={"X-CSRF-Token": self.csrf_token},
            json={"retention_days": 30},
            name="PUT /api/admin/properties/{property_id}/conversations/retention",
        )
