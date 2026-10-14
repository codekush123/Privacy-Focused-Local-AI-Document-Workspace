"""Build a prompt with the chosen strategy and make it fit the context window.

One place that every caller (chat, agent, generation) uses, so the strategy
switch and the token budget behave identically everywhere.

Full context is never truncated: if it does not fit, the caller gets the usual
``ContextTooLarge`` with the exact numbers. Retrieval is allowed to send fewer
passages, because dropping a low-ranked passage is the point of retrieval - but
that is reported, not hidden.

``auto`` is decided here rather than in the strategy class, because only here
is the real token count known: the documents go in full while they fit the
context window, and through retrieval once they do not.
"""
from __future__ import annotations

import logging
from typing import Any

from app.models.document import DocumentContent

from .context_budget import ContextCheck, ContextTooLarge, check_messages
from .context_strategy import (
    AutoContextStrategy,
    ContextStrategy,
    RetrievalContextStrategy,
    StrategyInfo,
    get_strategy,
)

log = logging.getLogger(__name__)

# How far the retrieval budget is cut on each attempt that does not fit.
SHRINK = 0.6
MAX_ATTEMPTS = 3


async def build_prompt(
    documents: list[DocumentContent],
    user_prompt: str,
    *,
    strategy: str | ContextStrategy | None = None,
    system_prompt: str | None = None,
    history: list[dict[str, str]] | None = None,
    max_output_tokens: int | None = None,
    reminder: str | None = None,
) -> tuple[list[dict[str, Any]], ContextCheck, StrategyInfo]:
    """Return (messages, context check, strategy info). Raises ContextTooLarge if it cannot fit.

    ``strategy`` is a name ("full", "retrieval", "auto") or a configured
    strategy object - the benchmark passes its own retrieval budget this way
    instead of changing the global settings other requests rely on.
    ``reminder`` is added as the last instruction of the system message, after
    the sources, where a small model still sees it (the chosen answer language).
    """
    chosen = strategy if isinstance(strategy, ContextStrategy) else get_strategy(strategy)
    base = chosen if isinstance(chosen, RetrievalContextStrategy) else RetrievalContextStrategy()

    def make(s: ContextStrategy) -> tuple[list[dict[str, Any]], StrategyInfo]:
        built, built_info = s.build(documents, user_prompt, system_prompt=system_prompt, history=history)
        if reminder and documents and built and built[0].get("role") == "system":
            built[0]["content"] += "\n\n" + reminder
        return built, built_info

    messages, info = make(chosen)
    check = await check_messages(messages, max_output_tokens=max_output_tokens)
    lead = ""  # why retrieval was chosen, kept in front of the retrieval's own reason

    if isinstance(chosen, AutoContextStrategy) and info.used == "full" and documents:
        if check.fits:
            if not chosen.threshold:
                info.reason = (
                    f"everything fits the context window ({check.prompt_tokens:,} of "
                    f"{check.allowed_prompt_tokens:,} prompt tokens), so the documents are sent in full"
                )
            return messages, check, info
        # Too large for full context: this is what retrieval is for.
        lead = (
            f"the documents need {check.prompt_tokens:,} prompt tokens but {check.allowed_prompt_tokens:,} fit, "
            "so only the matching passages are sent"
        )
        messages, info = make(base)
        info.name = "auto"
        info.reason = "; ".join(r for r in (lead, info.reason) if r)
        check = await check_messages(messages, max_output_tokens=max_output_tokens)

    # Retrieval can try again with a smaller budget; full context cannot shrink
    # without dropping evidence, so it is reported as too large instead.
    attempt = 0
    while not check.fits and info.used == "retrieval" and attempt < MAX_ATTEMPTS:
        attempt += 1
        budget = int(base.max_characters * (SHRINK**attempt))
        log.info("Retrieval prompt too large (%d tokens); retrying with %d characters", check.prompt_tokens, budget)
        retry = RetrievalContextStrategy(top_k=base.top_k, max_characters=budget)
        messages, retried = make(retry)
        retried.name = info.name
        retried.reason = "; ".join(
            r for r in (lead, retried.reason, f"reduced to fit the context window (attempt {attempt})") if r
        )
        info = retried
        check = await check_messages(messages, max_output_tokens=max_output_tokens)

    if not check.fits:
        raise ContextTooLarge(check)
    return messages, check, info
