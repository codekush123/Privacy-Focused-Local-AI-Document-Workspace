"""CSV parser.

Detects the delimiter, keeps the header row and converts all data rows to
Markdown tables. Rows are grouped into sections ("Rows 1-100", ...) so large
files stay navigable. Nothing is dropped: if the result is too large for the
model context, the context check reports that to the user instead.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

from app.models.document import DocumentSection, SourceType

from .base import BaseParser, ParseError, make_section, markdown_table
from .text_parser import read_text_with_fallback

ROWS_PER_SECTION = 100
CANDIDATE_DELIMITERS = ",;\t|"


def sniff_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=CANDIDATE_DELIMITERS).delimiter
    except csv.Error:
        # Fallback: the candidate that appears most often on the first line.
        first = sample.splitlines()[0] if sample else ""
        return max(CANDIDATE_DELIMITERS, key=first.count) if first else ","


class CsvParser(BaseParser):
    source_type = SourceType.csv
    extensions = ("csv", "tsv")

    def parse(self, path: Path, display_name: str) -> list[DocumentSection]:
        text = read_text_with_fallback(path)
        if not text.strip():
            raise ParseError("The CSV file is empty.")
        delimiter = "\t" if path.suffix.lower() == ".tsv" else sniff_delimiter(text[:20000])
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        rows = [r for r in reader if any(c.strip() for c in r)]
        if not rows:
            raise ParseError("The CSV file contains no data rows.")
        headers = [h.strip() for h in rows[0]]
        data = rows[1:]
        sections: list[DocumentSection] = []
        for i in range(0, max(len(data), 1), ROWS_PER_SECTION):
            chunk = data[i : i + ROWS_PER_SECTION]
            start, end = i + 1, i + len(chunk)
            locator = f"Rows {start}-{end}" if chunk else "Header only"
            sections.append(
                make_section(
                    len(sections) + 1,
                    locator,
                    locator,
                    markdown_table(headers, chunk),
                    row_start=start,
                    row_end=end,
                )
            )
        # Attach global info to the first section so the document metadata can pick it up.
        sections[0].metadata.update(
            {"row_count": len(data), "column_count": len(headers), "columns": headers, "delimiter": delimiter}
        )
        return sections

    def to_document(self, path, original_filename, display_name=None):
        doc = super().to_document(path, original_filename, display_name)
        first = doc.sections[0].metadata if doc.sections else {}
        doc.metadata.update({k: first.get(k) for k in ("row_count", "column_count", "delimiter") if k in first})
        return doc
