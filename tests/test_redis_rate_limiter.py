import asyncio
import os
import time
from collections import defaultdict

import pytest
from redis.asyncio import Redis

from app.guardrails import RateLimitUnavailable, RedisRateLimiter


class AtomicRedisStub:
    def __init__(self):
        self.counts = defaultdict(int)
        self.ttls = {}
        self.lock = asyncio.Lock()

    async def eval(self, _script, key_count, key, ttl_ms):
        assert key_count == 1
        async with self.lock:
            self.counts[key] += 1
            self.ttls.setdefault(key, int(ttl_ms))
            return self.counts[key]

    async def ping(self):
        return True

    async def aclose(self):
        return None


def test_multiple_limiter_instances_share_atomic_window_and_bounded_keys():
    async def run():
        backend = AtomicRedisStub()
        first = RedisRateLimiter("redis://unused", client=backend)
        second = RedisRateLimiter("redis://unused", client=backend)
        results = await asyncio.gather(*(
            (first if index % 2 else second).allow("session:property-a:secret-session", 17, 30)
            for index in range(60)
        ))
        assert sum(results) == 17
        key = next(iter(backend.counts))
        assert key.startswith("concierge:rate:")
        assert "secret-session" not in key
        assert backend.ttls[key] == 30_000
        assert await first.ping()

    asyncio.run(run())


def test_redis_failure_is_explicit_and_fails_closed():
    class BrokenRedis(AtomicRedisStub):
        async def eval(self, *_args):
            raise ConnectionError("private redis address must not escape")

    async def run():
        limiter = RedisRateLimiter("redis://unused", client=BrokenRedis())
        with pytest.raises(RateLimitUnavailable, match="temporarily unavailable") as error:
            await limiter.allow("password-reset:ip:192.0.2.1", 3, 60)
        assert "private redis address" not in str(error.value)

    asyncio.run(run())


def test_real_redis_instances_share_atomic_limits_when_configured():
    url = os.getenv("REDIS_TEST_URL", "").strip()
    if not url:
        pytest.skip("Set REDIS_TEST_URL to run the Redis service integration test.")

    async def run():
        client_a = Redis.from_url(url, decode_responses=False, socket_connect_timeout=1, socket_timeout=1)
        client_b = Redis.from_url(url, decode_responses=False, socket_connect_timeout=1, socket_timeout=1)
        limit_key = f"integration:{time.time_ns()}"
        first = RedisRateLimiter(url, client=client_a)
        second = RedisRateLimiter(url, client=client_b)
        redis_key = first._redis_key(limit_key)
        try:
            results = await asyncio.gather(*(
                (first if index % 2 else second).allow(limit_key, 23, 45)
                for index in range(100)
            ))
            assert sum(results) == 23
            ttl = await client_a.pttl(redis_key)
            assert 0 < ttl <= 45_000
        finally:
            await client_a.delete(redis_key)
            await client_a.aclose()
            await client_b.aclose()

    asyncio.run(run())
