import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.ai_providers import AIChatResponse, AIModelService, AIProviderStore
from app.improvement_loop import (
    ImprovementLoopManager,
    ImprovementLoopStore,
    build_iteration_messages,
    parse_iteration_response,
)
from app.main import app


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    return tmp_path / "test_loop.db"


@pytest.fixture
def loop_store(temp_db: Path) -> ImprovementLoopStore:
    return ImprovementLoopStore(temp_db)


@pytest.fixture
def ai_service(temp_db: Path) -> AIModelService:
    provider_store = AIProviderStore(temp_db)
    return AIModelService(provider_store)


def test_store_initialization_and_defaults(loop_store: ImprovementLoopStore):
    loop = loop_store.get("prop-1")
    assert loop["property_id"] == "prop-1"
    assert loop["status"] == "draft"
    assert loop["provider_id"] == "local"
    assert loop["approval_mode"] == "manual"
    assert loop["iteration_count"] == 0
    assert loop["consecutive_failures"] == 0


def test_save_config_and_validation(loop_store: ImprovementLoopStore):
    updated = loop_store.save_config(
        "prop-1",
        {
            "objective": "Improve spa FAQ accuracy",
            "satisfaction_criteria": "All hours and pricing verified",
            "evidence": "Audit findings from guest questions",
            "provider_id": "local",
            "model": "qwen3:8b",
            "approval_mode": "manual",
            "interval_seconds": 120,
            "max_iterations": 10,
            "max_consecutive_failures": 3,
        },
    )
    assert updated["objective"] == "Improve spa FAQ accuracy"
    assert updated["model"] == "qwen3:8b"
    assert updated["interval_seconds"] == 120
    assert updated["max_iterations"] == 10

    # Test invalid interval
    with pytest.raises(ValueError, match="between 5 seconds and 24 hours"):
        loop_store.save_config("prop-1", {"interval_seconds": 2})

    # Test invalid approval mode
    with pytest.raises(ValueError, match="Approval mode must be manual or continuous"):
        loop_store.save_config("prop-1", {"approval_mode": "invalid_mode"})

    # Test unavailable provider
    with pytest.raises(ValueError, match="Choose an available AI provider"):
        loop_store.save_config("prop-1", {"provider_id": "copilot"})


def test_validate_ready(loop_store: ImprovementLoopStore):
    with pytest.raises(ValueError, match="Add a loop objective"):
        loop_store.validate_ready("prop-2")

    loop_store.save_config("prop-2", {"objective": "Fix dining hours"})
    with pytest.raises(ValueError, match="Add satisfaction criteria"):
        loop_store.validate_ready("prop-2")

    loop_store.save_config("prop-2", {"satisfaction_criteria": "100% verified"})
    with pytest.raises(ValueError, match="Choose a model"):
        loop_store.validate_ready("prop-2")

    loop_store.save_config("prop-2", {"model": "qwen3:8b"})
    ready = loop_store.validate_ready("prop-2")
    assert ready["objective"] == "Fix dining hours"


def test_direct_connection_requires_enabled_provider(ai_service: AIModelService):
    with pytest.raises(RuntimeError, match="Enable Google Gemini"):
        ai_service.validate_direct_connection("prop-disabled", "gemini", "gemini-2.5-flash")


def test_iteration_lifecycle(loop_store: ImprovementLoopStore):
    loop_store.save_config(
        "prop-3",
        {
            "objective": "Ensure Wi-Fi setup instructions are clear",
            "satisfaction_criteria": "Zero unresolved portal questions",
            "model": "qwen3:8b",
        },
    )

    iter_info = loop_store.start_iteration("prop-3")
    assert iter_info["iteration_number"] == 1
    assert iter_info["status"] == "draft"

    completed = loop_store.complete_iteration(
        "prop-3",
        iter_info["iteration_id"],
        {
            "summary": "Step-by-step guest login instructions verified.",
            "score": 90,
            "satisfied": True,
            "findings": ["Clarify iOS private MAC behavior"],
            "next_action": "Present to operator",
        },
        raw='{"summary": "Step-by-step guest login instructions verified.", "score": 90, "satisfied": true}',
    )
    assert completed["iteration_count"] == 1
    assert completed["consecutive_failures"] == 0

    iterations = loop_store.list_iterations("prop-3")
    assert len(iterations) == 1
    assert iterations[0]["score"] == 90
    assert iterations[0]["model_recommends_satisfied"] is True

    context = loop_store.recent_context("prop-3")
    assert len(context) == 1
    assert context[0]["iteration_number"] == 1


def test_iteration_failure_threshold(loop_store: ImprovementLoopStore):
    loop_store.save_config(
        "prop-4",
        {
            "objective": "Review room service menu",
            "satisfaction_criteria": "All dietary tags present",
            "model": "qwen3:8b",
            "max_consecutive_failures": 2,
        },
    )

    iter1 = loop_store.start_iteration("prop-4")
    f1 = loop_store.fail_iteration("prop-4", iter1["iteration_id"], "Network timeout")
    assert f1["consecutive_failures"] == 1
    assert f1["status"] != "error"

    iter2 = loop_store.start_iteration("prop-4")
    f2 = loop_store.fail_iteration("prop-4", iter2["iteration_id"], "Endpoint unreachable")
    assert f2["consecutive_failures"] == 2
    assert f2["status"] == "error"
    assert "Endpoint unreachable" in f2["last_error"]


def test_cancellation_and_orphaned_cleanup(loop_store: ImprovementLoopStore):
    loop_store.save_config(
        "prop-5",
        {
            "objective": "Test cancellation",
            "satisfaction_criteria": "Clean cancel",
            "model": "qwen3:8b",
        },
    )

    it = loop_store.start_iteration("prop-5")
    loop_store.cancel_iteration("prop-5", it["iteration_id"], "Operator cancelled")
    history = loop_store.list_iterations("prop-5")
    assert history[0]["status"] == "cancelled"

    # Test orphan cleanup
    it2 = loop_store.start_iteration("prop-5")
    assert loop_store.list_iterations("prop-5")[0]["status"] == "running"
    cleaned = loop_store.cleanup_orphaned_iterations()
    assert cleaned >= 1
    assert loop_store.list_iterations("prop-5")[0]["status"] == "cancelled"


def test_decide_iteration(loop_store: ImprovementLoopStore):
    loop_store.save_config(
        "prop-6",
        {
            "objective": "Check event calendar accuracy",
            "satisfaction_criteria": "All dates valid",
            "model": "qwen3:8b",
        },
    )

    it = loop_store.start_iteration("prop-6")
    loop_store.complete_iteration("prop-6", it["iteration_id"], {"summary": "First draft"}, "{}")

    # Operator requests revision
    updated = loop_store.decide_iteration("prop-6", "revision_requested", "Please add holiday event times")
    assert updated["operator_feedback"] == "Please add holiday event times"
    assert updated["status"] == "running"

    latest = loop_store.list_iterations("prop-6")[0]
    assert latest["operator_decision"] == "revision_requested"
    assert latest["operator_feedback"] == "Please add holiday event times"


def test_parse_iteration_response():
    # 1. Clean JSON
    res1 = parse_iteration_response('{"summary": "All good", "score": 95, "satisfied": true}')
    assert res1["summary"] == "All good"
    assert res1["score"] == 95
    assert res1["satisfied"] is True

    # 2. Markdown fenced code block
    res2 = parse_iteration_response('```json\n{"summary": "Fenced json", "score": 80, "satisfied": false}\n```')
    assert res2["summary"] == "Fenced json"
    assert res2["score"] == 80

    # 3. Preamble and postscript text with embedded JSON
    res3 = parse_iteration_response(
        'Here is my assessment:\n{"summary": "Embedded json", "score": 85, "satisfied": true}\nHope this helps!'
    )
    assert res3["summary"] == "Embedded json"
    assert res3["score"] == 85
    assert res3["satisfied"] is True

    # 4. Unstructured / malformed fallback
    res4 = parse_iteration_response("I could not generate valid JSON.")
    assert "I could not generate valid JSON." in res4["summary"]
    assert res4["satisfied"] is False


def test_build_iteration_messages():
    loop = {
        "objective": "Polish reception answers",
        "satisfaction_criteria": "Accurate check-in times",
        "evidence": "Front desk notes",
        "operator_feedback": "Emphasize keycard pickup location",
        "iteration_count": 2,
    }
    history = [
        {
            "iteration_number": 1,
            "status": "completed",
            "summary": "Initial draft review",
            "score": 75,
            "operator_decision": "revision_requested",
            "operator_feedback": "Check-in time is 3 PM",
        }
    ]
    messages = build_iteration_messages(loop, history)
    assert len(messages) == 2
    assert messages[0].role == "system"
    assert "independent quality reviewer" in messages[0].content
    assert messages[1].role == "user"

    user_payload = json.loads(messages[1].content)
    assert user_payload["objective"] == "Polish reception answers"
    assert len(user_payload["previous_iterations"]) == 1
    assert user_payload["previous_iterations"][0]["score"] == 75


@pytest.mark.anyio
async def test_manager_run_single(temp_db: Path, loop_store: ImprovementLoopStore, ai_service: AIModelService):
    manager = ImprovementLoopManager(loop_store, ai_service)

    loop_store.save_config(
        "tenant-a",
        {
            "objective": "Verify concierge pool hours",
            "satisfaction_criteria": "Correct summer hours documented",
            "model": "qwen3:8b",
            "provider_id": "local",
        },
    )

    # Mock direct_chat on ai_service
    ai_service.direct_chat = AsyncMock(
        return_value=AIChatResponse(
            text='{"summary": "Pool hours confirmed: 7 AM - 9 PM daily.", "score": 98, "satisfied": true, "findings": []}',
            provider="local",
            model="qwen3:8b",
        )
    )

    result = await manager.run_single("tenant-a")
    assert result["loop"]["iteration_count"] == 1
    assert len(result["iterations"]) == 1
    assert result["iterations"][0]["score"] == 98
    assert result["iterations"][0]["model_recommends_satisfied"] is True


def test_api_improvement_loop_endpoints(temp_db: Path, monkeypatch: pytest.MonkeyPatch, admin_client: TestClient):
    isolated_store = ImprovementLoopStore(temp_db)
    isolated_ai = AIModelService(AIProviderStore(temp_db))
    isolated_manager = ImprovementLoopManager(isolated_store, isolated_ai)
    monkeypatch.setattr(main_module, "improvement_loop_store", isolated_store)
    monkeypatch.setattr(main_module, "improvement_loops", isolated_manager)

    client = admin_client
    property_id = "test-property"
    loop_base = f"/api/admin/properties/{{property_id}}/improvement-loop"
    paths = app.openapi()["paths"]
    for action in ("start", "resume", "pause", "stop", "satisfied", "run-next", "decision"):
        assert f"{loop_base}/{action}" in paths

    # 1. Get snapshot
    get_res = client.get(f"/api/admin/properties/{property_id}/improvement-loop")
    assert get_res.status_code == 200
    assert "loop" in get_res.json()
    assert "iterations" in get_res.json()

    # 2. Put config
    put_res = client.put(
        f"/api/admin/properties/{property_id}/improvement-loop",
        json={
            "objective": "Ensure late checkout policy is consistent",
            "satisfaction_criteria": "PMS fees and cutoff times match",
            "evidence": "Housekeeping manager report",
            "provider_id": "local",
            "model": "qwen3:8b",
            "approval_mode": "manual",
            "interval_seconds": 60,
            "max_iterations": 5,
            "max_consecutive_failures": 3,
        },
    )
    assert put_res.status_code == 200
    loop_data = put_res.json()["loop"]
    assert loop_data["objective"] == "Ensure late checkout policy is consistent"
    assert loop_data["model"] == "qwen3:8b"

    # 3. Pause, Stop, Satisfy endpoints
    pause_res = client.post(f"/api/admin/properties/{property_id}/improvement-loop/pause")
    assert pause_res.status_code == 200
    assert pause_res.json()["loop"]["status"] == "paused"

    stop_res = client.post(f"/api/admin/properties/{property_id}/improvement-loop/stop")
    assert stop_res.status_code == 200
    assert stop_res.json()["loop"]["status"] == "stopped"

    satisfy_res = client.post(f"/api/admin/properties/{property_id}/improvement-loop/satisfied")
    assert satisfy_res.status_code == 200
    assert satisfy_res.json()["loop"]["status"] == "satisfied"
