"""HTML parser: local .html/.htm files and fetched web pages.

Uses BeautifulSoup to strip scripts, styles, navigation and hidden content,
then markdownify to convert the remaining structure (headings, paragraphs,
lists, tables, links) into Markdown. JavaScript is never executed.
"""
from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup, Comment
from markdownify import markdownify as md

from app.models.document import DocumentSection, SourceType

from .base import BaseParser, ParseError, make_section
from .text_parser import read_text_with_fallback

NOISE_TAGS = (
    "script",
    "style",
    "noscript",
    "iframe",
    "svg",
    "canvas",
    "template",
    "nav",
    "header",
    "footer",
    "aside",
    "form",
    "button",
    "input",
    "select",
    "textarea",
)
_HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.I)
_NOISE_CLASS = re.compile(r"\b(nav|menu|sidebar|footer|cookie|banner|advert|ads?|breadcrumb|popup|modal)\b", re.I)


def html_to_markdown(html: str) -> tuple[str, str]:
    """Return (title, markdown) for an HTML string."""
    soup = BeautifulSoup(html, "lxml")
    title = (soup.title.string.strip() if soup.title and soup.title.string else "") or ""

    for tag in soup.find_all(NOISE_TAGS):
        tag.decompose()
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    for tag in soup.find_all(True):
        if tag.has_attr("hidden") or tag.get("aria-hidden") == "true":
            tag.decompose()
            continue
        style = tag.get("style")
        if style and _HIDDEN_STYLE.search(style):
            tag.decompose()
            continue
        # Attribute-based navigation noise (only for container elements).
        if tag.name in ("div", "section", "ul") and not tag.find(["h1", "h2", "h3", "p", "table"]):
            ident = " ".join([tag.get("id", ""), " ".join(tag.get("class", []) or []), tag.get("role", "")])
            if _NOISE_CLASS.search(ident):
                tag.decompose()

    root = soup.find("main") or soup.find("article") or soup.body or soup
    text = md(str(root), heading_style="ATX", bullets="*", strip=["img"])
    # Collapse excessive blank lines and trailing spaces.
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return title, text


class HtmlParser(BaseParser):
    source_type = SourceType.html
    extensions = ("html", "htm", "xhtml")

    def parse(self, path: Path, display_name: str) -> list[DocumentSection]:
        html = read_text_with_fallback(path)
        title, text = html_to_markdown(html)
        if not text.strip():
            raise ParseError("No readable content was found in the HTML file.")
        return [make_section(1, title or display_name, f"Page: {title or display_name}", text, page_title=title)]
