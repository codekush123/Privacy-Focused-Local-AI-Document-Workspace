"""Frontier reference models for the benchmark: Claude (Anthropic API) and GPT (OpenAI API).

BENCHMARK ONLY. The application itself is local-only and never imports this
module; only ``benchmark/run.py run --provider claude|openai`` does. What it
sends is the benchmark corpus - documents about a fictional company - never a
user's documents. It needs the optional ``anthropic`` / ``openai`` packages
(benchmark/requirements-frontier.txt) and the provider's key in
``ANTHROPIC_API_KEY`` / ``OPENAI_API_KEY``.

The prompt is built by the same context strategy the app uses, so a frontier
model sees exactly the same sources, locators and citation instructions as the
local models; only the endpoint differs. Each model runs with its provider's
default reasoning settings - the comparison is "the model as its vendor ships
it", not a tuned configuration.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any

DEFAULT_MODELS = {
    "claude": "claude-opus-5",
    # OpenAI's "near-flagship" tier, priced like Claude Opus rather than like the top tier.
    "openai": "gpt-6.1-sol",
}
DEFAULT_MODEL = DEFAULT_MODELS["claude"]
# Room for the provider's own reasoning plus the answer; answers themselves are short.
OUTPUT_BUDGET = 16000


class FrontierError(Exception):
    """Raised with a plain-language message when the frontier call fails."""


class FrontierSetupError(FrontierError):
    """Missing or rejected credentials, unknown model: every further call would fail too."""


@dataclass
class FrontierAnswer:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    refused: bool = False


def _credential(name: str) -> str | None:
    """The key from the environment; on Windows also from the user's saved
    environment variables, so a key added in Windows settings works without
    restarting the terminal."""
    value = os.environ.get(name)
    if value or sys.platform != "win32":
        return value
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            return winreg.QueryValueEx(key, name)[0] or None
    except OSError:
        return None


def _require(package: str):
    try:
        return __import__(package)
    except ImportError as exc:  # optional dependency
        raise FrontierSetupError(
            f"The frontier comparison needs the '{package}' package: "
            "backend/.venv/Scripts/python -m pip install -r benchmark/requirements-frontier.txt"
        ) from exc


def _split_system(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """App-style messages (system first) -> system text + conversation."""
    system = "\n\n".join(str(m["content"]) for m in messages if m["role"] == "system")
    rest = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] in ("user", "assistant")]
    return system, rest


class ClaudeAnswerer:
    provider = "claude"

    def __init__(self, model: str | None = None):
        anthropic = _require("anthropic")
        key = _credential("ANTHROPIC_API_KEY")
        if not key:
            raise FrontierSetupError("No Anthropic key found. Set ANTHROPIC_API_KEY (Windows: environment variables for your account).")
        self._anthropic = anthropic
        self.client = anthropic.AsyncAnthropic(api_key=key, max_retries=4)
        self.model = model or DEFAULT_MODELS["claude"]

    async def answer(self, messages: list[dict[str, Any]], max_tokens: int) -> FrontierAnswer:
        anthropic = self._anthropic
        system, rest = _split_system(messages)
        try:
            # The document block is identical for every question about one
            # language, so it is cached: later questions read it at a fraction
            # of the price. Thinking stays at the model's default (adaptive);
            # "default" fallbacks re-run a declined request on Anthropic's
            # recommended model instead of returning the refusal.
            response = await self.client.beta.messages.create(
                model=self.model,
                max_tokens=max(max_tokens, OUTPUT_BUDGET),
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=rest,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.AuthenticationError as exc:
            raise FrontierSetupError("The Anthropic API key was rejected. Check ANTHROPIC_API_KEY.") from exc
        except anthropic.PermissionDeniedError as exc:
            raise FrontierSetupError(f"The Anthropic key cannot use {self.model}.") from exc
        except anthropic.NotFoundError as exc:
            raise FrontierSetupError(f"Unknown Anthropic model {self.model}.") from exc
        except anthropic.RateLimitError as exc:
            raise FrontierError("Rate limited by the Anthropic API; try again later.") from exc
        except anthropic.APIStatusError as exc:
            raise FrontierError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise FrontierError("Could not reach the Anthropic API (network).") from exc

        u = response.usage
        prompt_tokens = u.input_tokens + (u.cache_creation_input_tokens or 0) + (u.cache_read_input_tokens or 0)
        if response.stop_reason == "refusal":
            return FrontierAnswer("", prompt_tokens, u.output_tokens, response.model, True)
        text = "".join(b.text for b in response.content if b.type == "text")
        return FrontierAnswer(text, prompt_tokens, u.output_tokens, response.model)


class OpenAIAnswerer:
    provider = "openai"

    def __init__(self, model: str | None = None):
        openai = _require("openai")
        key = _credential("OPENAI_API_KEY")
        if not key:
            raise FrontierSetupError("No OpenAI key found. Set OPENAI_API_KEY (Windows: environment variables for your account).")
        self._openai = openai
        self.client = openai.AsyncOpenAI(api_key=key, max_retries=4)
        self.model = model or DEFAULT_MODELS["openai"]

    async def answer(self, messages: list[dict[str, Any]], max_tokens: int) -> FrontierAnswer:
        openai = self._openai
        system, rest = _split_system(messages)
        try:
            # Responses API: the documents go in as instructions (the system
            # role); OpenAI caches a repeated prompt prefix automatically.
            response = await self.client.responses.create(
                model=self.model,
                instructions=system,
                input=rest,
                max_output_tokens=max(max_tokens, OUTPUT_BUDGET),
                prompt_cache_key="ldw-benchmark",
            )
        except openai.AuthenticationError as exc:
            raise FrontierSetupError("The OpenAI API key was rejected. Check OPENAI_API_KEY.") from exc
        except openai.PermissionDeniedError as exc:
            raise FrontierSetupError(f"The OpenAI key cannot use {self.model}.") from exc
        except openai.NotFoundError as exc:
            raise FrontierSetupError(f"Unknown OpenAI model {self.model}.") from exc
        except openai.RateLimitError as exc:
            raise FrontierError("Rate limited by the OpenAI API; try again later.") from exc
        except openai.APIStatusError as exc:
            raise FrontierError(f"OpenAI API error {exc.status_code}: {exc.message}") from exc
        except openai.APIConnectionError as exc:
            raise FrontierError("Could not reach the OpenAI API (network).") from exc

        if response.status == "incomplete":
            reason = getattr(response.incomplete_details, "reason", "unknown")
            raise FrontierError(f"OpenAI returned an incomplete answer ({reason}).")
        refused = any(
            getattr(part, "type", "") == "refusal"
            for item in response.output if getattr(item, "type", "") == "message"
            for part in item.content
        )
        u = response.usage
        return FrontierAnswer(response.output_text or "", u.input_tokens, u.output_tokens, response.model, refused)


def make_answerer(provider: str, model: str | None = None):
    if provider == "claude":
        return ClaudeAnswerer(model)
    if provider == "openai":
        return OpenAIAnswerer(model)
    raise ValueError(f"Unknown frontier provider {provider!r}")
