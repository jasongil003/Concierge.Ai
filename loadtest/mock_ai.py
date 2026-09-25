"""Fast deterministic OpenAI-compatible endpoint for non-billable load tests."""

from __future__ import annotations

import asyncio
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import uvicorn


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/models")
async def models() -> dict[str, object]:
    return {"data": [{"id": "concierge-loadtest", "owned_by": "local-test"}]}


@app.post("/v1/chat/completions")
async def chat(request: Request) -> JSONResponse:
    body = await request.json()
    mode = os.getenv("MOCK_AI_MODE", "normal").strip().lower()
    if mode == "slow":
        await asyncio.sleep(float(os.getenv("MOCK_AI_DELAY_SECONDS", "8")))
    if mode == "fail":
        raise HTTPException(status_code=503, detail="Deterministic test provider failure.")
    message = ""
    for item in body.get("messages", []):
        if item.get("role") == "user":
            message = str(item.get("content", ""))[:500]
    return JSONResponse(
        {
            "id": "loadtest-response",
            "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": f"Deterministic load-test response. Request received ({len(message)} characters)."}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 16, "total_tokens": 24},
        }
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("MOCK_AI_PORT", "8081")), workers=1)
