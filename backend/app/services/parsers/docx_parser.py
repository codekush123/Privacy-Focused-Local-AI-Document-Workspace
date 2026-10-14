"""DOCX parser using python-docx.

Walks the document body in order (paragraphs and tables interleaved),
converts headings, paragraphs, bullet/numbered items and tables to Markdown
and splits the result into sections at top-level headings.

Two places python-docx does not look into are read as well, because their
text is part of the document: content controls (``w:sdt``, the fill-in fields
of templates, which wrap whole paragraphs and tables) and text boxes. Missing
them dropped that text without a trace.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

from docx import Document as load_docx
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.models.document import DocumentSection, SourceType

from .base import BaseParser, ParseError, make_section, markdown_table

_HEADING_RE = re.compile(r"heading\s*(\d)", re.I)
# A text box is stored twice, as DrawingML and as a VML fallback; read one.
_MC_FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"


def _block_items(parent) -> Iterator:
    """Paragraphs and tables in reading order, including those inside content controls."""
    for child in parent.iterchildren():
        if child.tag in (qn("w:p"), qn("w:tbl")):
            yield child
        elif child.tag == qn("w:sdt"):
            content = child.find(qn("w:sdtContent"))
            if content is not None:
                yield from _block_items(content)


def _text_boxes(p_element) -> list[str]:
    """Paragraph texts of the text boxes anchored in one paragraph."""
    texts: list[str] = []
    for box in p_element.iter(qn("w:txbxContent")):
        if any(a.tag == _MC_FALLBACK for a in box.iterancestors()):
            continue
        for bp in box.iter(qn("w:p")):
            text = "".join(t.text or "" for t in bp.iter(qn("w:t"))).strip()
            if text and text not in texts:
                texts.append(text)
    return texts


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
        for child in _block_items(body):
            if child.tag == qn("w:p"):
                p = Paragraph(child, doc)
                boxes = _text_boxes(child)
                lvl = _heading_level(p)
                if lvl is not None and lvl <= 2 and p.text.strip():
                    flush()
                    current_title = p.text.strip()
                    buffer.extend(boxes)
                    continue  # the heading becomes the section header
                md = _paragraph_md(p)
                if md:
                    # keep consecutive list items together in one block
                    if md[:2] in ("* ", "1.") and buffer and buffer[-1][:2] in ("* ", "1."):
                        buffer[-1] += "\n" + md
                    else:
                        buffer.append(md)
                buffer.extend(boxes)
            elif child.tag == qn("w:tbl"):
                md = _table_md(Table(child, doc))
                if md:
                    buffer.append(md)
        flush()
        if not sections:
            raise ParseError("No readable text was found in the Word document.")
        return sections
