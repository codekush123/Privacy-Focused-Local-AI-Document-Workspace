"""The model pipeline without a model: streamed completions with prompt progress,
cut-off structured output, the budget-aware 'auto' strategy and the launcher
endpoints. llama-server is replaced by an in-memory HTTP transport."""
from __future__ import annotations

import json
import threading
from contextlib import aclosing

import httpx
import pytest
from pydantic import BaseModel

from app.config import settings
from app.models.document import DocumentContent, DocumentSection, SourceType
from app.services.features import structured, verify
from app.services.llm import client as client_mod
from app.services.llm import context_builder
from app.services.llm.client import Completion, LlamaServerClient, LlamaServerError, activities
from app.services.llm.context_budget import ContextCheck, ContextTooLarge
from app.services.llm.context_strategy import AutoContextStrategy, StrategyInfo


def sse(*chunks: dict) -> bytes:
    return ("".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n").encode()


def fake_server(monkeypatch, body: bytes, seen: list | None = None) -> LlamaServerClient:
    """A client whose requests are answered by ``body``; request payloads go to ``seen``."""
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(json.loads(request.content))
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    c = LlamaServerClient(base_url="http://127.0.0.1:8080")
    monkeypatch.setattr(c, "_client", lambda timeout=None: httpx.AsyncClient(
        base_url=c.base_url, transport=httpx.MockTransport(handler)))
    return c


PROGRESS = [
    {"choices": [{"delta": {"role": "assistant", "content": None}}], "prompt_progress": {"total": 100, "cache": 40, "processed": 40, "time_ms": 0}},
    {"choices": [{"delta": {"role": "assistant", "content": None}}], "prompt_progress": {"total": 100, "cache": 40, "processed": 70, "time_ms": 1000}},
    {"choices": [{"delta": {"role": "assistant", "content": None}}], "prompt_progress": {"total": 100, "cache": 40, "processed": 100, "time_ms": 2000}},
]


# ------------------------------------------------------------ the client
@pytest.mark.anyio
async def test_every_completion_is_streamed_with_prompt_progress(monkeypatch):
    seen: list = []
    c = fake_server(monkeypatch, sse(*PROGRESS, {"choices": [{"delta": {"content": "Hi"}, "finish_reason": "stop"}]}), seen)
    assert await c.chat([{"role": "user", "content": "x"}], max_tokens=50) == "Hi"
    assert seen[0]["stream"] is True and seen[0]["return_progress"] is True and seen[0]["max_tokens"] == 50


@pytest.mark.anyio
async def test_activity_reports_progress_while_the_request_runs(monkeypatch):
    c = fake_server(monkeypatch, sse(*PROGRESS, {"choices": [{"delta": {"content": "Hi"}}]}))
    async with aclosing(c.chat_stream([{"role": "user", "content": "x"}])) as events:
        async for ev in events:
            if ev["type"] == "delta":
                live = activities()[0]
                break
    # 40 tokens came from the cache; 60 were read in 2 s, so 30 tokens/s.
    assert live["prompt_total"] == 100 and live["prompt_cached"] == 40 and live["prompt_percent"] == 100
    assert live["prompt_tokens_per_second"] == 30.0 and live["phase"] == "writing" and live["generated_tokens"] == 1
    assert activities() == []  # removed once the request is over


def test_activity_estimates_the_remaining_reading_time():
    a = client_mod.Activity(id=1, started_at=0, max_tokens=10, phase="reading",
                            prompt_total=1000, prompt_cached=100, prompt_processed=400, prompt_ms=10_000)
    d = a.to_dict()
    assert d["prompt_percent"] == 40 and d["prompt_tokens_per_second"] == 30.0 and d["reading_eta_seconds"] == 20


@pytest.mark.anyio
async def test_complete_reports_a_cut_off_answer_and_keeps_reasoning_apart(monkeypatch):
    c = fake_server(monkeypatch, sse(
        {"choices": [{"delta": {"reasoning_content": "Let me think."}}]},
        {"choices": [{"delta": {"content": '{"a": '}}]},
        {"choices": [{"delta": {}, "finish_reason": "length"}]},
    ))
    done = await c.complete([{"role": "user", "content": "x"}], max_tokens=5)
    assert done.content == '{"a": ' and done.truncated and done.reasoning == "Let me think."


@pytest.mark.anyio
async def test_an_error_inside_the_stream_is_reported(monkeypatch):
    c = fake_server(monkeypatch, sse({"error": {"message": "context size exceeded"}}))
    with pytest.raises(LlamaServerError, match="context size exceeded"):
        await c.chat([{"role": "user", "content": "x"}])


def test_activity_endpoint(client):
    assert client.get("/api/llm/activity").json() == {"active": []}


def test_chat_stream_keeps_reasoning_apart_and_flags_a_cut_off_answer(client, monkeypatch):
    from app.routers import chat as chat_router

    async def fake_build(documents, prompt, **kw):
        check = ContextCheck(True, 10, 100, 64, 10, 26, "m", "", [])
        return [{"role": "user", "content": prompt}], check, StrategyInfo(name="full", used="full")

    async def fake_stream(messages, **kw):
        yield {"type": "thinking", "content": "Hmm."}
        yield {"type": "delta", "content": "The answer is"}
        yield {"type": "done", "usage": {"finish_reason": "length"}}

    monkeypatch.setattr(chat_router, "build_prompt", fake_build)
    monkeypatch.setattr(chat_router.llm_client, "chat_stream", fake_stream)
    with client.stream("POST", "/api/chat", json={"prompt": "q", "document_ids": []}) as r:
        events = [line for line in r.iter_lines() if line.startswith("data:")]
    thinking, delta, done = (json.loads(e[5:]) for e in events[1:])
    assert thinking == {"content": "Hmm."} and delta == {"content": "The answer is"}
    assert done["truncated"] is True and done["max_output_tokens"] == 64


# ------------------------------------------------------ structured output
class Item(BaseModel):
    name: str


def _fake_prompt(context_size: int = 16384, prompt_tokens: int = 2000):
    async def build(documents, user_prompt, **kw):
        out = kw.get("max_output_tokens") or settings.max_output_tokens
        check = ContextCheck(True, prompt_tokens, context_size, out, 1024, context_size - out - 1024, "m", "", [])
        return [{"role": "user", "content": user_prompt}], check, StrategyInfo(name="full", used="full")
    return build


def _fake_complete(*completions: Completion, budgets: list[int]):
    queue = list(completions)

    async def complete(messages, **kw):
        budgets.append(kw["max_tokens"])
        return queue.pop(0)
    return complete


@pytest.mark.anyio
async def test_cut_off_json_is_retried_with_more_room_not_the_same_limit(monkeypatch):
    budgets: list[int] = []
    monkeypatch.setattr(structured, "build_prompt", _fake_prompt())
    monkeypatch.setattr(structured.llm_client, "complete", _fake_complete(
        Completion('{"name": "Ab', "length"), Completion('{"name": "Abc"}', "stop"), budgets=budgets))
    result = await structured.ask_structured(Item, "x", max_tokens=1000)
    assert result.name == "Abc" and budgets == [1000, 2000]


@pytest.mark.anyio
async def test_cut_off_json_without_room_explains_what_happened(monkeypatch):
    budgets: list[int] = []
    # 2,000 prompt tokens in a 4,096 window: no room to double a 1,000-token answer.
    monkeypatch.setattr(structured, "build_prompt", _fake_prompt(context_size=4096))
    monkeypatch.setattr(structured.llm_client, "complete", _fake_complete(
        Completion('{"name": "Ab', "length"), budgets=budgets))
    with pytest.raises(structured.StructuredOutputTruncated, match="cut off"):
        await structured.ask_structured(Item, "x", max_tokens=1000, what="Word file structure")
    assert budgets == [1000]  # no futile second attempt with the same limit


@pytest.mark.anyio
async def test_file_generation_gets_its_own_output_budget(monkeypatch, tmp_path):
    from app.schemas.artifacts import DocxBlock, DocxSpec
    from app.services import generation

    seen: dict = {}

    async def fake_structured(model, prompt, documents, **kw):
        seen.update(kw)
        return DocxSpec(title="Notes", blocks=[DocxBlock(type="paragraph", text="Hello")])

    monkeypatch.setattr(generation, "ask_structured", fake_structured)
    info = await generation.generate_artifact("docx", "Make notes", [])
    assert seen["max_tokens"] == settings.generation_max_output_tokens > settings.max_output_tokens
    assert info.filename == "Notes.docx" and info.size_bytes > 0

    async def failing(*_a, **_k):
        raise structured.StructuredOutputTruncated("The Word file structure did not fit")

    monkeypatch.setattr(generation, "ask_structured", failing)
    with pytest.raises(generation.GenerationFailed, match="did not fit"):
        await generation.generate_artifact("docx", "Make notes", [])


@pytest.mark.anyio
async def test_a_fact_check_without_claims_is_not_zero_percent_grounded(monkeypatch):
    async def no_claims(*_a, **_k):
        return verify.VerificationSpec(claims=[], overall="")

    monkeypatch.setattr(verify, "ask_structured", no_claims)
    result = await verify.verify_answer("The documents do not say.", [])
    assert result.grounding_score == 100 and "no factual claims" in result.overall


# ------------------------------------------------ budget-aware 'auto'
def _doc(text: str, name: str = "big.pdf") -> DocumentContent:
    pages = [DocumentSection(section_id=f"s{i}", title=f"Page {i}", locator=f"Page {i}", markdown=para)
             for i, para in enumerate(text.split("\n\n"), start=1)]
    return DocumentContent(id=name, original_filename=name, source_type=SourceType.pdf, display_name=name,
                           sections=pages).finalize()


def _budget(context_size: int):
    """A token counter of about 4 characters per token, in a window of ``context_size``."""
    async def check(messages, *, max_output_tokens=None, **_kw):
        tokens = sum(len(str(m["content"])) for m in messages) // 4
        out = max_output_tokens or settings.max_output_tokens
        allowed = context_size - out - settings.context_safety_reserve
        return ContextCheck(tokens <= allowed, tokens, context_size, out, settings.context_safety_reserve,
                            allowed, "m", "too large" if tokens > allowed else "ok", [])
    return check


DOC = _doc("\n\n".join(f"Section {i} talks about turbines, budgets and the year {2000 + i}. " * 30 for i in range(40)))


@pytest.mark.anyio
async def test_auto_sends_everything_while_it_fits(monkeypatch):
    monkeypatch.setattr(context_builder, "check_messages", _budget(10**6))
    _m, check, info = await context_builder.build_prompt([DOC], "Which year talks about budgets?", strategy="auto")
    assert info.name == "auto" and info.used == "full"
    assert "fits the context window" in info.reason and f"{check.prompt_tokens:,}" in info.reason


@pytest.mark.anyio
async def test_auto_switches_to_retrieval_only_when_it_does_not_fit(monkeypatch):
    monkeypatch.setattr(context_builder, "check_messages", _budget(16384))
    _m, check, info = await context_builder.build_prompt([DOC], "Which section mentions the year 2007?", strategy="auto")
    assert info.name == "auto" and info.used == "retrieval" and check.fits
    assert "prompt tokens but" in info.reason and "passages matched" in info.reason


@pytest.mark.anyio
async def test_full_context_is_refused_not_truncated(monkeypatch):
    monkeypatch.setattr(context_builder, "check_messages", _budget(16384))
    with pytest.raises(ContextTooLarge):
        await context_builder.build_prompt([DOC], "Which section mentions the year 2007?", strategy="full")


@pytest.mark.anyio
@pytest.mark.parametrize("strategy", ["full", "retrieval", "auto"])
async def test_the_answer_language_is_the_last_instruction_after_the_sources(monkeypatch, strategy):
    """Found by the browser smoke test: with the rule only above the sources, an English
    question got a Finnish answer 3 times out of 6 despite "Vastaa suomeksi"."""
    from app.services.llm.prompts import CITATION_REMINDER, answer_language_reminder

    monkeypatch.setattr(context_builder, "check_messages", _budget(10**6))
    reminder = answer_language_reminder("Finnish")
    messages, _c, _i = await context_builder.build_prompt([DOC], "Which year talks about budgets?",
                                                          strategy=strategy, reminder=reminder)
    system = messages[0]["content"]
    assert system.endswith(reminder) and system.index(CITATION_REMINDER) < system.index(reminder)
    plain, _c, _i = await context_builder.build_prompt([DOC], "Which year talks about budgets?", strategy=strategy)
    assert reminder not in plain[0]["content"]  # the benchmark's prompts are unchanged


def test_auto_threshold_is_off_by_default():
    assert settings.retrieval_auto_threshold_characters == 0
    _m, info = AutoContextStrategy().build([DOC], "budgets")
    assert info.used == "full"  # the budget decides, in build_prompt


# ------------------------------------------------------------- launcher
def test_launcher_endpoints_do_not_block_the_server(client, monkeypatch):
    from app.services.llm.launcher import launcher

    threads: list[str] = []
    original = launcher.status

    def recording_status():
        threads.append(threading.current_thread().name)
        return original()

    monkeypatch.setattr(launcher, "status", recording_status)
    assert client.get("/api/llm/launcher").status_code == 200
    assert threads and threads[0].startswith("asyncio")  # a worker thread, not the event loop
