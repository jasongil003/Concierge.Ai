"""Guest and small admin workload for capacity tests against a test property."""

from __future__ import annotations

import os
import uuid

from locust import HttpUser, between, task


PROPERTY_ID = os.getenv("PROPERTY_ID", "lunara-mnl-001")
ADMIN_USERNAME = os.getenv("LOADTEST_ADMIN_USERNAME", "")
ADMIN_PASSWORD = os.getenv("LOADTEST_ADMIN_PASSWORD", "")
ADMIN_ENABLED = bool(ADMIN_USERNAME and ADMIN_PASSWORD)


class GuestUser(HttpUser):
    weight = 99
    wait_time = between(0.4, 1.2)

    def on_start(self) -> None:
        self.client_id = "load-" + uuid.uuid4().hex
        self.session_id = ""
        self.service_id = ""
        self.service_submitted = False
        self._start_session()

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
        catalog = self.client.get(
            "/api/guest/service-catalog",
            params={"property_id": PROPERTY_ID},
            name="GET /api/guest/service-catalog",
        )
        services = catalog.json().get("services", []) if catalog.ok else []
        enabled = [item for item in services if item.get("enabled") and not item.get("archived")]
        if enabled:
            self.service_id = enabled[0].get("service_id", "")

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
            name="POST /api/session/resume",
        )
        self.client.get(
            f"/api/guest/conversations/{self.session_id}/staff-messages",
            name="GET /api/guest/conversations/{session_id}/staff-messages",
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
