"""Accuracy benchmark endpoints (the Evaluation tab)."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.evaluation.runner import (
    RunConfig,
    delete_result,
    list_results,
    load_result,
    results_dir,
    retrieval_check,
    run_cases,
)
from app.services.evaluation.suite import load_suite, self_check
from app.services.llm.client import LlamaServerError

from .common import ensure_ai_allowed

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/eval", tags=["evaluation"])

# One benchmark at a time: it keeps llama-server busy for a long while.
_lock = asyncio.Lock()
_stop = asyncio.Event()


class RunRequest(BaseModel):
    languages: list[Literal["en", "fi"]] = Field(default_factory=lambda: ["en", "fi"], min_length=1)
    strategies: list[Literal["full", "retrieval"]] = Field(default_factory=lambda: ["full", "retrieval"], min_length=1)
    cross_lingual: bool = True
    categories: list[Literal["detail", "list", "unanswerable"]] | None = None
    limit: int | None = Field(default=None, ge=1, le=100)
    max_output_tokens: int = Field(default=512, ge=64, le=4096)


@router.get("/suite")
async def suite() -> dict:
    s = load_suite()
    return {
        **s.summary(),
        "problems": self_check(s),
        "questions": [
            {"id": q["id"], "category": q["category"], "cross": bool(q.get("cross")), "question": q["question"],
             "note": q.get("note")}
            for q in s.questions
        ],
    }


@router.post("/retrieval")
async def retrieval() -> dict:
    result = await asyncio.to_thread(retrieval_check)
    (results_dir() / "retrieval_check.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


@router.get("/retrieval")
async def last_retrieval() -> dict:
    p = results_dir() / "retrieval_check.json"
    if not p.is_file():
        raise HTTPException(404, "The retrieval check has not been run yet.")
    return json.loads(p.read_text(encoding="utf-8"))


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/run")
async def run(body: RunRequest):
    ensure_ai_allowed()
    if _lock.locked():
        raise HTTPException(409, "A benchmark run is already in progress.")
    cfg = RunConfig(
        languages=list(body.languages),
        strategies=list(body.strategies),
        cross_lingual=body.cross_lingual,
        categories=list(body.categories) if body.categories else None,
        limit=body.limit,
        max_output_tokens=body.max_output_tokens,
    )

    async def stream():
        async with _lock:
            _stop.clear()
            try:
                async for ev in run_cases(cfg):
                    yield _sse(ev["type"], ev)
                    if _stop.is_set():
                        yield _sse("stopped", {"message": "Stopped. The questions answered so far are saved."})
                        return
            except LlamaServerError as exc:
                yield _sse("error", {"error": str(exc)})
            except Exception:  # noqa: BLE001
                log.exception("Benchmark run failed")
                yield _sse("error", {"error": "The benchmark failed. Check the backend log."})

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/stop")
async def stop() -> dict:
    _stop.set()
    return {"stopping": _lock.locked()}


@router.get("/results")
async def results() -> list[dict]:
    return list_results()


@router.get("/results/{run_id}")
async def result(run_id: str) -> dict:
    try:
        return load_result(run_id)
    except KeyError as exc:
        raise HTTPException(404, "This benchmark result was not found.") from exc


@router.delete("/results/{run_id}", status_code=204)
async def remove(run_id: str) -> None:
    try:
        delete_result(run_id)
    except KeyError as exc:
        raise HTTPException(404, "This benchmark result was not found.") from exc
