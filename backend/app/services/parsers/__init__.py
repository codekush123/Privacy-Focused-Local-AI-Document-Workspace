"""Parser registry: maps file extensions to parser implementations."""
from __future__ import annotations

from pathlib import Path

from app.models.document import DocumentContent, SourceType

from .base import BaseParser, ParseError
from .csv_parser import CsvParser
from .docx_parser import DocxParser
from .html_parser import HtmlParser
from .pdf_parser import PdfParser
from .pptx_parser import PptxParser
from .text_parser import MarkdownParser, PastedTextParser, TxtParser
from .xlsx_parser import XlsxParser

PARSERS: list[BaseParser] = [
    TxtParser(),
    MarkdownParser(),
    HtmlParser(),
    CsvParser(),
    DocxParser(),
    PdfParser(),
    XlsxParser(),
    PptxParser(),
]

_BY_EXT: dict[str, BaseParser] = {ext: p for p in PARSERS for ext in p.extensions}
SUPPORTED_EXTENSIONS: tuple[str, ...] = tuple(sorted(_BY_EXT))


def parser_for_extension(ext: str) -> BaseParser:
    ext = ext.lower().lstrip(".")
    try:
        return _BY_EXT[ext]
    except KeyError as exc:
        raise ParseError(
            f"This file type (.{ext or '?'}) is not supported. Supported: {', '.join(SUPPORTED_EXTENSIONS)}."
        ) from exc


def parse_file(path: Path, original_filename: str, display_name: str | None = None) -> DocumentContent:
    parser = parser_for_extension(Path(original_filename).suffix)
    return parser.to_document(path, original_filename, display_name)


def parse_pasted_text(path: Path, display_name: str) -> DocumentContent:
    return PastedTextParser().to_document(path, display_name, display_name)


__all__ = [
    "PARSERS",
    "SUPPORTED_EXTENSIONS",
    "ParseError",
    "SourceType",
    "parse_file",
    "parse_pasted_text",
    "parser_for_extension",
]
