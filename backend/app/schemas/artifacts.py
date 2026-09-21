"""Structured output schemas the LLM must produce for file generation.

The JSON schema of these models is passed to llama-server as
``response_format`` (grammar-constrained decoding), and the returned JSON is
validated with Pydantic before a writer turns it into a real file. Free-form
LLM text is never parsed for file generation.

Keep these models flat and simple: every field has a plain type and a default
so the resulting JSON schema converts cleanly to a llama.cpp grammar.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------------ DOCX ---
class DocxBlock(_Strict):
    type: Literal["heading", "paragraph", "bullets", "numbered", "table"]
    text: str = Field(default="", description="Text for heading/paragraph blocks")
    level: int = Field(default=1, ge=1, le=3, description="Heading level (1-3) for heading blocks")
    items: list[str] = Field(default_factory=list, description="Items for bullets/numbered blocks")
    headers: list[str] = Field(default_factory=list, description="Column headers for table blocks")
    rows: list[list[str]] = Field(default_factory=list, description="Table rows (cells as strings)")


class DocxSpec(_Strict):
    title: str
    subtitle: str = ""
    blocks: list[DocxBlock]


# ------------------------------------------------------------------ XLSX ---
class XlsxSheet(_Strict):
    name: str = Field(description="Worksheet name (max 31 chars)")
    headers: list[str]
    rows: list[list[str]]
    notes: str = Field(default="", description="Optional short note placed under the table")


class XlsxSpec(_Strict):
    workbook_title: str
    sheets: list[XlsxSheet]


# ------------------------------------------------------------------ PPTX ---
class PptxSlide(_Strict):
    title: str
    bullet_points: list[str]
    notes: str = Field(default="", description="Optional speaker notes")


class PptxSpec(_Strict):
    presentation_title: str
    subtitle: str = ""
    slides: list[PptxSlide]


def json_schema_for(model: type[BaseModel]) -> dict:
    """JSON schema suitable for llama-server's response_format."""
    return model.model_json_schema()
