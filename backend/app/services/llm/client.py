"""Single access point for all HTTP communication with llama.cpp ``llama-server``.

Nothing else in the codebase should talk to llama-server directly.

Endpoints used:
  GET  /health                - server availability
  GET  /props                 - active model path, active context size (n_ctx)
  GET  /v1/models             - model id / metadata (n_ctx_train etc.)
  POST /tokenize              - exact token counting with the loaded model
  POST /apply-template        - render messages with the model's chat template
  POST /v1/chat/completions   - OpenAI-compatible chat (streaming and non-streaming)
"""
from __future__ import annotations

import json
import logging
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
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class LlamaServerClient:
    def __init__(self, base_url: str | None = None, timeout: float | None = None):
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.timeout = timeout or settings.llm_timeout_seconds

    # ------------------------------------------------------------------ utils
    def _client(self, timeout: float | None = None) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, timeout=timeout or self.timeout)

    @staticmethod
    def _friendly(exc: Exception) -> LlamaServerError:
        if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
            return LlamaServerUnavailable(
                "llama-server is not running or not reachable. Start it locally and try again."
            )
        if isinstance(exc, httpx.ReadTimeout):
            return LlamaServerError("llama-server took too long to respond.")
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
    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        json_schema: dict[str, Any] | None = None,
        schema_name: str = "output",
    ) -> str:
        payload: dict[str, Any] = {
            "messages": messages,
            "stream": False,
            "max_tokens": max_tokens or settings.max_output_tokens,
            "temperature": settings.chat_temperature if temperature is None else temperature,
        }
        if json_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": json_schema},
            }
        try:
            async with self._client() as c:
                r = await c.post("/v1/chat/completions", json=payload)
                r.raise_for_status()
                data = r.json()
        except httpx.HTTPError as exc:
            raise self._friendly(exc) from exc
        choices = data.get("choices") or []
        if not choices:
            raise LlamaServerError("llama-server returned no completion.")
        return choices[0].get("message", {}).get("content") or ""

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield events: {"type": "delta", "content": str} ... {"type": "done", "usage": {...}}."""
        payload: dict[str, Any] = {
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_tokens": max_tokens or settings.max_output_tokens,
            "temperature": settings.chat_temperature if temperature is None else temperature,
        }
        try:
            async with self._client() as c:
                async with c.stream("POST", "/v1/chat/completions", json=payload) as r:
                    if r.status_code != 200:
                        body = await r.aread()
                        raise httpx.HTTPStatusError(
                            "error", request=r.request, response=httpx.Response(r.status_code, content=body)
                        )
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
                        if obj.get("usage"):
                            usage = obj["usage"]
                        for ch in obj.get("choices") or []:
                            delta = ch.get("delta", {}).get("content")
                            if delta:
                                yield {"type": "delta", "content": delta}
                            if ch.get("finish_reason"):
                                usage.setdefault("finish_reason", ch["finish_reason"])
                    yield {"type": "done", "usage": usage}
        except httpx.HTTPError as exc:
            raise self._friendly(exc) from exc


llm_client = LlamaServerClient()
