"""Playwright app with loopback-only controls for deterministic session tests."""

from __future__ import annotations

import hmac
import ipaddress
import os
import time
from typing import Literal

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from app.config import settings
from app.main import app, store


class SessionClockRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=200)
    mode: Literal["idle_expired", "near_expiry", "revoked", "read"]


if settings.app_environment == "test" and os.environ.get("CONCIERGE_TESTING") == "1":

    @app.post("/__e2e__/guest-session-clock")
    async def control_guest_session_clock(payload: SessionClockRequest, request: Request):
        peer = request.client.host if request.client else ""
        try:
            if not ipaddress.ip_address(peer).is_loopback:
                raise ValueError("loopback is required")
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Not found.") from exc
        supplied = request.headers.get("X-E2E-Control", "")
        expected = os.environ.get("CONCIERGE_E2E_CONTROL_TOKEN", "")
        if not expected or not hmac.compare_digest(supplied, expected):
            raise HTTPException(status_code=404, detail="Not found.")

        session = store.peek(payload.session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found.")
        now = int(time.time())
        if payload.mode == "idle_expired":
            with store._connect() as db:
                db.execute(
                    "UPDATE sessions SET last_seen_at=? WHERE session_id=?",
                    (now - 86400, payload.session_id),
                )
        elif payload.mode == "near_expiry":
            with store._connect() as db:
                db.execute(
                    "UPDATE sessions SET last_seen_at=?,guest_token_expires_at=? WHERE session_id=?",
                    (now, now + 120, payload.session_id),
                )
        elif payload.mode == "revoked":
            store.revoke_guest_credentials(payload.session_id)

        with store._connect() as db:
            row = db.execute(
                "SELECT last_seen_at,guest_token_expires_at,guest_token_revoked_at "
                "FROM sessions WHERE session_id=?",
                (payload.session_id,),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Session not found.")
        return {
            "last_seen_at": row["last_seen_at"],
            "guest_token_expires_at": row["guest_token_expires_at"],
            "guest_token_revoked_at": row["guest_token_revoked_at"],
        }
