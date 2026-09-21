"""Context strategies.

The prototype uses ``FullContextStrategy``: every selected document is placed
in full into the prompt. The interface leaves room for a future
``RetrievalContextStrategy`` (chunking + retrieval) without changing the chat
or generation endpoints.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.models.document import DocumentContent

from .prompts import SYSTEM_PROMPT, SYSTEM_PROMPT_NO_SOURCES, build_reference_block


class ContextStrategy(ABC):
    name: str = "abstract"

    @abstractmethod
    def build_messages(
        self,
        documents: list[DocumentContent],
        user_prompt: str,
        *,
        system_prompt: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        """Return OpenAI-style chat messages."""


class FullContextStrategy(ContextStrategy):
    name = "full_context"

    def build_messages(
        self,
        documents: list[DocumentContent],
        user_prompt: str,
        *,
        system_prompt: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        if documents:
            block = build_reference_block([(d.display_name, d.full_markdown) for d in documents])
            system = (system_prompt or SYSTEM_PROMPT) + "\n\nSelected source materials:\n\n" + block
        else:
            system = system_prompt or SYSTEM_PROMPT_NO_SOURCES
        messages.append({"role": "system", "content": system})
        for h in history or []:
            if h.get("role") in ("user", "assistant") and h.get("content"):
                messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": user_prompt})
        return messages


# Planned for the final project, intentionally not implemented in the prototype:
# class RetrievalContextStrategy(ContextStrategy): ...

default_strategy: ContextStrategy = FullContextStrategy()
