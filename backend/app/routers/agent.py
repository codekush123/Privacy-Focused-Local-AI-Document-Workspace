"""Agentic endpoint: one request, a visible Router -> Tool -> Verifier trace."""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.agents.orchestrator import run_agent
from app.services.agents.router_agent import Intent

from .common import ensure_ai_allowed, resolve_documents

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent", tags=["agent"])


class AgentRequest(BaseModel):
    request: str = Field(min_length=1, max_length=20000)
    document_ids: list[str] = Field(default_factory=list)
    allow_files: bool = True
    auto_verify: bool = True
    max_output_tokens: int | None = Field(default=None, ge=16, le=32768)


@router.get("/tools")
async def tools() -> dict[str, list[str]]:
    return {"intents": list(Intent.__args__)}  # type: ignore[attr-defined]


@router.post("/run")
async def run(body: AgentRequest) -> StreamingResponse:
    """Server-sent events: one 'step' event per agent step, then 'result' or 'error'."""
    ensure_ai_allowed()
    docs = resolve_documents(body.document_ids)

    async def stream():
        try:
            async for event in run_agent(
                body.request, docs,
                allow_files=body.allow_files,
                auto_verify=body.auto_verify,
                max_output_tokens=body.max_output_tokens,
            ):
                name = event.get("step")
                kind = "result" if name == "result" else "error" if name == "error" else "step"
                yield f"event: {kind}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:  # noqa: BLE001
            log.exception("Agent run failed")
            payload = {"error": "The agent run failed. Check the backend log.", "detail": str(exc)[:200]}
            yield f"event: error\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
