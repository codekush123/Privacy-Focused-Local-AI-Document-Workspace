"""Convert a Markdown chat answer into .docx, .pdf or .tex (LaTeX).

These exporters take the model's normal Markdown answer (no second model call)
and render it with a small block-level Markdown parser that understands
headings, paragraphs, bullet / numbered lists, tables, fenced code and
blockquotes, plus inline bold / italic / code.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from pathlib import Path

import markdown as md_lib
import pymupdf
from docx import Document
from docx.shared import Pt, RGBColor

# ------------------------------------------------------------ block parser --

@dataclass
class Block:
    kind: str  # heading | paragraph | bullets | numbered | table | code | quote
    text: str = ""
    level: int = 1
    items: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)


_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def _split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", line)]


def parse_markdown(text: str) -> list[Block]:
    lines = text.replace("\r\n", "\n").split("\n")
    blocks: list[Block] = []
    i = 0
    para: list[str] = []

    def flush_para():
        if para:
            blocks.append(Block("paragraph", " ".join(s.strip() for s in para)))
            para.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            flush_para()
            i += 1
            continue
        if stripped.startswith("```"):
            flush_para()
            code: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            blocks.append(Block("code", "\n".join(code)))
            i += 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            flush_para()
            blocks.append(Block("heading", m.group(2).strip().rstrip("#").strip(), level=len(m.group(1))))
            i += 1
            continue
        if stripped.startswith("|") and i + 1 < len(lines) and _TABLE_SEP.match(lines[i + 1]):
            flush_para()
            rows = [_split_row(stripped)]
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(_split_row(lines[i]))
                i += 1
            blocks.append(Block("table", rows=rows))
            continue
        if re.match(r"^[-*+]\s+", stripped):
            flush_para()
            items: list[str] = []
            while i < len(lines) and re.match(r"^\s*[-*+]\s+", lines[i]):
                items.append(re.sub(r"^\s*[-*+]\s+", "", lines[i]).strip())
                i += 1
            blocks.append(Block("bullets", items=items))
            continue
        if re.match(r"^\d+[.)]\s+", stripped):
            flush_para()
            items = []
            while i < len(lines) and re.match(r"^\s*\d+[.)]\s+", lines[i]):
                items.append(re.sub(r"^\s*\d+[.)]\s+", "", lines[i]).strip())
                i += 1
            blocks.append(Block("numbered", items=items))
            continue
        if stripped.startswith(">"):
            flush_para()
            quote: list[str] = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            blocks.append(Block("quote", " ".join(quote)))
            continue
        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", stripped):
            flush_para()
            i += 1
            continue
        para.append(line)
        i += 1
    flush_para()
    return blocks


# ------------------------------------------------------------ inline runs --

_INLINE = re.compile(r"(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`|\*[^*\s][^*]*\*|_[^_\s][^_]*_)")


def inline_runs(text: str) -> list[tuple[str, str]]:
    """Split text into (style, text) tuples; style in {'', 'bold', 'italic', 'code'}."""
    runs: list[tuple[str, str]] = []
    pos = 0
    for m in _INLINE.finditer(text):
        if m.start() > pos:
            runs.append(("", text[pos : m.start()]))
        tok = m.group(0)
        if tok.startswith("**") or tok.startswith("__"):
            runs.append(("bold", tok[2:-2]))
        elif tok.startswith("`"):
            runs.append(("code", tok[1:-1]))
        else:
            runs.append(("italic", tok[1:-1]))
        pos = m.end()
    if pos < len(text):
        runs.append(("", text[pos:]))
    # strip link syntax [text](url) -> text (url)
    return [(s, re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", t)) for s, t in runs]


def plain(text: str) -> str:
    return "".join(t for _, t in inline_runs(text))


# ------------------------------------------------------------------- DOCX --

def _add_runs(paragraph, text: str) -> None:
    for style, chunk in inline_runs(text):
        run = paragraph.add_run(chunk)
        if style == "bold":
            run.bold = True
        elif style == "italic":
            run.italic = True
        elif style == "code":
            run.font.name = "Consolas"


def markdown_to_docx(text: str, out_path: Path, title: str | None = None, sources: list[str] | None = None) -> Path:
    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)
    if title:
        doc.add_heading(title, level=0)
    for b in parse_markdown(text):
        if b.kind == "heading":
            doc.add_heading(plain(b.text), level=min(b.level, 4))
        elif b.kind == "paragraph":
            _add_runs(doc.add_paragraph(), b.text)
        elif b.kind == "bullets":
            for it in b.items:
                _add_runs(doc.add_paragraph(style="List Bullet"), it)
        elif b.kind == "numbered":
            for it in b.items:
                _add_runs(doc.add_paragraph(style="List Number"), it)
        elif b.kind == "quote":
            _add_runs(doc.add_paragraph(style="Intense Quote"), b.text)
        elif b.kind == "code":
            p = doc.add_paragraph()
            r = p.add_run(b.text)
            r.font.name = "Consolas"
            r.font.size = Pt(9)
        elif b.kind == "table" and b.rows:
            ncols = max(len(r) for r in b.rows)
            t = doc.add_table(rows=0, cols=ncols)
            t.style = "Light Grid Accent 1"
            for ri, row in enumerate(b.rows):
                cells = t.add_row().cells
                for ci in range(ncols):
                    cells[ci].text = ""
                    _add_runs(cells[ci].paragraphs[0], row[ci] if ci < len(row) else "")
                    if ri == 0:
                        for run in cells[ci].paragraphs[0].runs:
                            run.bold = True
            doc.add_paragraph()
    if sources:
        p = doc.add_paragraph()
        r = p.add_run("Sources: " + ", ".join(sources))
        r.font.size = Pt(8)
        r.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return out_path


# -------------------------------------------------------------------- PDF --

_PDF_CSS = """
body { font-family: sans-serif; font-size: 11pt; line-height: 1.4; }
h1 { font-size: 20pt; } h2 { font-size: 16pt; } h3 { font-size: 13pt; }
table { border-collapse: collapse; margin: 6pt 0; }
th, td { border: 1px solid #999; padding: 3pt 6pt; font-size: 10pt; }
th { background-color: #e8eef8; font-weight: bold; }
code, pre { font-family: monospace; font-size: 9.5pt; }
pre { background-color: #f2f2f2; padding: 6pt; }
blockquote { color: #555; border-left: 3px solid #bbb; padding-left: 8pt; margin-left: 0; }
.sources { color: #777; font-size: 8pt; margin-top: 18pt; }
"""


def markdown_to_pdf(text: str, out_path: Path, title: str | None = None, sources: list[str] | None = None) -> Path:
    body = md_lib.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])
    parts = []
    if title:
        parts.append(f"<h1>{html.escape(title)}</h1>")
    parts.append(body)
    if sources:
        parts.append('<p class="sources">Sources: ' + html.escape(", ".join(sources)) + "</p>")
    story = pymupdf.Story(html="<body>" + "".join(parts) + "</body>", user_css=_PDF_CSS)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = pymupdf.DocumentWriter(str(out_path))
    page_rect = pymupdf.paper_rect("a4")
    content = page_rect + (50, 50, -50, -50)
    more = True
    while more:
        dev = writer.begin_page(page_rect)
        more, _ = story.place(content)
        story.draw(dev)
        writer.end_page()
    writer.close()
    return out_path


# ------------------------------------------------------------------ LaTeX --

_LATEX_SPECIAL = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
    "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}


def latex_escape(s: str) -> str:
    return "".join(_LATEX_SPECIAL.get(ch, ch) for ch in s)


def _latex_inline(text: str) -> str:
    out = []
    for style, chunk in inline_runs(text):
        esc = latex_escape(chunk)
        if style == "bold":
            out.append(r"\textbf{" + esc + "}")
        elif style == "italic":
            out.append(r"\emph{" + esc + "}")
        elif style == "code":
            out.append(r"\texttt{" + esc + "}")
        else:
            out.append(esc)
    return "".join(out)


_SECTION = {1: "section", 2: "subsection", 3: "subsubsection", 4: "paragraph", 5: "subparagraph", 6: "subparagraph"}


def markdown_to_latex(text: str, title: str | None = None, sources: list[str] | None = None) -> str:
    lines = [
        r"\documentclass[11pt,a4paper]{article}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{booktabs}",
        r"\usepackage{longtable}",
        r"\usepackage{hyperref}",
        r"\usepackage[margin=2.5cm]{geometry}",
        r"\setlength{\parskip}{6pt}",
        r"\setlength{\parindent}{0pt}",
    ]
    if title:
        lines += [r"\title{" + latex_escape(title) + "}", r"\date{}", r"\author{}"]
    lines += ["", r"\begin{document}"]
    if title:
        lines.append(r"\maketitle")
    lines.append("")
    for b in parse_markdown(text):
        if b.kind == "heading":
            lines.append("\\" + _SECTION.get(b.level, "paragraph") + "*{" + _latex_inline(b.text) + "}")
        elif b.kind == "paragraph":
            lines.append(_latex_inline(b.text))
        elif b.kind in ("bullets", "numbered"):
            env = "itemize" if b.kind == "bullets" else "enumerate"
            lines.append(r"\begin{" + env + "}")
            lines += ["  \\item " + _latex_inline(it) for it in b.items]
            lines.append(r"\end{" + env + "}")
        elif b.kind == "quote":
            lines += [r"\begin{quote}", _latex_inline(b.text), r"\end{quote}"]
        elif b.kind == "code":
            lines += [r"\begin{verbatim}", b.text, r"\end{verbatim}"]
        elif b.kind == "table" and b.rows:
            ncols = max(len(r) for r in b.rows)
            lines.append(r"\begin{longtable}{" + "l" * ncols + "}")
            lines.append(r"\toprule")
            for ri, row in enumerate(b.rows):
                cells = [_latex_inline(row[c] if c < len(row) else "") for c in range(ncols)]
                if ri == 0:
                    cells = [r"\textbf{" + c + "}" for c in cells]
                lines.append(" & ".join(cells) + r" \\")
                if ri == 0:
                    lines.append(r"\midrule")
            lines += [r"\bottomrule", r"\end{longtable}"]
        lines.append("")
    if sources:
        lines += [r"\vspace{1em}", r"{\small\textcolor{gray}{Sources: " + latex_escape(", ".join(sources)) + "}}"]
        if r"\usepackage{xcolor}" not in lines:
            lines.insert(1, r"\usepackage{xcolor}")
    lines.append(r"\end{document}")
    return "\n".join(lines) + "\n"


def write_latex(text: str, out_path: Path, title: str | None = None, sources: list[str] | None = None) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown_to_latex(text, title, sources), encoding="utf-8")
    return out_path
