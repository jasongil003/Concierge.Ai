"""Cross-instance provider limits backed by Redis rather than process memory."""

import asyncio
from dataclasses import replace
import os

import pytest
from redis.asyncio import Redis

from app.ai_providers import AIChatRequest, AIChatResponse, AIMessage, AIModelService, AIProviderStore, ProviderBulkheadFull
import app.ai_providers as ai_provider_module


REDIS_URL = os.getenv("REDIS_TEST_URL", "").strip()
pytestmark = pytest.mark.skipif(not REDIS_URL, reason="REDIS_TEST_URL is required for shared provider bulkhead integration.")


def test_two_service_instances_share_provider_concurrency_slots(tmp_path, monkeypatch):
    updated = replace(
        ai_provider_module.settings,
        ai_provider_concurrency_limit=1,
        ai_provider_concurrency_limits={"local": 1},
        ai_provider_queue_capacity=4,
        ai_provider_queue_wait_seconds=0.03,
        ai_provider_retry_attempts=0,
    )
    monkeypatch.setattr(ai_provider_module, "settings", updated)
    redis_key = "concierge:ai:bulkhead:local"
    first = AIModelService(AIProviderStore(tmp_path / "first.db"))
    second = AIModelService(AIProviderStore(tmp_path / "second.db"))

    class SlowAdapter:
        async def send_message(self, _request, _credential):
            await asyncio.sleep(0.12)
            return AIChatResponse("safe mocked response", "local", "mock", 1, 1)

    request = AIChatRequest("hotel-a", "local", "mock", [AIMessage("user", "hello")], timeout_seconds=1)
    async def run():
        first_redis = Redis.from_url(REDIS_URL, decode_responses=False, socket_connect_timeout=1, socket_timeout=1)
        second_redis = Redis.from_url(REDIS_URL, decode_responses=False, socket_connect_timeout=1, socket_timeout=1)
        first.set_distributed_redis(first_redis)
        second.set_distributed_redis(second_redis)
        try:
            await first_redis.delete(redis_key)
            outcomes = await asyncio.gather(
                first._send_with_resilience("local", SlowAdapter(), request, {}),
                second._send_with_resilience("local", SlowAdapter(), request, {}),
                return_exceptions=True,
            )
            return outcomes
        finally:
            await first_redis.delete(redis_key)
            await first_redis.aclose()
            await second_redis.aclose()

    outcomes = asyncio.run(run())
    assert sum(isinstance(item, AIChatResponse) for item in outcomes) == 1
    assert sum(isinstance(item, ProviderBulkheadFull) for item in outcomes) == 1
