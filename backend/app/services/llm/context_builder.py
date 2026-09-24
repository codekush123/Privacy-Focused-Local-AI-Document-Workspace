"""Build a prompt with the chosen strategy and make it fit the context window.

One place that every caller (chat, agent, generation) uses, so the strategy
switch and the token budget behave identically everywhere.

Full context is never truncated: if it does not fit, the caller gets the usual
``ContextTooLarge`` with the exact numbers. Retrieval is allowed to send fewer
passages, because dropping a low-ranked passage is the point of retrieval - but
that is reported, not hidden.
"""
from __future__ import annotations

import logging
from typing import Any

from app.models.document import DocumentContent

from .context_budget import ContextCheck, ContextTooLarge, check_messages
from .context_strategy import RetrievalContextStrategy, StrategyInfo, get_strategy

log = logging.getLogger(__name__)

# How far the retrieval budget is cut on each attempt that does not fit.
SHRINK = 0.6
MAX_ATTEMPTS = 3


async def build_prompt(
    documents: list[DocumentContent],
    user_prompt: str,
    *,
    strategy: str | None = None,
    system_prompt: str | None = None,
    history: list[dict[str, str]] | None = None,
    max_output_tokens: int | None = None,
) -> tuple[list[dict[str, Any]], ContextCheck, StrategyInfo]:
    """Return (messages, context check, strategy info). Raises ContextTooLarge if it cannot fit."""
    chosen = get_strategy(strategy)
    messages, info = chosen.build(documents, user_prompt, system_prompt=system_prompt, history=history)
    check = await check_messages(messages, max_output_tokens=max_output_tokens)

    # Retrieval can try again with a smaller budget; full context cannot shrink
    # without dropping evidence, so it is reported as too large instead.
    attempt = 0
    while not check.fits and info.used == "retrieval" and attempt < MAX_ATTEMPTS:
        attempt += 1
        budget = int(RetrievalContextStrategy().max_characters * (SHRINK**attempt))
        log.info("Retrieval prompt too large (%d tokens); retrying with %d characters", check.prompt_tokens, budget)
        retry = RetrievalContextStrategy(max_characters=budget)
        messages, info = retry.build(documents, user_prompt, system_prompt=system_prompt, history=history)
        info.reason = (info.reason + f"; reduced to fit the context window (attempt {attempt})").lstrip("; ")
        check = await check_messages(messages, max_output_tokens=max_output_tokens)

    if not check.fits:
        raise ContextTooLarge(check)
    return messages, check, info
