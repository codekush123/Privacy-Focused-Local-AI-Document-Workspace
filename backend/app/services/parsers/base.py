"""Parser base class and shared helpers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.models.document import DocumentContent, DocumentSection, SourceType
from app.utils.files import new_id


class ParseError(Exception):
    """User-facing parse failure."""


class BaseParser(ABC):
    source_type: SourceType
    extensions: tuple[str, ...] = ()

    @abstractmethod
    def parse(self, path: Path, display_name: str) -> list[DocumentSection]:
        """Return the sections of the document in reading order."""

    def to_document(self, path: Path, original_filename: str, display_name: str | None = None) -> DocumentContent:
        display_name = display_name or original_filename
        try:
            sections = self.parse(path, display_name)
        except ParseError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ParseError(f"The {self.source_type.value.upper()} file could not be read: {exc}") from exc
        doc = DocumentContent(
            id=new_id(),
            original_filename=original_filename,
            source_type=self.source_type,
            display_name=display_name,
            source_path=str(path),
            sections=sections,
            size_bytes=path.stat().st_size if path.exists() else 0,
        )
        return doc.finalize()


def make_section(index: int, title: str, locator: str, markdown: str, **meta) -> DocumentSection:
    return DocumentSection(
        section_id=f"s{index}",
        title=title,
        locator=locator,
        markdown=markdown,
        metadata=meta,
    )


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a Markdown table. Cells are escaped for pipes/newlines."""

    def esc(v) -> str:
        s = "" if v is None else str(v)
        return s.replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()

    if not headers:
        headers = [f"Column {i + 1}" for i in range(len(rows[0]) if rows else 0)]
    width = len(headers)
    lines = ["| " + " | ".join(esc(h) or " " for h in headers) + " |"]
    lines.append("|" + "|".join([" --- "] * width) + "|")
    for r in rows:
        cells = [esc(c) for c in r] + [""] * (width - len(r))
        lines.append("| " + " | ".join(cells[:width]) + " |")
    return "\n".join(lines)
