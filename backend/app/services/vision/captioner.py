"""Describe extracted figures with a local vision-language model.

The model is asked for structured JSON (figure type, title, description, the
text visible in the image, and the concrete data points of a chart), which is
validated with Pydantic. The accepted descriptions are then merged back into
the document's Markdown as a "Figure" block inside the right section, so every
other feature - chat, citations, quiz, fact-check, export - can use the visual
content as if it had been text all along.

Requires llama-server started with a multimodal projector, e.g.
    llama-server -m model.gguf --mmproj mmproj.gguf -c 16384 --jinja
"""
from __future__ import annotations

import json
import logging
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import settings
from app.models.document import DocumentContent
from app.services.llm.client import LlamaServerError, llm_client

from .extractor import ImageRecord, image_bytes

log = logging.getLogger(__name__)

FIGURE_BLOCK_RE = re.compile(r"\n*### Figure .*?(?=\n## |\Z)", re.S)

FigureType = Literal["chart", "diagram", "photo", "screenshot", "table", "formula", "logo", "other"]


class FigureSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    figure_type: FigureType
    title: str = Field(description="Short caption, max 10 words")
    description: str = Field(description="What the figure shows, 1-4 sentences. Describe trends and relationships, not colours.")
    text_in_image: str = Field(description="Any text, axis labels or legend entries visible in the image; empty string if none")
    data_points: list[str] = Field(description='Concrete values read from a chart or table, e.g. "2023: 45%"; [] if not applicable')


class VisionUnavailable(Exception):
    pass


DESCRIBE_SYSTEM = (
    "You describe figures from documents for a reader who cannot see them. Be factual and specific. "
    "Never guess values that are not visible. If the image is decorative (a logo, a border, a background), "
    "say so briefly and return an empty data_points list."
)

DESCRIBE_PROMPT = (
    "This figure comes from the document '{document}', at {locator}.\n"
    "{context}"
    "Describe it so that someone reading only your description could answer questions about it. "
    "If it is a chart, read the axis labels, the legend and the actual values."
)


async def ensure_vision_available() -> None:
    info = await llm_client.server_info()
    if not info.reachable:
        raise VisionUnavailable(info.error or "llama-server is not running.")
    if not info.supports_vision:
        raise VisionUnavailable(
            "The loaded model has no vision support. Restart llama-server with a multimodal projector, "
            "for example: llama-server -m <model>.gguf --mmproj <mmproj>.gguf -c 16384 --jinja"
        )


def _section_context(doc: DocumentContent, record: ImageRecord, limit: int = 600) -> str:
    for s in doc.sections:
        if s.section_id == record.section_id:
            text = s.markdown.strip()
            if text:
                return f"Surrounding text of that section:\n\"\"\"\n{text[:limit]}\n\"\"\"\n"
            break
    return ""


async def describe_image(doc: DocumentContent, record: ImageRecord) -> FigureSpec:
    prompt = DESCRIBE_PROMPT.format(
        document=doc.display_name, locator=record.locator or "an unknown location",
        context=_section_context(doc, record),
    )
    raw = await llm_client.chat_with_images(
        prompt,
        [image_bytes(record)],
        system_prompt=DESCRIBE_SYSTEM,
        json_schema=FigureSpec.model_json_schema(),
        schema_name="FigureSpec",
        max_tokens=800,
        temperature=settings.structured_temperature,
    )
    try:
        return FigureSpec.model_validate(_loads(raw))
    except (ValidationError, ValueError) as exc:
        raise LlamaServerError(f"The figure description was not valid JSON: {str(exc)[:200]}") from exc


async def ask_about_image(doc: DocumentContent, record: ImageRecord, question: str) -> str:
    """Free-form question about one figure (no schema, plain Markdown answer)."""
    prompt = (
        f"The figure below comes from '{doc.display_name}' ({record.locator}).\n"
        f"{_section_context(doc, record)}"
        f"Question: {question.strip()}\n\n"
        "Answer using only what is visible in the image and the surrounding text. "
        "If the image does not show it, say so."
    )
    return await llm_client.chat_with_images(
        prompt, [image_bytes(record)], system_prompt=DESCRIBE_SYSTEM, max_tokens=700
    )


def _loads(text: str):
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


def apply_to_record(record: ImageRecord, spec: FigureSpec) -> ImageRecord:
    record.figure_type = spec.figure_type
    record.title = spec.title.strip()
    record.description = spec.description.strip()
    record.text_in_image = spec.text_in_image.strip()
    record.data_points = [d for d in spec.data_points if d.strip()]
    record.described = True
    return record


def figure_markdown(records: list[ImageRecord]) -> str:
    """Render accepted figure descriptions as a Markdown block."""
    lines: list[str] = []
    for i, r in enumerate(records, start=1):
        if not (r.described and r.accepted):
            continue
        label = f"Figure {i}" + (f" - {r.title}" if r.title else "")
        lines.append(f"### {label}")
        lines.append("")
        lines.append(f"_(image described locally by the vision model; type: {r.figure_type or 'unknown'})_")
        lines.append("")
        if r.description:
            lines.append(r.description)
        if r.text_in_image:
            lines.append("")
            lines.append(f"Text in the image: {r.text_in_image}")
        if r.data_points:
            lines.append("")
            lines.append("Values read from the figure:")
            lines.extend(f"* {d}" for d in r.data_points)
        lines.append("")
    return "\n".join(lines).rstrip()


def merge_into_document(doc: DocumentContent, records: list[ImageRecord]) -> DocumentContent:
    """Insert (or refresh) the figure descriptions inside each section's Markdown."""
    by_section: dict[str | None, list[ImageRecord]] = {}
    for r in records:
        by_section.setdefault(r.section_id, []).append(r)

    for section in doc.sections:
        section.markdown = FIGURE_BLOCK_RE.sub("", section.markdown).rstrip()
        block = figure_markdown(by_section.get(section.section_id, []))
        if block:
            section.markdown = (section.markdown + "\n\n" + block).strip()
            section.metadata["figures"] = len([r for r in by_section[section.section_id] if r.described and r.accepted])

    # figures whose section could not be resolved go into an extra section
    orphans = figure_markdown(by_section.get(None, []))
    doc.sections = [s for s in doc.sections if s.locator != "Figures"]
    if orphans:
        from app.services.parsers.base import make_section

        doc.sections.append(make_section(len(doc.sections) + 1, "Figures", "Figures", orphans))

    described = sum(1 for r in records if r.described and r.accepted)
    doc.metadata["figures_described"] = described
    doc.rebuild_markdown()
    log.info("Merged %d figure description(s) into %s", described, doc.display_name)
    return doc
