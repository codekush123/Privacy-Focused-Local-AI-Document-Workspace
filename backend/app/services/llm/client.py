"""Single access point for all HTTP communication with llama.cpp ``llama-server``.

Nothing else in the codebase should talk to llama-server directly.

Endpoints used:
  GET  /health                - server availability
  GET  /props                 - active model path, active context size (n_ctx)
  GET  /v1/models             - model id / metadata (n_ctx_train etc.)
  POST /tokenize              - exact token counting with the loaded model
  POST /apply-template        - render messages with the model's chat template
  POST /v1/chat/completions   - OpenAI-compatible chat, always streamed (see below)

Every completion is streamed with ``return_progress``, also when the caller
wants the whole answer at once. llama-server then reports how far it has read
the prompt while it reads it. On a CPU that reading takes minutes, and without
those reports the connection is silent for the whole time: a 14,000-token
prompt at ~22 tokens/s outlasted the read timeout. With them the timeout only
applies between two reports, and the same numbers drive the progress bar in
the UI (``activities``). Servers that do not know the flag simply ignore it.
"""
from __future__ import annotations

import base64
import itertools
import json
import logging
import time
from contextlib import aclosing
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import httpx

from app.config import settings

log = logging.getLogger(__name__)


class LlamaServerError(Exception):
    """Raised for any failure talking to llama-server (with a user-friendly message)."""


class LlamaServerUnavailable(LlamaServerError):
    pass


@dataclass
class Speed:
    """Throughput of the most recent completion, as reported by llama-server."""

    prompt_tokens_per_second: float | None = None
    generated_tokens_per_second: float | None = None
    measured_at: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "prompt_tokens_per_second": round(self.prompt_tokens_per_second, 1) if self.prompt_tokens_per_second else None,
            "generated_tokens_per_second": round(self.generated_tokens_per_second, 1) if self.generated_tokens_per_second else None,
        }


# Updated after every completion so the UI can show real throughput and warn
# when the loaded model is too heavy for this machine.
last_speed = Speed()


def _record_timings(timings: dict[str, Any] | None) -> None:
    if not timings:
        return
    p_ms, p_n = timings.get("prompt_ms"), timings.get("prompt_n")
    g_ms, g_n = timings.get("predicted_ms"), timings.get("predicted_n")
    if p_ms and p_n:
        last_speed.prompt_tokens_per_second = p_n / (p_ms / 1000)
    if g_ms and g_n:
        last_speed.generated_tokens_per_second = g_n / (g_ms / 1000)
    last_speed.measured_at = time.time()


@dataclass
class Activity:
    """One request to llama-server in flight, as the UI's progress bar shows it.

    ``prompt_processed`` counts the prompt tokens that are in the model's cache
    so far, including ``prompt_cached`` ones reused from the previous request,
    exactly as llama-server reports them.
    """

    id: int
    started_at: float
    max_tokens: int
    phase: str = "waiting"  # waiting -> reading -> (thinking) -> writing
    prompt_total: int | None = None
    prompt_cached: int = 0
    prompt_processed: int = 0
    prompt_ms: float = 0.0
    generated: int = 0  # streamed answer chunks, about one token each
    thinking: int = 0  # streamed reasoning chunks of a thinking model

    def to_dict(self) -> dict[str, Any]:
        read_now = max(self.prompt_processed - self.prompt_cached, 0)
        rate = read_now / (self.prompt_ms / 1000) if self.prompt_ms > 0 and read_now > 0 else None
        rate = rate or last_speed.prompt_tokens_per_second  # before the first report: the last measured speed
        eta = None
        if self.phase in ("waiting", "reading") and self.prompt_total and rate:
            eta = round(max(self.prompt_total - self.prompt_processed, 0) / rate)
        percent = None
        if self.prompt_total:
            percent = min(100, round(100 * self.prompt_processed / self.prompt_total))
        return {
            "id": self.id,
            "phase": self.phase,
            "elapsed_seconds": round(time.time() - self.started_at, 1),
            "prompt_total": self.prompt_total,
            "prompt_cached": self.prompt_cached,
            "prompt_processed": self.prompt_processed,
            "prompt_percent": percent,
            "reading_eta_seconds": eta,
            "prompt_tokens_per_second": round(rate, 1) if rate else None,
            "generated_tokens": self.generated,
            "thinking_tokens": self.thinking,
            "max_tokens": self.max_tokens,
        }


_activities: dict[int, Activity] = {}
_activity_ids = itertools.count(1)


def activities() -> list[dict[str, Any]]:
    """Requests in flight, newest first."""
    return [a.to_dict() for a in sorted(_activities.values(), key=lambda a: a.started_at, reverse=True)]


@dataclass
class Completion:
    """A finished completion. ``finish_reason == "length"`` means the output hit
    ``max_tokens`` and was cut off - for JSON output, that it is incomplete."""

    content: str
    finish_reason: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""

    @property
    def truncated(self) -> bool:
        return self.finish_reason == "length"


@dataclass
class ServerInfo:
    reachable: bool
    endpoint: str
    model_name: str | None = None
    model_path: str | None = None
    context_size: int | None = None  # active n_ctx per slot
    train_context_size: int | None = None  # n_ctx_train from metadata if reported
    total_slots: int | None = None
    build_info: str | None = None
    chat_template_available: bool = False
    supports_vision: bool = False
    supports_audio: bool = False
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class LlamaServerClient:
    def __init__(self, base_url: str | None = None, timeout: float | None = None):
        self._base_url = base_url
        self.timeout = timeout or settings.llm_timeout_seconds

    @property
    def base_url(self) -> str:
        return (self._base_url or settings.llm_base_url).rstrip("/")

    # ------------------------------------------------------------------ utils
    def _client(self, timeout: float | None = None) -> httpx.AsyncClient:
        # The read timeout is the longest silence allowed between two chunks of
        # a response, not a limit on the whole completion.
        t = timeout or self.timeout
        return httpx.AsyncClient(base_url=self.base_url, timeout=httpx.Timeout(t, connect=min(t, 10.0)))

    def _friendly(self, exc: Exception) -> LlamaServerError:
        if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
            return LlamaServerUnavailable(
                "llama-server is not running or not reachable. Start it locally and try again."
            )
        if isinstance(exc, httpx.ReadTimeout):
            return LlamaServerError(
                f"llama-server sent nothing for {int(self.timeout)} seconds and the request was given up. "
                "Raise LDW_LLM_TIMEOUT_SECONDS if the model is very slow on this machine."
            )
        if isinstance(exc, httpx.HTTPStatusError):
            try:
                body = exc.response.json()
                detail = (body.get("error") or {}).get("message") if isinstance(body, dict) else None
                detail = detail or exc.response.text
            except Exception:  # pragma: no cover
                detail = exc.response.text
            return LlamaServerError(f"llama-server returned an error: {str(detail)[:300]}")
        return LlamaServerError(f"Unexpected llama-server error: {exc}")

    # ----------------------------------------------------------------- health
    async def health(self) -> bool:
        try:
            async with self._client(settings.llm_health_timeout_seconds) as c:
                r = await c.get("/health")
                return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def server_info(self) -> ServerInfo:
        """Collect model + active context configuration from /props and /v1/models."""
        info = ServerInfo(reachable=False, endpoint=self.base_url)
        try:
            async with self._client(settings.llm_health_timeout_seconds) as c:
                h = await c.get("/health")
                if h.status_code != 200:
                    info.error = "llama-server is starting or the model is still loading."
                    return info
                info.reachable = True
                props = (await c.get("/props")).json()
                info.raw = props
                gen = props.get("default_generation_settings", {}) or {}
                info.context_size = gen.get("n_ctx")
                info.total_slots = props.get("total_slots")
                info.model_path = props.get("model_path")
                info.build_info = props.get("build_info")
                info.chat_template_available = bool(props.get("chat_template"))
                modalities = props.get("modalities") or {}
                info.supports_vision = bool(modalities.get("vision"))
                info.supports_audio = bool(modalities.get("audio"))
                # model name: prefer /v1/models id, fall back to path
                try:
                    models = (await c.get("/v1/models")).json()
                    data = models.get("data") or []
                    if data:
                        info.model_name = data[0].get("id")
                        meta = data[0].get("meta") or {}
                        info.train_context_size = meta.get("n_ctx_train")
                except Exception:  # noqa: BLE001 - /v1/models is optional
                    pass
                if info.model_name and ("/" in info.model_name or "\\" in info.model_name):
                    info.model_name = info.model_name.replace("\\", "/").split("/")[-1]
                if not info.model_name and info.model_path:
                    info.model_name = info.model_path.replace("\\", "/").split("/")[-1]
                if not info.context_size:
                    info.context_size = settings.fallback_context_size
                    info.error = "llama-server did not report its context size; using fallback."
        except httpx.HTTPError as exc:
            info.reachable = False
            info.error = str(self._friendly(exc))
        except ValueError as exc:  # JSON decode problems
            info.reachable = False
            info.error = f"Unexpected response from llama-server: {exc}"
        return info

    # --------------------------------------------------------------- tokenize
    async def tokenize(self, text: str, add_special: bool = False) -> list[int]:
        try:
            async with self._client() as c:
                r = await c.post(
                    "/tokenize",
                    json={"content": text, "add_special": add_special, "with_pieces": False},
                )
                r.raise_for_status()
                return r.json().get("tokens", [])
        except httpx.HTTPError as exc:
            raise self._friendly(exc) from exc

    async def count_tokens(self, text: str, add_special: bool = False) -> int:
        if not text:
            return 0
        return len(await self.tokenize(text, add_special=add_special))

    async def apply_template(self, messages: list[dict[str, Any]]) -> str | None:
        """Render messages with the server's chat template. Returns None if unsupported."""
        try:
            async with self._client() as c:
                r = await c.post("/apply-template", json={"messages": messages})
                if r.status_code != 200:
                    return None
                return r.json().get("prompt")
        except httpx.HTTPError:
            return None

    async def count_prompt_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Exact prompt token count: render with chat template, then tokenize."""
        prompt = await self.apply_template(messages)
        if prompt is not None:
            # The template output already contains special tokens as text.
            return await self.count_tokens(prompt, add_special=False)
        # Fallback: sum of message contents plus a small per-message overhead.
        total = 0
        for m in messages:
            total += await self.count_tokens(str(m.get("content", ""))) + 8
        return total

    # ------------------------------------------------------------------- chat
    @staticmethod
    def _payload(
        messages: list[dict[str, Any]],
        max_tokens: int | None,
        temperature: float | None,
        json_schema: dict[str, Any] | None = None,
        schema_name: str = "output",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            "return_progress": True,
            "max_tokens": max_tokens or settings.max_output_tokens,
            "temperature": settings.chat_temperature if temperature is None else temperature,
        }
        if json_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": json_schema},
            }
        return payload

    async def _events(self, payload: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        """Stream one completion: {"type": "delta" | "thinking", "content"} events, then
        {"type": "done", "usage": {..., "finish_reason"}}. Progress goes to ``activities``."""
        activity = Activity(id=next(_activity_ids), started_at=time.time(), max_tokens=payload["max_tokens"])
        _activities[activity.id] = activity
        try:
            async with self._client() as c:
                async with c.stream("POST", "/v1/chat/completions", json=payload) as r:
                    if r.status_code != 200:
                        body = await r.aread()
                        raise httpx.HTTPStatusError(
                            "error", request=r.request, response=httpx.Response(r.status_code, content=body)
                        )
                    activity.phase = "reading"
                    usage: dict[str, Any] = {}
                    async for line in r.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        chunk = line[5:].strip()
                        if chunk == "[DONE]":
                            break
                        try:
                            obj = json.loads(chunk)
                        except json.JSONDecodeError:
                            continue
                        if obj.get("error"):
                            message = obj["error"].get("message") if isinstance(obj["error"], dict) else obj["error"]
                            raise LlamaServerError(f"llama-server returned an error: {str(message)[:300]}")
                        progress = obj.get("prompt_progress")
                        if progress:
                            activity.prompt_total = progress.get("total") or activity.prompt_total
                            activity.prompt_cached = progress.get("cache") or 0
                            activity.prompt_processed = progress.get("processed") or 0
                            activity.prompt_ms = progress.get("time_ms") or 0.0
                        if obj.get("usage"):
                            usage = obj["usage"]
                        _record_timings(obj.get("timings"))
                        for ch in obj.get("choices") or []:
                            delta = ch.get("delta") or {}
                            if delta.get("reasoning_content"):
                                activity.phase, activity.thinking = "thinking", activity.thinking + 1
                                yield {"type": "thinking", "content": delta["reasoning_content"]}
                            if delta.get("content"):
                                activity.phase, activity.generated = "writing", activity.generated + 1
                                yield {"type": "delta", "content": delta["content"]}
                            if ch.get("finish_reason"):
                                usage.setdefault("finish_reason", ch["finish_reason"])
                    if usage.get("finish_reason") == "length":
                        log.info("Completion stopped at the output limit of %d tokens", payload["max_tokens"])
                    yield {"type": "done", "usage": usage}
        except httpx.HTTPError as exc:
            raise self._friendly(exc) from exc
        finally:
            _activities.pop(activity.id, None)

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        json_schema: dict[str, Any] | None = None,
        schema_name: str = "output",
    ) -> Completion:
        """The whole answer at once, with the reason it stopped."""
        payload = self._payload(messages, max_tokens, temperature, json_schema, schema_name)
        content: list[str] = []
        reasoning: list[str] = []
        usage: dict[str, Any] = {}
        async with aclosing(self._events(payload)) as events:
            async for ev in events:
                if ev["type"] == "delta":
                    content.append(ev["content"])
                elif ev["type"] == "thinking":
                    reasoning.append(ev["content"])
                else:
                    usage = ev["usage"]
        return Completion("".join(content), usage.get("finish_reason"), usage, "".join(reasoning))

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        json_schema: dict[str, Any] | None = None,
        schema_name: str = "output",
    ) -> str:
        completion = await self.complete(
            messages, max_tokens=max_tokens, temperature=temperature, json_schema=json_schema, schema_name=schema_name,
        )
        return completion.content

    async def chat_with_images(
        self,
        prompt: str,
        images: list[bytes],
        *,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        json_schema: dict[str, Any] | None = None,
        schema_name: str = "output",
        media_type: str = "image/png",
    ) -> str:
        """Multimodal completion: one text prompt plus one or more images.

        Requires llama-server to be started with a projector (``--mmproj``); use
        ``server_info().supports_vision`` to check before calling.
        """
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for raw in images:
            b64 = base64.b64encode(raw).decode("ascii")
            content.append({"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}})
        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": content})
        return await self.chat(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            json_schema=json_schema,
            schema_name=schema_name,
        )

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield {"type": "delta", "content"} (and {"type": "thinking", "content"} from a
        thinking model) as the answer is written, then {"type": "done", "usage": {...}}.

        Closing this generator (the user pressed Stop) closes the connection at
        once, and llama-server stops writing the answer nobody will read."""
        async with aclosing(self._events(self._payload(messages, max_tokens, temperature))) as events:
            async for ev in events:
                yield ev


llm_client = LlamaServerClient()
