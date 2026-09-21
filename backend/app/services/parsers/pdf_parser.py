"""PDF parser using PyMuPDF / PyMuPDF4LLM.

PyMuPDF4LLM converts each page to Markdown (headings, lists, tables). Every
page becomes its own section with locator "Page N" so page boundaries stay
visible in the normalized output.

OCR: pages without a text layer are reported in metadata. If
``LDW_PDF_OCR=true`` and Tesseract is available, PyMuPDF's OCR text page is
used for such pages. OCR is optional and never blocks parsing.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import pymupdf
import pymupdf4llm

from app.models.document import DocumentSection, SourceType

from .base import BaseParser, ParseError, make_section

log = logging.getLogger(__name__)

OCR_ENABLED = os.environ.get("LDW_PDF_OCR", "false").lower() in ("1", "true", "yes")


def _ocr_page(page: pymupdf.Page) -> str:
    """Best-effort OCR through PyMuPDF (requires Tesseract). Returns '' on failure."""
    try:
        tp = page.get_textpage_ocr(full=True)
        return page.get_text(textpage=tp) or ""
    except Exception as exc:  # noqa: BLE001
        log.info("OCR unavailable for page %s: %s", page.number + 1, exc)
        return ""


class PdfParser(BaseParser):
    source_type = SourceType.pdf
    extensions = ("pdf",)

    def parse(self, path: Path, display_name: str) -> list[DocumentSection]:
        try:
            doc = pymupdf.open(str(path))
        except Exception as exc:  # noqa: BLE001
            raise ParseError("The PDF could not be read. Is it a valid PDF file?") from exc
        if doc.is_encrypted and not doc.authenticate(""):
            raise ParseError("The PDF is password protected.")
        try:
            chunks = pymupdf4llm.to_markdown(doc, page_chunks=True, show_progress=False)
        except Exception as exc:  # noqa: BLE001
            log.warning("pymupdf4llm failed for %s (%s); falling back to plain text", display_name, exc)
            chunks = [{"text": page.get_text(), "metadata": {"page_number": page.number + 1}} for page in doc]

        sections: list[DocumentSection] = []
        empty_pages: list[int] = []
        for i, chunk in enumerate(chunks):
            page_no = (chunk.get("metadata") or {}).get("page_number") or (i + 1)
            text = (chunk.get("text") or "").strip()
            ocr_used = False
            if not text:
                if OCR_ENABLED:
                    text = _ocr_page(doc[page_no - 1]).strip()
                    ocr_used = bool(text)
                if not text:
                    empty_pages.append(page_no)
                    text = "_(no extractable text on this page - it may be an image or scan)_"
            sections.append(
                make_section(len(sections) + 1, f"Page {page_no}", f"Page {page_no}", text, page=page_no, ocr=ocr_used)
            )
        page_count = doc.page_count
        doc.close()
        if not sections:
            raise ParseError("The PDF contains no pages.")
        sections[0].metadata.update({"page_count": page_count, "pages_without_text": empty_pages})
        if empty_pages and len(empty_pages) == page_count:
            log.info("PDF %s has no text layer on any page (OCR %s)", display_name, "on" if OCR_ENABLED else "off")
        return sections

    def to_document(self, path, original_filename, display_name=None):
        doc = super().to_document(path, original_filename, display_name)
        first = doc.sections[0].metadata if doc.sections else {}
        doc.metadata.update({k: first.get(k) for k in ("page_count", "pages_without_text") if k in first})
        return doc
