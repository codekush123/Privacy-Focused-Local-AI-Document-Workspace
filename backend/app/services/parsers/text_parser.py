"""TXT, Markdown and pasted-text parsers."""
from __future__ import annotations

from pathlib import Path

from app.models.document import DocumentSection, SourceType

from .base import BaseParser, ParseError, make_section


def read_text_with_fallback(path: Path) -> str:
    data = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    try:
        from charset_normalizer import from_bytes

        best = from_bytes(data).best()
        if best is not None:
            return str(best)
    except Exception:  # noqa: BLE001
        pass
    return data.decode("latin-1", errors="replace")


class TxtParser(BaseParser):
    source_type = SourceType.txt
    extensions = ("txt", "text", "log")

    def parse(self, path: Path, display_name: str) -> list[DocumentSection]:
        text = read_text_with_fallback(path)
        if not text.strip():
            raise ParseError("The text file is empty.")
        return [make_section(1, "Text", "Text", text, characters=len(text))]


class MarkdownParser(BaseParser):
    source_type = SourceType.md
    extensions = ("md", "markdown")

    def parse(self, path: Path, display_name: str) -> list[DocumentSection]:
        text = read_text_with_fallback(path)
        if not text.strip():
            raise ParseError("The Markdown file is empty.")
        # Keep the Markdown unchanged; record top-level headings as metadata.
        headings = [ln.lstrip("# ").strip() for ln in text.splitlines() if ln.startswith("#")]
        return [make_section(1, "Markdown", "Markdown", text, headings=headings[:50])]


class PastedTextParser(BaseParser):
    source_type = SourceType.text
    extensions = ()

    def parse(self, path: Path, display_name: str) -> list[DocumentSection]:
        text = read_text_with_fallback(path)
        if not text.strip():
            raise ParseError("The pasted text is empty.")
        return [make_section(1, "Pasted text", "Pasted text", text, characters=len(text))]
