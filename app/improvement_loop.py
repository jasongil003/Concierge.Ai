import asyncio
import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from .ai_providers import AIMessage, AIModelService, PROVIDER_DEFINITIONS


ACTIVE_STATUSES = {"running", "awaiting_approval"}
FINAL_STATUSES = {"stopped", "satisfied"}
VALID_STATUSES = {"draft", "running", "awaiting_approval", "paused", "stopped", "satisfied", "error"}


class ImprovementLoopStore:
    """Persistent operator-owned state for an advisory improvement loop."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS improvement_loops (
                    property_id TEXT PRIMARY KEY,
                    objective TEXT NOT NULL DEFAULT '',
                    satisfaction_criteria TEXT NOT NULL DEFAULT '',
                    evidence TEXT NOT NULL DEFAULT '',
                    provider_id TEXT NOT NULL DEFAULT 'local',
                    model TEXT NOT NULL DEFAULT '',
                    approval_mode TEXT NOT NULL DEFAULT 'manual',
                    interval_seconds INTEGER NOT NULL DEFAULT 60,
                    max_iterations INTEGER NOT NULL DEFAULT 0,
                    max_consecutive_failures INTEGER NOT NULL DEFAULT 3,
                    status TEXT NOT NULL DEFAULT 'draft',
                    iteration_count INTEGER NOT NULL DEFAULT 0,
                    consecutive_failures INTEGER NOT NULL DEFAULT 0,
                    operator_feedback TEXT NOT NULL DEFAULT '',
                    last_error TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS improvement_loop_iterations (
                    iteration_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    property_id TEXT NOT NULL,
                    iteration_number INTEGER NOT NULL,
                    provider_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    status TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    score INTEGER,
                    model_recommends_satisfied INTEGER NOT NULL DEFAULT 0,
                    response_json TEXT NOT NULL DEFAULT '{}',
                    raw_response TEXT NOT NULL DEFAULT '',
                    operator_decision TEXT NOT NULL DEFAULT '',
                    operator_feedback TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    started_at INTEGER NOT NULL,
                    finished_at INTEGER,
                    UNIQUE(property_id, iteration_number)
                )
                """
            )

    def get(self, property_id: str) -> dict[str, Any]:
        now = int(time.time())
        with self._connect() as db:
            db.execute(
                """
                INSERT OR IGNORE INTO improvement_loops
                (property_id, created_at, updated_at)
                VALUES (?, ?, ?)
                """,
                (property_id, now, now),
            )
            row = db.execute("SELECT * FROM improvement_loops WHERE property_id = ?", (property_id,)).fetchone()
        return self._serialize_loop(row)

    def save_config(self, property_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.get(property_id)
        if current["status"] in ACTIVE_STATUSES:
            raise ValueError("Pause the loop before changing its configuration.")

        objective = str(payload.get("objective", current["objective"])).strip()
        criteria = str(payload.get("satisfaction_criteria", current["satisfaction_criteria"])).strip()
        evidence = str(payload.get("evidence", current["evidence"])).strip()
        provider_id = str(payload.get("provider_id", current["provider_id"])).strip().lower()
        model = str(payload.get("model", current["model"])).strip()
        approval_mode = str(payload.get("approval_mode", current["approval_mode"])).strip().lower()
        interval_seconds = int(payload.get("interval_seconds", current["interval_seconds"]))
        max_iterations = int(payload.get("max_iterations", current["max_iterations"]))
        max_failures = int(payload.get("max_consecutive_failures", current["max_consecutive_failures"]))

        if provider_id not in PROVIDER_DEFINITIONS or PROVIDER_DEFINITIONS[provider_id].get("unavailable"):
            raise ValueError("Choose an available AI provider.")
        if approval_mode not in {"manual", "continuous"}:
            raise ValueError("Approval mode must be manual or continuous.")
        if not 5 <= interval_seconds <= 86400:
            raise ValueError("Loop interval must be between 5 seconds and 24 hours.")
        if not 0 <= max_iterations <= 100000:
            raise ValueError("Maximum iterations must be zero (unlimited) or between 1 and 100000.")
        if not 1 <= max_failures <= 20:
            raise ValueError("Maximum consecutive failures must be between 1 and 20.")

        status = current["status"]
        if status in FINAL_STATUSES or status == "error":
            status = "paused"
        with self._connect() as db:
            db.execute(
                """
                UPDATE improvement_loops
                SET objective = ?, satisfaction_criteria = ?, evidence = ?, provider_id = ?, model = ?,
                    approval_mode = ?, interval_seconds = ?, max_iterations = ?, max_consecutive_failures = ?,
                    status = ?, last_error = '', updated_at = ?
                WHERE property_id = ?
                """,
                (
                    objective,
                    criteria,
                    evidence,
                    provider_id,
                    model,
                    approval_mode,
                    interval_seconds,
                    max_iterations,
                    max_failures,
                    status,
                    int(time.time()),
                    property_id,
                ),
            )
        return self.get(property_id)

    def validate_ready(self, property_id: str) -> dict[str, Any]:
        loop = self.get(property_id)
        if not loop["objective"]:
            raise ValueError("Add a loop objective before starting.")
        if not loop["satisfaction_criteria"]:
            raise ValueError("Add satisfaction criteria before starting.")
        if not loop["provider_id"] or loop["provider_id"] not in PROVIDER_DEFINITIONS:
            raise ValueError("Choose a valid AI provider before starting.")
        if PROVIDER_DEFINITIONS[loop["provider_id"]].get("unavailable"):
            raise ValueError(f"Provider '{loop['provider_id']}' is currently unavailable.")
        if not loop["model"]:
            raise ValueError("Choose a model before starting.")
        return loop

    def set_status(self, property_id: str, status: str, error: str = "") -> dict[str, Any]:
        if status not in VALID_STATUSES:
            raise ValueError("Invalid loop status.")
        with self._connect() as db:
            db.execute(
                """
                UPDATE improvement_loops
                SET status = ?, last_error = ?, updated_at = ?
                WHERE property_id = ?
                """,
                (status, error[:1000], int(time.time()), property_id),
            )
        return self.get(property_id)

    def start_iteration(self, property_id: str) -> dict[str, Any]:
        loop = self.validate_ready(property_id)
        now = int(time.time())
        with self._connect() as db:
            row = db.execute(
                "SELECT COALESCE(MAX(iteration_number), 0) FROM improvement_loop_iterations WHERE property_id = ?",
                (property_id,),
            ).fetchone()
            current_max = row[0] if row else 0
            number = max(loop["iteration_count"], current_max) + 1
            cursor = db.execute(
                """
                INSERT INTO improvement_loop_iterations
                (property_id, iteration_number, provider_id, model, status, started_at)
                VALUES (?, ?, ?, ?, 'running', ?)
                """,
                (property_id, number, loop["provider_id"], loop["model"], now),
            )
            db.execute(
                """
                UPDATE improvement_loops
                SET iteration_count = ?, updated_at = ?
                WHERE property_id = ?
                """,
                (number, now, property_id),
            )
        return {"iteration_id": cursor.lastrowid, "iteration_number": number, **loop}

    def complete_iteration(self, property_id: str, iteration_id: int, response: dict[str, Any], raw: str) -> dict[str, Any]:
        summary = str(response.get("summary") or response.get("next_action") or "Iteration completed.").strip()
        score = response.get("score")
        try:
            score = max(0, min(100, int(score))) if score is not None else None
        except (TypeError, ValueError):
            score = None
        recommends_satisfied = bool(response.get("satisfied"))
        with self._connect() as db:
            db.execute(
                """
                UPDATE improvement_loop_iterations
                SET status = 'completed', summary = ?, score = ?, model_recommends_satisfied = ?,
                    response_json = ?, raw_response = ?, finished_at = ?
                WHERE property_id = ? AND iteration_id = ?
                """,
                (
                    summary[:2000],
                    score,
                    1 if recommends_satisfied else 0,
                    json.dumps(response, separators=(",", ":")),
                    raw[:20000],
                    int(time.time()),
                    property_id,
                    iteration_id,
                ),
            )
            db.execute(
                """
                UPDATE improvement_loops
                SET consecutive_failures = 0, operator_feedback = '', last_error = '', updated_at = ?
                WHERE property_id = ?
                """,
                (int(time.time()), property_id),
            )
        return self.get(property_id)

    def fail_iteration(self, property_id: str, iteration_id: int, error: str) -> dict[str, Any]:
        loop = self.get(property_id)
        failures = loop["consecutive_failures"] + 1
        next_status = "error" if failures >= loop["max_consecutive_failures"] else "running"
        with self._connect() as db:
            db.execute(
                """
                UPDATE improvement_loop_iterations
                SET status = 'error', error = ?, finished_at = ?
                WHERE property_id = ? AND iteration_id = ?
                """,
                (error[:2000], int(time.time()), property_id, iteration_id),
            )
            db.execute(
                """
                UPDATE improvement_loops
                SET consecutive_failures = ?, status = ?, last_error = ?, updated_at = ?
                WHERE property_id = ?
                """,
                (failures, next_status, error[:1000], int(time.time()), property_id),
            )
        return self.get(property_id)

    def cancel_iteration(self, property_id: str, iteration_id: int, reason: str = "Iteration cancelled by operator.") -> dict[str, Any]:
        with self._connect() as db:
            db.execute(
                """
                UPDATE improvement_loop_iterations
                SET status = 'cancelled', error = ?, finished_at = ?
                WHERE property_id = ? AND iteration_id = ? AND status = 'running'
                """,
                (reason[:2000], int(time.time()), property_id, iteration_id),
            )
        return self.get(property_id)

    def cleanup_orphaned_iterations(self) -> int:
        now = int(time.time())
        with self._connect() as db:
            cursor = db.execute(
                """
                UPDATE improvement_loop_iterations
                SET status = 'cancelled', error = 'Server reloaded while iteration was running.', finished_at = ?
                WHERE status = 'running'
                """,
                (now,),
            )
            return cursor.rowcount

    def decide_iteration(self, property_id: str, decision: str, feedback: str = "") -> dict[str, Any]:
        if decision not in {"approved", "revision_requested"}:
            raise ValueError("Decision must approve the iteration or request revision.")
        with self._connect() as db:
            latest = db.execute(
                """
                SELECT iteration_id FROM improvement_loop_iterations
                WHERE property_id = ? AND status = 'completed'
                ORDER BY iteration_number DESC LIMIT 1
                """,
                (property_id,),
            ).fetchone()
            if latest is None:
                raise ValueError("There is no completed iteration to review.")
            db.execute(
                """
                UPDATE improvement_loop_iterations
                SET operator_decision = ?, operator_feedback = ?
                WHERE iteration_id = ?
                """,
                (decision, feedback[:4000], latest["iteration_id"]),
            )
            db.execute(
                """
                UPDATE improvement_loops
                SET operator_feedback = ?, status = 'running', updated_at = ?
                WHERE property_id = ?
                """,
                (feedback[:4000], int(time.time()), property_id),
            )
        return self.get(property_id)

    def list_iterations(self, property_id: str, limit: int = 30) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT * FROM improvement_loop_iterations
                WHERE property_id = ?
                ORDER BY iteration_number DESC LIMIT ?
                """,
                (property_id, max(1, min(limit, 100))),
            ).fetchall()
        return [self._serialize_iteration(row) for row in rows]

    def recent_context(self, property_id: str, limit: int = 5) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT * FROM improvement_loop_iterations
                WHERE property_id = ? AND status = 'completed'
                ORDER BY iteration_number DESC LIMIT ?
                """,
                (property_id, max(1, min(limit, 50))),
            ).fetchall()
        return list(reversed([self._serialize_iteration(row) for row in rows]))

    def running_property_ids(self) -> list[str]:
        with self._connect() as db:
            rows = db.execute("SELECT property_id FROM improvement_loops WHERE status = 'running'").fetchall()
        return [row["property_id"] for row in rows]

    @staticmethod
    def _serialize_loop(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "property_id": row["property_id"],
            "objective": row["objective"],
            "satisfaction_criteria": row["satisfaction_criteria"],
            "evidence": row["evidence"],
            "provider_id": row["provider_id"],
            "model": row["model"],
            "approval_mode": row["approval_mode"],
            "interval_seconds": row["interval_seconds"],
            "max_iterations": row["max_iterations"],
            "max_consecutive_failures": row["max_consecutive_failures"],
            "status": row["status"],
            "iteration_count": row["iteration_count"],
            "consecutive_failures": row["consecutive_failures"],
            "operator_feedback": row["operator_feedback"],
            "last_error": row["last_error"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _serialize_iteration(row: sqlite3.Row) -> dict[str, Any]:
        try:
            response = json.loads(row["response_json"] or "{}")
        except json.JSONDecodeError:
            response = {}
        return {
            "iteration_id": row["iteration_id"],
            "iteration_number": row["iteration_number"],
            "provider_id": row["provider_id"],
            "model": row["model"],
            "status": row["status"],
            "summary": row["summary"],
            "score": row["score"],
            "model_recommends_satisfied": bool(row["model_recommends_satisfied"]),
            "response": response,
            "operator_decision": row["operator_decision"],
            "operator_feedback": row["operator_feedback"],
            "error": row["error"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
        }


class ImprovementLoopManager:
    def __init__(self, store: ImprovementLoopStore, models: AIModelService) -> None:
        self.store = store
        self.models = models
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.locks: dict[str, asyncio.Lock] = {}

    def snapshot(self, property_id: str) -> dict[str, Any]:
        return {"loop": self.store.get(property_id), "iterations": self.store.list_iterations(property_id)}

    def start(self, property_id: str) -> dict[str, Any]:
        loop = self.store.validate_ready(property_id)
        self.models.validate_direct_connection(property_id, loop["provider_id"], loop["model"])
        loop = self.store.set_status(property_id, "running")
        self._schedule(property_id)
        return loop

    def pause(self, property_id: str) -> dict[str, Any]:
        loop = self.store.set_status(property_id, "paused")
        self._cancel(property_id)
        return loop

    def stop(self, property_id: str) -> dict[str, Any]:
        loop = self.store.set_status(property_id, "stopped")
        self._cancel(property_id)
        return loop

    def satisfy(self, property_id: str) -> dict[str, Any]:
        loop = self.store.set_status(property_id, "satisfied")
        self._cancel(property_id)
        return loop

    def decide(self, property_id: str, decision: str, feedback: str = "") -> dict[str, Any]:
        loop = self.store.decide_iteration(property_id, decision, feedback)
        self._schedule(property_id)
        return loop

    async def run_single(self, property_id: str) -> dict[str, Any]:
        loop = self.store.validate_ready(property_id)
        self.models.validate_direct_connection(property_id, loop["provider_id"], loop["model"])
        self._cancel(property_id)
        self.store.set_status(property_id, "running")
        await self._run_iteration(property_id)
        loop = self.store.get(property_id)
        if loop["status"] == "running":
            self.store.set_status(property_id, "paused")
        return self.snapshot(property_id)

    def resume_persisted(self) -> None:
        self.store.cleanup_orphaned_iterations()
        for property_id in self.store.running_property_ids():
            self._schedule(property_id)

    def shutdown(self) -> None:
        for property_id in list(self.tasks):
            self._cancel(property_id)

    def _schedule(self, property_id: str) -> None:
        existing = self.tasks.get(property_id)
        if existing and not existing.done():
            return
        task = asyncio.create_task(self._run(property_id), name=f"improvement-loop:{property_id}")
        self.tasks[property_id] = task
        task.add_done_callback(lambda completed, key=property_id: self._task_done(key, completed))

    def _cancel(self, property_id: str) -> None:
        task = self.tasks.get(property_id)
        if task and not task.done() and task is not asyncio.current_task():
            task.cancel()

    def _task_done(self, property_id: str, task: asyncio.Task[None]) -> None:
        if self.tasks.get(property_id) is task:
            self.tasks.pop(property_id, None)
        if task.cancelled():
            return
        try:
            task.exception()
        except asyncio.CancelledError:
            return

    async def _run(self, property_id: str) -> None:
        try:
            while True:
                loop = self.store.get(property_id)
                if loop["status"] != "running":
                    return
                if loop["max_iterations"] and loop["iteration_count"] >= loop["max_iterations"]:
                    self.store.set_status(property_id, "paused", "Iteration limit reached.")
                    return

                await self._run_iteration(property_id)
                loop = self.store.get(property_id)
                if loop["status"] != "running":
                    return

                # If the latest iteration recommended satisfied, halt in awaiting_approval for operator confirmation
                latest_iterations = self.store.list_iterations(property_id, limit=1)
                if latest_iterations and latest_iterations[0].get("model_recommends_satisfied"):
                    self.store.set_status(property_id, "awaiting_approval")
                    return

                if loop["approval_mode"] == "manual":
                    self.store.set_status(property_id, "awaiting_approval")
                    return
                await asyncio.sleep(loop["interval_seconds"])
        except asyncio.CancelledError:
            return

    async def _run_iteration(self, property_id: str) -> None:
        lock = self.locks.setdefault(property_id, asyncio.Lock())
        async with lock:
            loop = self.store.get(property_id)
            if loop["status"] != "running":
                return
            iteration = self.store.start_iteration(property_id)
            try:
                messages = build_iteration_messages(loop, self.store.recent_context(property_id))
                response = await self.models.direct_chat(
                    property_id=property_id,
                    provider_id=loop["provider_id"],
                    model=loop["model"],
                    messages=messages,
                )
                parsed = parse_iteration_response(response.text)
                self.store.complete_iteration(property_id, iteration["iteration_id"], parsed, response.text)
            except asyncio.CancelledError:
                self.store.cancel_iteration(property_id, iteration["iteration_id"], "Iteration cancelled.")
                raise
            except Exception as exc:
                failed = self.store.fail_iteration(property_id, iteration["iteration_id"], str(exc))
                if failed["status"] == "error" or failed["approval_mode"] == "manual":
                    self.store.set_status(property_id, "error", str(exc))


def build_iteration_messages(loop: dict[str, Any], history: list[dict[str, Any]]) -> list[AIMessage]:
    history_payload = [
        {
            "iteration": item["iteration_number"],
            "summary": item["summary"],
            "score": item["score"],
            "decision": item["operator_decision"],
            "feedback": item["operator_feedback"],
        }
        for item in history
        if item["status"] == "completed"
    ]
    system = (
        "You are the independent quality reviewer in an operator-controlled improvement loop. "
        "Assess the supplied objective and evidence. Never claim that code or configuration changed. "
        "Return JSON only with keys: summary (string), score (0-100 integer), satisfied (boolean), "
        "findings (array of strings), next_action (string), and acceptance_checks (array of strings). "
        "The satisfied value is a recommendation only; the human operator is the sole authority who can end the loop."
    )
    user = json.dumps(
        {
            "objective": loop["objective"],
            "satisfaction_criteria": loop["satisfaction_criteria"],
            "current_evidence": loop["evidence"],
            "latest_operator_feedback": loop["operator_feedback"],
            "previous_iterations": history_payload,
            "iteration_number": loop["iteration_count"] + 1,
        },
        indent=2,
    )
    return [AIMessage("system", system), AIMessage("user", user)]


def parse_iteration_response(raw: str) -> dict[str, Any]:
    text = raw.strip()
    # 1. Try directly parsing text
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return _normalize_payload(payload)
    except json.JSONDecodeError:
        pass

    # 2. Try extracting from markdown fenced code block
    fence_pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
    match = re.search(fence_pattern, text)
    if match:
        try:
            payload = json.loads(match.group(1).strip())
            if isinstance(payload, dict):
                return _normalize_payload(payload)
        except json.JSONDecodeError:
            pass

    # 3. Try finding outermost JSON object
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            payload = json.loads(text[start : end + 1])
            if isinstance(payload, dict):
                return _normalize_payload(payload)
        except json.JSONDecodeError:
            pass

    return {
        "summary": text[:2000] or "The provider returned an empty response.",
        "score": None,
        "satisfied": False,
        "findings": [],
        "next_action": "Review the unstructured provider response.",
        "acceptance_checks": [],
    }


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    payload.setdefault("summary", "Iteration completed.")
    payload.setdefault("satisfied", False)
    payload.setdefault("findings", [])
    payload.setdefault("next_action", "Review this iteration.")
    payload.setdefault("acceptance_checks", [])
    return payload
