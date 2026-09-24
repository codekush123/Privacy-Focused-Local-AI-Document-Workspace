"""Context strategies: how the selected documents become a prompt.

``FullContextStrategy``  every selected document in full (the prototype default)
``RetrievalContextStrategy``  only the passages that match the question
``auto``  full context while it fits the budget, retrieval when it does not

Both build the same ``<source id="n" name="...">`` structure with the same
locator headings, so citations, the citation viewer and the fact-checker work
identically whichever strategy produced the prompt. That is what makes the two
comparable: only the *selection* of text changes, never its shape.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

from app.config import settings
from app.models.document import DocumentContent
from app.services.retrieval.bm25 import Bm25Index, content_terms
from app.services.retrieval.chunker import Chunk, chunk_documents

from .prompts import CITATION_REMINDER, SYSTEM_PROMPT, SYSTEM_PROMPT_NO_SOURCES, build_reference_block, wrap_source

StrategyName = Literal["full", "retrieval", "auto"]


@dataclass
class StrategyInfo:
    """What a strategy actually did - shown in the UI and used by evaluations."""

    name: str
    used: str  # the strategy that produced this prompt ("full" or "retrieval")
    passages: int = 0
    passages_available: int = 0
    documents: int = 0
    characters: int = 0  # size of the whole prompt
    passage_characters: int = 0  # size of the retrieved passages only
    reason: str = ""
    locators: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "used": self.used,
            "passages": self.passages,
            "passages_available": self.passages_available,
            "documents": self.documents,
            "characters": self.characters,
            "passage_characters": self.passage_characters,
            "reason": self.reason,
            "locators": self.locators,
        }


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

    def build(
        self,
        documents: list[DocumentContent],
        user_prompt: str,
        *,
        system_prompt: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> tuple[list[dict[str, Any]], StrategyInfo]:
        """Messages plus a description of how they were assembled."""
        messages = self.build_messages(documents, user_prompt, system_prompt=system_prompt, history=history)
        info = StrategyInfo(
            name=self.name,
            used=self.name,
            documents=len(documents),
            characters=sum(len(str(m.get("content", ""))) for m in messages),
        )
        return messages, info


def _assemble(messages: list[dict[str, Any]], system: str, history, user_prompt: str) -> list[dict[str, Any]]:
    messages.append({"role": "system", "content": system})
    for h in history or []:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": user_prompt})
    return messages


class FullContextStrategy(ContextStrategy):
    name = "full"

    def build_messages(self, documents, user_prompt, *, system_prompt=None, history=None):
        if documents:
            block = build_reference_block([(d.display_name, d.full_markdown) for d in documents])
            system = (
                (system_prompt or SYSTEM_PROMPT)
                + "\n\nSelected source materials:\n\n"
                + block
                + "\n\n"
                + CITATION_REMINDER
            )
        else:
            system = system_prompt or SYSTEM_PROMPT_NO_SOURCES
        return _assemble([], system, history, user_prompt)


RETRIEVAL_NOTE = (
    "Only the passages relevant to the question are included below, not the complete documents. "
    "Each passage keeps its original location. If the passages do not contain the answer, say that "
    "the selected excerpts do not cover it rather than guessing."
)


class RetrievalContextStrategy(ContextStrategy):
    """BM25 over locator-preserving passages, assembled back into <source> blocks."""

    name = "retrieval"

    def __init__(
        self,
        top_k: int | None = None,
        max_characters: int | None = None,
        neighbours: int | None = None,
        include_outline: bool | None = None,
    ):
        self.top_k = top_k or settings.retrieval_top_k
        self.max_characters = max_characters or settings.retrieval_max_characters
        self.neighbours = settings.retrieval_neighbours if neighbours is None else neighbours
        self.include_outline = settings.retrieval_include_outline if include_outline is None else include_outline

    # ------------------------------------------------------------ selection
    def select(self, documents: list[DocumentContent], query: str) -> tuple[list[Chunk], StrategyInfo]:
        chunks = chunk_documents(documents, settings.retrieval_chunk_words, settings.retrieval_overlap_paragraphs)
        info = StrategyInfo(name=self.name, used=self.name, documents=len(documents), passages_available=len(chunks))
        if not chunks:
            info.reason = "the selected documents contain no text"
            return [], info
        if not content_terms(query):
            # "summarise this" has nothing to match on - retrieval would be arbitrary.
            info.used = "full"
            info.reason = "the request has no searchable terms, so the full documents are used"
            return [], info

        index = Bm25Index(chunks)
        hits = index.search(query, self.top_k)
        if not hits:
            info.used = "full"
            info.reason = "no passage matched the question, so the full documents are used"
            return [], info

        chosen: dict[tuple[str, int], Chunk] = {}
        by_key = {c.key: c for c in chunks}
        for chunk, _score in hits:
            for offset in range(-self.neighbours, self.neighbours + 1):
                neighbour = by_key.get((chunk.document_id, chunk.order + offset))
                if neighbour is not None:
                    chosen.setdefault(neighbour.key, neighbour)

        # Fill the budget in rank order, then present the passages in reading order.
        by_rank = {c.key: i for i, (c, _s) in enumerate(hits)}
        candidates = sorted(chosen.values(), key=lambda c: (by_rank.get(c.key, len(hits)), c.document_index, c.order))
        kept: list[Chunk] = []
        used = 0
        for c in candidates:
            if used + len(c.text) > self.max_characters:
                continue
            kept.append(c)
            used += len(c.text)
        if not kept:
            # The budget is smaller than any single passage: send the best one
            # anyway rather than silently falling back to the whole document.
            best = hits[0][0]
            kept, used = [best], len(best.text)
        kept.sort(key=lambda c: (c.document_index, c.order))
        info.passages = len(kept)
        info.passage_characters = used
        info.locators = sorted({f"{c.document_name} - {c.locator}" for c in kept})
        info.reason = f"{len(kept)} of {len(chunks)} passages matched the question"
        return kept, info

    # ------------------------------------------------------------- assembly
    def _sources_block(self, documents: list[DocumentContent], chunks: list[Chunk]) -> str:
        by_doc: dict[int, list[Chunk]] = {}
        for c in chunks:
            by_doc.setdefault(c.document_index, []).append(c)
        blocks: list[str] = []
        for index, doc in enumerate(documents, start=1):
            picked = by_doc.get(index)
            if not picked:
                continue
            parts: list[str] = []
            last_locator = None
            for c in sorted(picked, key=lambda c: c.order):
                if c.locator != last_locator:
                    parts.append(f"## {c.locator}")
                    last_locator = c.locator
                parts.append(c.text)
            blocks.append(wrap_source(index, doc.display_name, "\n\n".join(parts)))
        return "\n\n".join(blocks)

    @staticmethod
    def _outline(documents: list[DocumentContent], limit: int = 40) -> str:
        lines = []
        for i, d in enumerate(documents, start=1):
            locators = [s.locator for s in d.sections][:limit]
            more = "" if len(d.sections) <= limit else f" (+{len(d.sections) - limit} more)"
            # Deliberately not written as "S1 name: locator": that looks like a
            # citation and the model copies the shape into its answer.
            lines.append(f'Source {i} ("{d.display_name}") covers {", ".join(locators)}{more}')
        return "Contents of the selected documents:\n" + "\n".join(lines)

    def build_messages(self, documents, user_prompt, *, system_prompt=None, history=None):
        messages, _ = self.build(documents, user_prompt, system_prompt=system_prompt, history=history)
        return messages

    def build(self, documents, user_prompt, *, system_prompt=None, history=None):
        if not documents:
            return FullContextStrategy().build(documents, user_prompt, system_prompt=system_prompt, history=history)
        chunks, info = self.select(documents, user_prompt)
        if not chunks:
            # Fall back rather than send an empty or arbitrary context.
            messages, full_info = FullContextStrategy().build(
                documents, user_prompt, system_prompt=system_prompt, history=history
            )
            info.used = "full"
            info.characters = full_info.characters
            return messages, info

        parts = [system_prompt or SYSTEM_PROMPT, "", RETRIEVAL_NOTE, ""]
        if self.include_outline:
            parts += [self._outline(documents), ""]
        parts += ["Relevant excerpts:", "", self._sources_block(documents, chunks), "", CITATION_REMINDER]
        system = "\n".join(parts)
        messages = _assemble([], system, history, user_prompt)
        info.characters = sum(len(str(m.get("content", ""))) for m in messages)
        return messages, info


class AutoContextStrategy(ContextStrategy):
    """Full context while the documents are small; retrieval once they are not."""

    name = "auto"

    def __init__(self, threshold_characters: int | None = None):
        self.threshold = threshold_characters or settings.retrieval_auto_threshold_characters

    def _pick(self, documents: list[DocumentContent]) -> ContextStrategy:
        total = sum(len(d.full_markdown) for d in documents)
        return FullContextStrategy() if total <= self.threshold else RetrievalContextStrategy()

    def build_messages(self, documents, user_prompt, *, system_prompt=None, history=None):
        return self._pick(documents).build_messages(
            documents, user_prompt, system_prompt=system_prompt, history=history
        )

    def build(self, documents, user_prompt, *, system_prompt=None, history=None):
        inner = self._pick(documents)
        messages, info = inner.build(documents, user_prompt, system_prompt=system_prompt, history=history)
        total = sum(len(d.full_markdown) for d in documents)
        info.name = "auto"
        if inner.name == "full":
            info.reason = f"the selection is small ({total:,} characters), so everything is sent"
        else:
            detail = f"; {info.reason}" if info.reason else ""
            info.reason = f"the selection is large ({total:,} characters), so only matching passages are sent{detail}"
        return messages, info


_STRATEGIES: dict[str, type[ContextStrategy]] = {
    "full": FullContextStrategy,
    "retrieval": RetrievalContextStrategy,
    "auto": AutoContextStrategy,
}


def get_strategy(name: str | None = None) -> ContextStrategy:
    key = (name or settings.context_strategy or "full").lower()
    if key not in _STRATEGIES:
        raise ValueError(f"Unknown context strategy: {name}")
    return _STRATEGIES[key]()


def available_strategies() -> list[dict[str, str]]:
    return [
        {"id": "full", "label": "Full context", "description": "Send every selected document in full. Most faithful, slowest on long documents."},
        {"id": "retrieval", "label": "Retrieval", "description": "Send only the passages that match the question (BM25, local, no embeddings)."},
        {"id": "auto", "label": "Automatic", "description": "Full context for small selections, retrieval for large ones."},
    ]


# Kept for backwards compatibility with earlier code paths.
default_strategy: ContextStrategy = FullContextStrategy()
