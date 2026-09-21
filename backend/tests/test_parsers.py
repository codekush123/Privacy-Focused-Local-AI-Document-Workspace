"""Parser tests: every fixture must yield the known verification phrase in
normalized Markdown, at the expected locator."""
from __future__ import annotations

import pytest

from app.services.parsers import ParseError, parse_file, parser_for_extension
from app.services.parsers.csv_parser import sniff_delimiter
from app.services.parsers.html_parser import html_to_markdown

from .conftest import MULTILINGUAL, PHRASE


@pytest.mark.parametrize(
    "name,source_type",
    [
        ("sample.txt", "txt"),
        ("sample.md", "md"),
        ("sample.html", "html"),
        ("sample.csv", "csv"),
        ("sample.docx", "docx"),
        ("sample.pdf", "pdf"),
        ("sample.xlsx", "xlsx"),
        ("sample.pptx", "pptx"),
    ],
)
def test_phrase_survives_conversion(fixtures, name, source_type):
    doc = parse_file(fixtures / name, name)
    assert doc.source_type.value == source_type
    assert doc.status == "ready"
    assert PHRASE in doc.full_markdown
    assert doc.full_markdown.startswith(f"# Source: {name}")
    assert doc.character_count == len(doc.full_markdown)
    assert doc.sections, "at least one section expected"


def test_txt_and_md_keep_content(fixtures):
    md = parse_file(fixtures / "sample.md", "sample.md")
    assert "# Markdown Title" in md.full_markdown
    assert "- item one" in md.full_markdown  # Markdown left mostly unchanged
    txt = parse_file(fixtures / "sample.txt", "sample.txt")
    assert "Plain text fixture." in txt.full_markdown


def test_html_removes_noise_and_keeps_structure(fixtures):
    doc = parse_file(fixtures / "sample.html", "sample.html")
    text = doc.full_markdown
    assert "SCRIPT_MARKER" not in text
    assert "NAV_MARKER" not in text
    assert "FOOTER_MARKER" not in text
    assert "HIDDEN_MARKER" not in text
    assert "# HTML Heading" in text
    assert "* alpha" in text
    assert "| Name | Score |" in text
    assert doc.sections[0].locator == "Page: Fixture Page"


def test_html_to_markdown_handles_plain_fragment():
    title, text = html_to_markdown("<p>Hello <b>bold</b></p>")
    assert title == ""
    assert "Hello **bold**" in text


def test_csv_table_and_delimiters(fixtures):
    doc = parse_file(fixtures / "sample.csv", "sample.csv")
    assert "| Name | Score | Grade |" in doc.full_markdown
    assert "| Smith, Jr. | 88 | B |" in doc.full_markdown  # quoted comma preserved
    assert doc.metadata["row_count"] == 5
    assert doc.metadata["column_count"] == 3
    assert doc.sections[0].locator == "Rows 1-5"
    semi = parse_file(fixtures / "semicolon.csv", "semicolon.csv")
    assert semi.metadata["delimiter"] == ";"
    assert "| 1 | BLUE ELEPHANT 1947 |" in semi.full_markdown
    assert sniff_delimiter("a\tb\n1\t2\n") == "\t"


def test_docx_headings_lists_tables(fixtures):
    doc = parse_file(fixtures / "sample.docx", "sample.docx")
    locators = [s.locator for s in doc.sections]
    assert "Heading: Introduction" in locators
    assert "Heading: Details" in locators
    assert "* First bullet\n* Second bullet" in doc.full_markdown
    assert "| Color | TABLE_CELL_VALUE |" in doc.full_markdown


def test_pdf_page_boundaries(fixtures):
    doc = parse_file(fixtures / "sample.pdf", "sample.pdf")
    assert [s.locator for s in doc.sections] == ["Page 1", "Page 2", "Page 3"]
    assert PHRASE in doc.sections[2].markdown
    assert PHRASE not in doc.sections[0].markdown
    assert doc.metadata["page_count"] == 3


def test_xlsx_sheets(fixtures):
    doc = parse_file(fixtures / "sample.xlsx", "sample.xlsx")
    by_loc = {s.locator: s for s in doc.sections}
    assert set(by_loc) == {"Sheet: Students", "Sheet: Results"}
    assert "| Ada | 95 | A |" in by_loc["Sheet: Students"].markdown
    assert PHRASE in by_loc["Sheet: Results"].markdown
    assert doc.metadata["sheets"] == ["Students", "Results"]


def test_pptx_slide_two_has_phrase(fixtures):
    doc = parse_file(fixtures / "sample.pptx", "sample.pptx")
    assert doc.sections[0].locator == "Slide 1"
    assert doc.sections[1].locator == "Slide 2"
    assert PHRASE in doc.sections[1].markdown
    assert PHRASE not in doc.sections[0].markdown
    assert "## Slide 2 - Second Slide" in doc.full_markdown
    assert "| PPTX_TABLE_CELL | x |" in doc.full_markdown


@pytest.mark.parametrize(
    "name", ["sample.txt", "sample.md", "sample.html", "sample.csv", "sample.docx", "sample.xlsx", "sample.pptx"]
)
def test_multilingual_characters_survive(fixtures, name):
    """Smoke test only: characters from several scripts must survive parsing."""
    doc = parse_file(fixtures / name, name)
    for lang, sample in MULTILINGUAL.items():
        assert sample in doc.full_markdown, f"{lang} text lost in {name}"


def test_unsupported_extension():
    with pytest.raises(ParseError):
        parser_for_extension("exe")


def test_corrupt_office_file(tmp_path):
    bad = tmp_path / "bad.docx"
    bad.write_bytes(b"this is not a zip")
    with pytest.raises(ParseError):
        parse_file(bad, "bad.docx")
