"""Context budget checking.

Before any request is sent to the model we build the real messages, count the
tokens with llama-server's own tokenizer and compare against the active
context window minus the space reserved for the answer. Documents are never
truncated silently: if they do not fit, the caller gets a clear explanation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.config import settings

from .client import LlamaServerClient, LlamaServerUnavailable, llm_client


@dataclass
class ContextCheck:
    fits: bool
    prompt_tokens: int
    context_size: int
    max_output_tokens: int
    safety_reserve: int
    allowed_prompt_tokens: int
    model_name: str | None
    message: str
    suggestions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ContextTooLarge(Exception):
    def __init__(self, check: ContextCheck):
        super().__init__(check.message)
        self.check = check


async def check_messages(
    messages: list[dict[str, Any]],
    *,
    client: LlamaServerClient = llm_client,
    max_output_tokens: int | None = None,
) -> ContextCheck:
    info = await client.server_info()
    if not info.reachable:
        raise LlamaServerUnavailable(info.error or "llama-server is not running.")
    context_size = info.context_size or settings.fallback_context_size
    max_out = max_output_tokens or settings.max_output_tokens
    reserve = settings.context_safety_reserve
    allowed = max(context_size - max_out - reserve, 0)
    prompt_tokens = await client.count_prompt_tokens(messages)
    fits = prompt_tokens <= allowed
    if fits:
        msg = (
            f"Context usage: {prompt_tokens:,} / {context_size:,} tokens "
            f"({allowed:,} allowed for the prompt)."
        )
        suggestions: list[str] = []
    else:
        msg = (
            f"The selected documents require approximately {prompt_tokens:,} tokens, but the active model "
            f"context is {context_size:,} tokens (of which {allowed:,} are available for the prompt after "
            f"reserving {max_out:,} for the answer and {reserve:,} as a safety margin)."
        )
        suggestions = [
            "Select fewer documents.",
            "Start llama-server with a larger context (for example -c 65536).",
            "Use a model that supports a larger context window.",
        ]
    return ContextCheck(
        fits=fits,
        prompt_tokens=prompt_tokens,
        context_size=context_size,
        max_output_tokens=max_out,
        safety_reserve=reserve,
        allowed_prompt_tokens=allowed,
        model_name=info.model_name,
        message=msg,
        suggestions=suggestions,
    )
