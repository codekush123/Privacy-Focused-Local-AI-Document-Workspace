"""Chat and context-check endpoints."""
from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.schemas.api import ChatRequest, ContextCheckRequest
from app.services.llm.client import LlamaServerError, llm_client
from app.services.llm.context_budget import ContextTooLarge
from app.services.llm.context_builder import build_prompt
from app.services.llm.context_strategy import available_strategies, get_strategy
from app.services.features.citations import citation_stats, extract_citations, source_map
from app.services.llm.prompts import QUICK_ACTIONS, TRANSLATE_PROMPT

from .common import ensure_ai_allowed, resolve_documents, to_http

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])


@router.get("/context/strategies")
async def context_strategies() -> dict:
    from app.config import settings

    return {"strategies": available_strategies(), "default": settings.context_strategy}


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
    try:
        _messages, check, info = await build_prompt(
            docs, body.prompt or "(question)",
            strategy=body.strategy,
            history=[h.model_dump() for h in body.history],
        )
    except ContextTooLarge as exc:
        return {**exc.check.to_dict(), "strategy": body.strategy or get_strategy().name, "document_count": len(docs)}
    except LlamaServerError as exc:
        raise to_http(exc) from exc
    return {**check.to_dict(), "strategy": info.name, "strategy_info": info.to_dict(), "document_count": len(docs)}


@router.post("/context/compare")
async def context_compare(body: ContextCheckRequest) -> dict:
    """Token cost of the same question under each strategy - the basis for the
    full-context vs retrieval comparison."""
    ensure_ai_allowed()
    docs = resolve_documents(body.document_ids)
    out: dict[str, dict] = {}
    for name in ("full", "retrieval"):
        try:
            _m, check, info = await build_prompt(docs, body.prompt or "(question)", strategy=name)
            out[name] = {"fits": check.fits, "prompt_tokens": check.prompt_tokens, **info.to_dict()}
        except ContextTooLarge as exc:
            out[name] = {"fits": False, "prompt_tokens": exc.check.prompt_tokens, "reason": exc.check.message}
        except LlamaServerError as exc:
            raise to_http(exc) from exc
    full_t, ret_t = out["full"].get("prompt_tokens") or 0, out["retrieval"].get("prompt_tokens") or 0
    saved = full_t - ret_t
    out["saving"] = {
        "tokens": saved,
        "percent": round(100 * saved / full_t) if full_t else 0,
    }
    # Retrieval carries a fixed overhead (its instructions and the document
    # outline), so on small selections it can cost more than it saves.
    if saved > 0:
        out["recommended"] = "retrieval"
        out["note"] = f"Retrieval sends {saved:,} fewer tokens for this question."
    else:
        out["recommended"] = "full"
        out["note"] = (
            "The selection is small enough that sending it in full costs no more than retrieving from it "
            f"({-saved:,} tokens of retrieval overhead)."
        )
    return out


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat")
async def chat(body: ChatRequest):
    ensure_ai_allowed()
    docs = resolve_documents(body.document_ids)
    try:
        messages, check, strategy_info = await build_prompt(
            docs, body.prompt,
            strategy=body.strategy,
            history=[h.model_dump() for h in body.history],
            max_output_tokens=body.max_output_tokens,
        )
    except ContextTooLarge as exc:
        raise to_http(exc) from exc
    except LlamaServerError as exc:
        raise to_http(exc) from exc

    t0 = time.perf_counter()
    log.info(
        "Chat: %d document(s), strategy %s/%s, prompt tokens %d / ctx %d, stream=%s",
        len(docs), strategy_info.name, strategy_info.used, check.prompt_tokens, check.context_size, body.stream,
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
            "strategy_info": strategy_info.to_dict(),
        }

    async def event_stream():
        yield _sse(
            "context",
            {
                **check.to_dict(),
                "sources": [d.display_name for d in docs],
                "source_map": [m.model_dump() for m in source_map(docs)],
                "strategy_info": strategy_info.to_dict(),
            },
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
