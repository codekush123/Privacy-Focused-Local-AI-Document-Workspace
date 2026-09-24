"""Shared helper: ask the local model for JSON that must match a Pydantic model.

Used by verification, study mode, data queries and privacy guard. The schema
is passed to llama-server as ``response_format`` (grammar-constrained
decoding), the response is validated with Pydantic and one retry is made with
the validation error if the first attempt is invalid.
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


class StructuredOutputFailed(Exception):
    pass


def _extract_json(text: str) -> Any:
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
    # Structured helpers (verification, quizzes, scans) reason over the whole
    # material, so they deliberately use full context.
    messages, _check, _info = await build_prompt(
        documents or [], user_prompt, strategy="full", system_prompt=system_prompt, max_output_tokens=max_tokens
    )
    schema = model.model_json_schema()
    last_error = ""
    for attempt in range(2):
        try:
            raw = await llm_client.chat(
                messages,
                json_schema=schema,
                schema_name=model.__name__,
                max_tokens=max_tokens,
                temperature=settings.structured_temperature if temperature is None else temperature,
            )
            return model.model_validate(_extract_json(raw))
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = str(exc)[:400]
            log.warning("%s invalid on attempt %d: %s", what, attempt + 1, last_error)
            messages = messages + [
                {"role": "assistant", "content": "(previous attempt was invalid JSON)"},
                {"role": "user", "content": f"The previous output was invalid ({last_error}). Return only valid JSON matching the schema."},
            ]
    raise StructuredOutputFailed(f"The model did not return a valid {what}. Please retry.")
