"""Grounded citations.

The system prompt asks the model to cite as ``[S<id>: <locator>]``. This module
parses those markers out of an answer and resolves each one to a concrete
document section so the UI can show the exact passage the model relied on.
"""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

from app.models.document import DocumentContent, DocumentSection

CITATION_RE = re.compile(r"\[S(\d+)\s*[:\-–]\s*([^\]]{1,80})\]")


class SourceMapEntry(BaseModel):
    index: int
    id: str
    name: str
    locators: list[str]


class Citation(BaseModel):
    marker: str
    source_index: int
    locator: str
    document_id: str | None = None
    document_name: str | None = None
    section_id: str | None = None
    resolved_locator: str | None = None
    found: bool = False


def source_map(documents: list[DocumentContent]) -> list[SourceMapEntry]:
    return [
        SourceMapEntry(index=i + 1, id=d.id, name=d.display_name, locators=[s.locator for s in d.sections])
        for i, d in enumerate(documents)
    ]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def find_section(doc: DocumentContent, locator: str) -> DocumentSection | None:
    """Match a cited locator to a section: exact, then normalized, then contains."""
    want = _norm(locator)
    for s in doc.sections:
        if s.locator == locator:
            return s
    for s in doc.sections:
        if _norm(s.locator) == want or _norm(s.title) == want:
            return s
    for s in doc.sections:
        ns = _norm(s.locator)
        if want and (want in ns or ns in want):
            return s
    # Models routinely drop numbering ("Heading: The artificial neuron" for
    # "Heading: 1. The artificial neuron"), so accept a locator whose words are
    # all present in the real one.
    want_words = [w for w in want.split() if len(w) > 1]
    if len(want_words) >= 2:
        for s in doc.sections:
            section_words = set(_norm(s.locator).split())
            if all(w in section_words for w in want_words):
                return s

    # The model may cite a heading that lives inside a section (e.g. "Evaluation metrics" on Page 3).
    if len(want) >= 4:
        for s in doc.sections:
            if want in _norm(s.markdown[:400]):
                return s
    # "Page 3" vs "page 3" vs "p. 3" style numbers
    m = re.search(r"(\d+)", locator)
    if m:
        num = m.group(1)
        for s in doc.sections:
            if re.search(rf"\b{num}\b", s.locator):
                return s
    return None


def extract_citations(answer: str, documents: list[DocumentContent]) -> list[Citation]:
    seen: dict[str, Citation] = {}
    for m in CITATION_RE.finditer(answer):
        marker = m.group(0)
        if marker in seen:
            continue
        idx = int(m.group(1))
        locator = m.group(2).strip()
        c = Citation(marker=marker, source_index=idx, locator=locator)
        if 1 <= idx <= len(documents):
            doc = documents[idx - 1]
            c.document_id = doc.id
            c.document_name = doc.display_name
            sec = find_section(doc, locator)
            if sec is not None:
                c.section_id = sec.section_id
                c.resolved_locator = sec.locator
                c.found = True
        seen[marker] = c
    return list(seen.values())


def citation_stats(citations: list[Citation]) -> dict[str, Any]:
    return {
        "total": len(citations),
        "resolved": sum(1 for c in citations if c.found),
        "unresolved": [c.marker for c in citations if not c.found],
    }
