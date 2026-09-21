"""Chat and context-check endpoints."""
from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.schemas.api import ChatRequest, ContextCheckRequest
from app.services.llm.client import LlamaServerError, llm_client
from app.services.llm.context_budget import ContextTooLarge, check_messages
from app.services.llm.context_strategy import default_strategy
from app.services.features.citations import citation_stats, extract_citations, source_map
from app.services.llm.prompts import QUICK_ACTIONS, TRANSLATE_PROMPT

from .common import ensure_ai_allowed, resolve_documents, to_http

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])


@router.get("/chat/quick-actions")
async def quick_actions() -> dict[str, str]:
    return QUICK_ACTIONS


@router.get("/chat/translate-prompt")
async def translate_prompt(language: str) -> dict[str, str]:
    return {"prompt": TRANSLATE_PROMPT.format(language=language.strip()[:40] or "English")}


@router.post("/context/check")
async def context_check(body: ContextCheckRequest) -> dict:
    ensure_ai_allowed()
    docs = resolve_documents(body.document_ids)
    messages = default_strategy.build_messages(
        docs, body.prompt or "(question)", history=[h.model_dump() for h in body.history]
    )
    try:
        check = await check_messages(messages)
    except LlamaServerError as exc:
        raise to_http(exc) from exc
    return {**check.to_dict(), "strategy": default_strategy.name, "document_count": len(docs)}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat")
async def chat(body: ChatRequest):
    ensure_ai_allowed()
    docs = resolve_documents(body.document_ids)
    messages = default_strategy.build_messages(docs, body.prompt, history=[h.model_dump() for h in body.history])
    try:
        check = await check_messages(messages, max_output_tokens=body.max_output_tokens)
    except LlamaServerError as exc:
        raise to_http(exc) from exc
    if not check.fits:
        raise to_http(ContextTooLarge(check))

    t0 = time.perf_counter()
    log.info(
        "Chat: %d document(s), prompt tokens %d / ctx %d, stream=%s",
        len(docs), check.prompt_tokens, check.context_size, body.stream,
    )

    if not body.stream:
        try:
            answer = await llm_client.chat(messages, max_tokens=body.max_output_tokens)
        except LlamaServerError as exc:
            raise to_http(exc) from exc
        log.info("Chat completed in %.1fs", time.perf_counter() - t0)
        cites = extract_citations(answer, docs)
        return {
            "answer": answer,
            "context": check.to_dict(),
            "sources": [d.display_name for d in docs],
            "source_map": [m.model_dump() for m in source_map(docs)],
            "citations": [c.model_dump() for c in cites],
            "citation_stats": citation_stats(cites),
        }

    async def event_stream():
        yield _sse(
            "context",
            {**check.to_dict(), "sources": [d.display_name for d in docs], "source_map": [m.model_dump() for m in source_map(docs)]},
        )
        collected: list[str] = []
        try:
            async for ev in llm_client.chat_stream(messages, max_tokens=body.max_output_tokens):
                if ev["type"] == "delta":
                    collected.append(ev["content"])
                    yield _sse("delta", {"content": ev["content"]})
                else:
                    usage = ev.get("usage") or {}
                    log.info("Chat stream completed in %.1fs (%s)", time.perf_counter() - t0, usage)
                    cites = extract_citations("".join(collected), docs)
                    yield _sse(
                        "done",
                        {
                            "usage": usage,
                            "elapsed_seconds": round(time.perf_counter() - t0, 1),
                            "citations": [c.model_dump() for c in cites],
                            "citation_stats": citation_stats(cites),
                        },
                    )
        except LlamaServerError as exc:
            yield _sse("error", {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            log.exception("Streaming chat failed")
            yield _sse("error", {"error": "The answer could not be generated. Check the backend log."})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
