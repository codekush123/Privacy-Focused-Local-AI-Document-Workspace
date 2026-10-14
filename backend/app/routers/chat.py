"""Chat and context-check endpoints."""
from __future__ import annotations

import json
import logging
import time
from contextlib import aclosing

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.schemas.api import ChatRequest, ContextCheckRequest, TranslateRequest
from app.services.llm.client import LlamaServerError, llm_client
from app.services.llm.context_budget import ContextTooLarge
from app.services.llm.context_builder import build_prompt
from app.services.llm.context_strategy import available_strategies, get_strategy
from app.services.features.citations import citation_stats, extract_citations, source_map
from app.services.features.answer_check import check_answer
from app.services.features.translate import language_name, translate_answer
from app.services.llm.prompts import (
    QUICK_ACTIONS, SYSTEM_PROMPT, SYSTEM_PROMPT_NO_SOURCES, TRANSLATE_PROMPT, answer_language_reminder,
    answer_language_rule,
)

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


@router.post("/chat/translate")
async def translate(body: TranslateRequest) -> dict:
    """Translate an existing answer; citations are protected and re-resolved."""
    ensure_ai_allowed()
    docs = resolve_documents(body.document_ids)
    t0 = time.perf_counter()
    try:
        result = await translate_answer(body.text, body.language)
    except (ContextTooLarge, LlamaServerError) as exc:
        raise to_http(exc) from exc
    log.info("Translated %d characters into %s in %.1fs", len(body.text), result.language, time.perf_counter() - t0)
    cites = extract_citations(result.text, docs) if docs else []
    return {
        "translation": result.text,
        "language": result.language,
        "truncated": result.truncated,
        "markers": {
            "total": result.markers_total,
            "restored": result.markers_restored,
            "reattached": result.markers_reattached,
        },
        "citations": [c.model_dump() for c in cites],
        "citation_stats": citation_stats(cites),
        "answer_check": check_answer(result.text, docs, body.question).model_dump(),
        "elapsed_seconds": round(time.perf_counter() - t0, 1),
    }


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def answer_system_prompt(answer_language: str | None, *, has_documents: bool) -> str | None:
    """The system prompt for a chosen answer language, or None for the default.

    The language applies with or without selected documents: a user who picks
    "Vastaa suomeksi" expects Finnish even before choosing any sources.
    """
    if not answer_language:
        return None
    base = SYSTEM_PROMPT if has_documents else SYSTEM_PROMPT_NO_SOURCES
    return base + answer_language_rule(language_name(answer_language))


@router.post("/chat")
async def chat(body: ChatRequest):
    ensure_ai_allowed()
    docs = resolve_documents(body.document_ids)
    system_prompt = answer_system_prompt(body.answer_language, has_documents=bool(docs))
    language = language_name(body.answer_language) if body.answer_language else None
    try:
        messages, check, strategy_info = await build_prompt(
            docs, body.prompt,
            strategy=body.strategy,
            system_prompt=system_prompt,
            history=[h.model_dump() for h in body.history],
            max_output_tokens=body.max_output_tokens,
            reminder=answer_language_reminder(language) if language else None,
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
            completion = await llm_client.complete(messages, max_tokens=body.max_output_tokens)
        except LlamaServerError as exc:
            raise to_http(exc) from exc
        log.info("Chat completed in %.1fs", time.perf_counter() - t0)
        answer = completion.content
        cites = extract_citations(answer, docs)
        return {
            "answer": answer,
            "truncated": completion.truncated,
            "context": check.to_dict(),
            "sources": [d.display_name for d in docs],
            "source_map": [m.model_dump() for m in source_map(docs)],
            "citations": [c.model_dump() for c in cites],
            "citation_stats": citation_stats(cites),
            "answer_check": check_answer(answer, docs, body.prompt).model_dump(),
            "strategy_info": strategy_info.to_dict(),
        }

    def _done_event(usage: dict, answer: str) -> dict:
        log.info("Chat stream completed in %.1fs (%s)", time.perf_counter() - t0, usage)
        cites = extract_citations(answer, docs)
        return {
            "usage": usage,
            # Cut off at the output limit: the UI says so instead of ending mid-sentence.
            "truncated": usage.get("finish_reason") == "length",
            "max_output_tokens": check.max_output_tokens,
            "elapsed_seconds": round(time.perf_counter() - t0, 1),
            "citations": [c.model_dump() for c in cites],
            "citation_stats": citation_stats(cites),
            "answer_check": check_answer(answer, docs, body.prompt).model_dump(),
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
        # aclosing: when the browser disconnects (Stop), the model stops at once.
        stream = aclosing(llm_client.chat_stream(messages, max_tokens=body.max_output_tokens))
        try:
            async with stream as events:
                async for ev in events:
                    if ev["type"] == "delta":
                        collected.append(ev["content"])
                        yield _sse("delta", {"content": ev["content"]})
                    elif ev["type"] == "thinking":
                        # A thinking model's reasoning is shown apart from the answer and never checked.
                        yield _sse("thinking", {"content": ev["content"]})
                    elif ev["type"] == "done":
                        yield _sse("done", _done_event(ev.get("usage") or {}, "".join(collected)))
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
