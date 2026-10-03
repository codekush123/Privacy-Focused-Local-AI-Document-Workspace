"""Frontier reference model for the benchmark (Claude via the Anthropic API).

BENCHMARK ONLY. The application itself is local-only and never imports this
module; only ``benchmark/run.py run --provider claude`` does. What it sends is
the benchmark corpus - documents about a fictional company - never a user's
documents. It needs the optional ``anthropic`` package and a credential
(``ANTHROPIC_API_KEY``), see benchmark/requirements-frontier.txt.

The prompt is built by the same context strategy the app uses, so the frontier
model sees exactly the same sources, locators and citation instructions as the
local models; only the endpoint differs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_MODEL = "claude-opus-5"


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


def _split_system(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """OpenAI-style messages (system first) -> Anthropic system + messages."""
    system = "\n\n".join(str(m["content"]) for m in messages if m["role"] == "system")
    rest = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] in ("user", "assistant")]
    return system, rest


class ClaudeAnswerer:
    def __init__(self, model: str = DEFAULT_MODEL):
        try:
            import anthropic
        except ImportError as exc:  # optional dependency
            raise FrontierError(
                "The frontier comparison needs the 'anthropic' package: "
                "backend/.venv/Scripts/python -m pip install -r benchmark/requirements-frontier.txt"
            ) from exc
        self._anthropic = anthropic
        # Credentials come from the environment (ANTHROPIC_API_KEY or an `ant auth login` profile).
        self.client = anthropic.AsyncAnthropic(max_retries=4)
        self.model = model

    async def answer(self, messages: list[dict[str, Any]], max_tokens: int) -> FrontierAnswer:
        anthropic = self._anthropic
        system, rest = _split_system(messages)
        try:
            # Thinking stays at the model's default (adaptive); the answer budget
            # is generous so thinking never crowds out the answer. "default"
            # fallbacks re-run a declined request on Anthropic's recommended model.
            response = await self.client.beta.messages.create(
                model=self.model,
                max_tokens=max(max_tokens, 16000),
                system=system,
                messages=rest,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.AuthenticationError as exc:
            raise FrontierSetupError("The Anthropic API key was rejected. Check ANTHROPIC_API_KEY.") from exc
        except anthropic.PermissionDeniedError as exc:
            raise FrontierSetupError(f"The API key cannot use {self.model}.") from exc
        except anthropic.NotFoundError as exc:
            raise FrontierSetupError(f"Unknown model {self.model}.") from exc
        except anthropic.RateLimitError as exc:
            raise FrontierError("Rate limited by the Anthropic API; try again later.") from exc
        except anthropic.APIStatusError as exc:
            raise FrontierError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise FrontierError("Could not reach the Anthropic API (network).") from exc
        except TypeError as exc:  # the SDK found no credential at all
            raise FrontierSetupError(
                "No Anthropic credential found. Set ANTHROPIC_API_KEY for this shell, e.g. "
                "PowerShell: $env:ANTHROPIC_API_KEY = '<your key>'"
            ) from exc

        if response.stop_reason == "refusal":
            return FrontierAnswer("", response.usage.input_tokens, response.usage.output_tokens, response.model, True)
        text = "".join(b.text for b in response.content if b.type == "text")
        return FrontierAnswer(text, response.usage.input_tokens, response.usage.output_tokens, response.model)
