"""Normalized internal document representation.

Every supported input format (txt, md, html, url, csv, docx, pdf, xlsx, pptx,
pasted text) is converted into a ``DocumentContent`` whose text lives in
Markdown. Sections keep the source locator (page, slide, sheet, heading, row
range) so source identity is not lost when several documents are combined into
one prompt.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    text = "text"
    txt = "txt"
    md = "md"
    html = "html"
    url = "url"
    csv = "csv"
    docx = "docx"
    pdf = "pdf"
    xlsx = "xlsx"
    pptx = "pptx"


class DocumentSection(BaseModel):
    section_id: str
    title: str
    # Human readable location inside the source, e.g. "Page 14", "Slide 7",
    # "Sheet: Results", "Heading: Introduction", "Rows 1-50".
    locator: str
    markdown: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentContent(BaseModel):
    id: str
    original_filename: str
    source_type: SourceType
    display_name: str
    source_path: str | None = None
    imported_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sections: list[DocumentSection] = Field(default_factory=list)
    full_markdown: str = ""
    character_count: int = 0
    token_count: int | None = None
    size_bytes: int = 0
    status: str = "ready"  # ready | error
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def finalize(self) -> "DocumentContent":
        """Compute ``full_markdown`` from sections if missing, and counts."""
        if not self.full_markdown:
            parts = [f"# Source: {self.display_name}", ""]
            for s in self.sections:
                if not s.title or s.title == s.locator or s.title in s.locator:
                    parts.append(f"## {s.locator}")
                else:
                    parts.append(f"## {s.locator} - {s.title}")
                parts.append("")
                parts.append(s.markdown.rstrip())
                parts.append("")
            self.full_markdown = "\n".join(parts).rstrip() + "\n"
        self.character_count = len(self.full_markdown)
        return self


class DocumentSummary(BaseModel):
    """Lightweight view returned by the document list endpoint."""

    id: str
    display_name: str
    original_filename: str
    source_type: SourceType
    status: str
    error: str | None = None
    size_bytes: int
    character_count: int
    token_count: int | None
    section_count: int
    imported_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_document(cls, doc: DocumentContent) -> "DocumentSummary":
        return cls(
            id=doc.id,
            display_name=doc.display_name,
            original_filename=doc.original_filename,
            source_type=doc.source_type,
            status=doc.status,
            error=doc.error,
            size_bytes=doc.size_bytes,
            character_count=doc.character_count,
            token_count=doc.token_count,
            section_count=len(doc.sections),
            imported_at=doc.imported_at,
            metadata=doc.metadata,
        )
