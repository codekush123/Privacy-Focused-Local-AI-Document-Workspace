"""Structured artifact generation: prompt -> schema-constrained JSON -> file.

Flow for every Office format:
  1. build the same full-context messages as chat, plus format instructions
  2. check the context budget (never truncate)
  3. ask llama-server for JSON constrained by the Pydantic model's schema
  4. validate with Pydantic (one retry with the validation error on failure)
  5. hand the validated spec to the writer and register the export
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from app.config import settings
from app.models.document import DocumentContent
from app.schemas.artifacts import DocxSpec, PptxSpec, XlsxSpec, json_schema_for
from app.services.export_store import ExportInfo, export_store
from app.services.llm.client import LlamaServerError, llm_client
from app.services.llm.context_budget import ContextTooLarge
from app.services.llm.context_builder import build_prompt
from app.services.writers.docx_writer import write_docx
from app.services.writers.pptx_writer import write_pptx
from app.services.writers.markdown_export import markdown_to_docx, markdown_to_pdf, write_latex
from app.services.writers.simple_writers import write_csv, write_text
from app.services.writers.xlsx_writer import write_xlsx

log = logging.getLogger(__name__)


class GenerationFailed(Exception):
    """User-facing failure of structured generation."""


FORMAT_INSTRUCTIONS = {
    "docx": (
        "Produce the content of a Word document as JSON. Use 'heading' blocks to structure it, "
        "'paragraph' blocks for prose, 'bullets'/'numbered' blocks with 'items' for lists and 'table' blocks with "
        "'headers' and 'rows' for tabular data. Only fill the fields relevant to each block type. "
        "Base the content strictly on the selected source materials."
    ),
    "xlsx": (
        "Produce the content of an Excel workbook as JSON: one or more sheets, each with a short name, a header row "
        "and data rows. Every row must have exactly as many cells as there are headers; write all cell values as "
        "strings (numbers as plain digits). Base the content strictly on the selected source materials."
    ),
    "pptx": (
        "Produce the content of a PowerPoint presentation as JSON: a presentation title, an optional subtitle and a "
        "list of slides. Each slide has a short title and 3-6 concise bullet points (max ~15 words each). "
        "Base the content strictly on the selected source materials."
    ),
}

_SPECS: dict[str, type[BaseModel]] = {"docx": DocxSpec, "xlsx": XlsxSpec, "pptx": PptxSpec, "csv": XlsxSpec}
_WRITERS: dict[str, Callable[[Any, Path, list[str] | None], Path]] = {
    "docx": write_docx,
    "xlsx": write_xlsx,
    "pptx": write_pptx,
    "csv": lambda spec, path, _sources: write_csv(spec, path),
}


def _slug(text: str, fallback: str) -> str:
    s = re.sub(r"[^A-Za-z0-9À-ɏЀ-ӿ一-鿿؀-ۿ]+", "_", text or "").strip("_")
    return (s[:60] or fallback)


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


async def generate_artifact(
    kind: str,
    prompt: str,
    documents: list[DocumentContent],
    *,
    filename: str | None = None,
) -> ExportInfo:
    if kind not in _SPECS:
        raise GenerationFailed(f"Unsupported output format: {kind}")
    spec_model = _SPECS[kind]
    schema = json_schema_for(spec_model)
    instructions = FORMAT_INSTRUCTIONS["xlsx" if kind == "csv" else kind]
    user_prompt = f"{prompt.strip()}\n\n[Output format]\n{instructions}"
    # File generation summarises whole documents, so it always uses full context.
    messages, _check, _info = await build_prompt(documents, user_prompt, strategy="full")

    spec: BaseModel | None = None
    last_error = ""
    for attempt in range(2):
        try:
            raw = await llm_client.chat(
                messages,
                json_schema=schema,
                schema_name=f"{kind}_spec",
                temperature=settings.structured_temperature,
            )
            data = _extract_json(raw)
            spec = spec_model.model_validate(data)
            break
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = str(exc)[:400]
            log.warning("Structured %s output invalid on attempt %d: %s", kind, attempt + 1, last_error)
            messages = messages + [
                {"role": "assistant", "content": "(previous attempt was invalid JSON)"},
                {"role": "user", "content": f"The previous output was invalid ({last_error}). Return only valid JSON matching the schema."},
            ]
    if spec is None:
        pretty = {"docx": "Word", "xlsx": "Excel", "pptx": "PowerPoint", "csv": "CSV"}[kind]
        raise GenerationFailed(f"The generated {pretty} structure was invalid. Please retry.")

    title = getattr(spec, "title", None) or getattr(spec, "workbook_title", None) or getattr(spec, "presentation_title", None) or "export"
    fname = filename or f"{_slug(title, kind)}.{kind}"
    if not fname.lower().endswith(f".{kind}"):
        fname += f".{kind}"
    sources = [d.display_name for d in documents]
    info, path = export_store.reserve(fname, kind, sources, prompt)
    try:
        _WRITERS[kind](spec, path, sources)
    except Exception as exc:  # noqa: BLE001
        log.exception("Writer failed for %s", kind)
        raise GenerationFailed(f"The {kind.upper()} file could not be written: {exc}") from exc
    return export_store.commit(info)


TEXT_EXPORT_KINDS = ("md", "txt", "docx", "pdf", "tex")


def save_text_export(
    text: str, kind: str, filename: str | None, sources: list[str], prompt: str, title: str | None = None
) -> ExportInfo:
    """Save an existing chat answer as .md / .txt / .docx / .pdf / .tex (no model call)."""
    if kind not in TEXT_EXPORT_KINDS:
        raise GenerationFailed(f"Unsupported export format: {kind}")
    fname = filename or f"{_slug(prompt[:40], 'answer')}.{kind}"
    if not fname.lower().endswith(f".{kind}"):
        fname += f".{kind}"
    info, path = export_store.reserve(fname, kind, sources, prompt)
    try:
        if kind in ("md", "txt"):
            write_text(text, path)
        elif kind == "docx":
            markdown_to_docx(text, path, title=title, sources=sources)
        elif kind == "pdf":
            markdown_to_pdf(text, path, title=title, sources=sources)
        elif kind == "tex":
            write_latex(text, path, title=title, sources=sources)
    except Exception as exc:  # noqa: BLE001
        log.exception("Text export failed for %s", kind)
        raise GenerationFailed(f"The {kind.upper()} file could not be written: {exc}") from exc
    return export_store.commit(info)


__all__ = ["GenerationFailed", "LlamaServerError", "generate_artifact", "save_text_export"]
