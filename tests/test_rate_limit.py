from pathlib import Path

from app.guardrails import SQLiteRateLimiter


def test_rate_limit_survives_backend_instance_recreation(tmp_path: Path):
    path = tmp_path / "limits.db"
    first_worker = SQLiteRateLimiter(path)
    second_worker = SQLiteRateLimiter(path)
    assert first_worker.allow("hotel-a:guest-chat:session-1", 2, 60) is True
    assert second_worker.allow("hotel-a:guest-chat:session-1", 2, 60) is True
    assert SQLiteRateLimiter(path).allow("hotel-a:guest-chat:session-1", 2, 60) is False
    assert SQLiteRateLimiter(path).allow("hotel-b:guest-chat:session-1", 2, 60) is True
