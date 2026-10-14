"""Shared helper: ask the local model for JSON that must match a Pydantic model.

Used by verification, study mode, data queries, privacy guard, timeline and
file generation. The schema is passed to llama-server as ``response_format``
(grammar-constrained decoding), and the response is validated with Pydantic.

Two different failures are told apart, because they need different retries:

* the output was **cut off** at the token limit (``finish_reason == "length"``):
  the JSON is incomplete, and asking again with the same limit only repeats
  the failure - measured: a Word summary of the benchmark's 9-page annual
  report hit 1,024 tokens twice and failed after 7 minutes. The retry gets a
  larger limit if the context window has room, otherwise the user is told
  plainly what happened;
* the output is **invalid** JSON or does not match the schema: one retry with
  the validation error.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.config import settings
from app.models.document import DocumentContent
from app.services.llm.client import llm_client
from app.services.llm.context_builder import build_prompt

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# A cut-off answer is retried once with up to this much more room - and only
# when the window allows at least half as much again: a slightly larger limit
# would just repeat the failure, minutes later on a CPU.
TRUNCATION_GROWTH = 2
MIN_GROWTH = 1.5


class StructuredOutputFailed(Exception):
    pass


class StructuredOutputTruncated(StructuredOutputFailed):
    """The model needed more output tokens than the context window leaves room for."""


def extract_json(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


async def ask_structured(
    model: type[T],
    user_prompt: str,
    documents: list[DocumentContent] | None = None,
    *,
    system_prompt: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    what: str = "structured output",
) -> T:
    # Structured helpers (verification, quizzes, scans, files) reason over the
    # whole material, so they deliberately use full context.
    budget = max_tokens or settings.max_output_tokens
    messages, check, _info = await build_prompt(
        documents or [], user_prompt, strategy="full", system_prompt=system_prompt, max_output_tokens=budget
    )
    schema = model.model_json_schema()
    temp = settings.structured_temperature if temperature is None else temperature
    last_error = ""
    for attempt in range(2):
        completion = await llm_client.complete(
            messages, json_schema=schema, schema_name=model.__name__, max_tokens=budget, temperature=temp,
        )
        if completion.truncated:
            # Room left in the window for a longer answer, keeping the safety reserve.
            room = check.context_size - check.prompt_tokens - check.safety_reserve
            log.warning("%s cut off at %d tokens on attempt %d (room for %d)", what, budget, attempt + 1, room)
            if attempt == 0 and room >= budget * MIN_GROWTH:
                budget = min(budget * TRUNCATION_GROWTH, room)
                continue
            raise StructuredOutputTruncated(
                f"The {what} did not fit into the {budget:,} tokens the model may write and was cut off before "
                "it was complete. Ask for something shorter (fewer items or sections), select fewer documents, "
                "or start llama-server with a larger context (-c)."
            )
        try:
            return model.model_validate(extract_json(completion.content))
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = str(exc)[:400]
            log.warning("%s invalid on attempt %d: %s", what, attempt + 1, last_error)
            messages = messages + [
                {"role": "assistant", "content": "(previous attempt was invalid JSON)"},
                {"role": "user", "content": f"The previous output was invalid ({last_error}). Return only valid JSON matching the schema."},
            ]
    raise StructuredOutputFailed(f"The model did not return a valid {what}. Please retry.")
