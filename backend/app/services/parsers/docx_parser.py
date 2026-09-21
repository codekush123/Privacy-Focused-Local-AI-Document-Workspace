"""DOCX parser using python-docx.

Walks the document body in order (paragraphs and tables interleaved),
converts headings, paragraphs, bullet/numbered items and tables to Markdown
and splits the result into sections at top-level headings.
"""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document as load_docx
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.models.document import DocumentSection, SourceType

from .base import BaseParser, ParseError, make_section, markdown_table

_HEADING_RE = re.compile(r"heading\s*(\d)", re.I)


def _heading_level(p: Paragraph) -> int | None:
    name = (p.style.name if p.style is not None else "") or ""
    if name.lower() == "title":
        return 1
    m = _HEADING_RE.search(name)
    return int(m.group(1)) if m else None


def _is_list(p: Paragraph) -> tuple[bool, bool]:
    """Return (is_list_item, is_numbered)."""
    name = ((p.style.name if p.style is not None else "") or "").lower()
    ppr = p._p.pPr
    has_num = ppr is not None and ppr.find(qn("w:numPr")) is not None
    if "list" in name or has_num:
        numbered = "number" in name
        return True, numbered
    return False, False


def _paragraph_md(p: Paragraph) -> str | None:
    text = p.text.strip()
    if not text:
        return None
    lvl = _heading_level(p)
    if lvl:
        return "#" * min(lvl + 1, 6) + " " + text  # keep '#' for the source header
    is_list, numbered = _is_list(p)
    if is_list:
        return ("1. " if numbered else "* ") + text
    return text


def _table_md(t: Table) -> str:
    rows: list[list[str]] = []
    for r in t.rows:
        cells = []
        seen = set()
        for c in r.cells:
            # merged cells repeat the same underlying element; skip duplicates
            key = id(c._tc)
            if key in seen:
                continue
            seen.add(key)
            cells.append(c.text.strip())
        rows.append(cells)
    if not rows:
        return ""
    return markdown_table(rows[0], rows[1:])


class DocxParser(BaseParser):
    source_type = SourceType.docx
    extensions = ("docx",)

    def parse(self, path: Path, display_name: str) -> list[DocumentSection]:
        try:
            doc = load_docx(str(path))
        except Exception as exc:  # noqa: BLE001
            raise ParseError("The Word document could not be opened. Is it a valid .docx file?") from exc

        sections: list[DocumentSection] = []
        current_title = "Document start"
        buffer: list[str] = []

        def flush():
            body = "\n\n".join(buffer).strip()
            # keep a heading-only first section (e.g. the document title) so nothing is lost
            if body or (current_title != "Document start" and not sections):
                sections.append(
                    make_section(len(sections) + 1, current_title, f"Heading: {current_title}", body)
                )
            buffer.clear()

        body = doc.element.body
        for child in body.iterchildren():
            if child.tag == qn("w:p"):
                p = Paragraph(child, doc)
                lvl = _heading_level(p)
                if lvl is not None and lvl <= 2 and p.text.strip():
                    flush()
                    current_title = p.text.strip()
                    continue  # the heading becomes the section header
                md = _paragraph_md(p)
                if md:
                    # keep consecutive list items together in one block
                    if md[:2] in ("* ", "1.") and buffer and buffer[-1][:2] in ("* ", "1."):
                        buffer[-1] += "\n" + md
                    else:
                        buffer.append(md)
            elif child.tag == qn("w:tbl"):
                md = _table_md(Table(child, doc))
                if md:
                    buffer.append(md)
        flush()
        if not sections:
            raise ParseError("No readable text was found in the Word document.")
        return sections
