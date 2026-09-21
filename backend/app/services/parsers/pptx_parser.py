"""PPTX parser using python-pptx.

Every slide becomes a section "Slide N" with the slide title, body text
(bullets preserved by paragraph level), tables and speaker notes. Images are
listed by count only; they are not interpreted.
"""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.util import Emu

from app.models.document import DocumentSection, SourceType

from .base import BaseParser, ParseError, make_section, markdown_table


def _iter_shapes(shapes):
    for sh in shapes:
        if sh.shape_type == MSO_SHAPE_TYPE.GROUP:
            yield from _iter_shapes(sh.shapes)
        else:
            yield sh


def _text_frame_md(tf, is_title: bool = False) -> list[str]:
    lines: list[str] = []
    for para in tf.paragraphs:
        text = "".join(r.text for r in para.runs).strip() or para.text.strip()
        if not text:
            continue
        if is_title:
            lines.append(text)
        else:
            indent = "  " * max(para.level or 0, 0)
            lines.append(f"{indent}* {text}")
    return lines


class PptxParser(BaseParser):
    source_type = SourceType.pptx
    extensions = ("pptx",)

    def parse(self, path: Path, display_name: str) -> list[DocumentSection]:
        try:
            prs = Presentation(str(path))
        except Exception as exc:  # noqa: BLE001
            raise ParseError("The PowerPoint file could not be opened. Is it a valid .pptx file?") from exc

        sections: list[DocumentSection] = []
        for idx, slide in enumerate(prs.slides, start=1):
            title = ""
            body: list[str] = []
            tables: list[str] = []
            image_count = 0
            title_shape = slide.shapes.title
            if title_shape is not None and title_shape.has_text_frame:
                title = title_shape.text_frame.text.strip().replace("\n", " ")

            # sort shapes top-to-bottom, left-to-right for a sensible reading order
            shapes = sorted(
                _iter_shapes(slide.shapes),
                key=lambda s: (Emu(s.top or 0), Emu(s.left or 0)),
            )
            for sh in shapes:
                if title_shape is not None and sh.shape_id == title_shape.shape_id:
                    continue
                if sh.shape_type == MSO_SHAPE_TYPE.PICTURE:
                    image_count += 1
                    continue
                if getattr(sh, "has_table", False) and sh.has_table:
                    rows = [[c.text.strip() for c in r.cells] for r in sh.table.rows]
                    if rows:
                        tables.append(markdown_table(rows[0], rows[1:]))
                    continue
                if sh.has_text_frame:
                    body.extend(_text_frame_md(sh.text_frame))

            notes = ""
            if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
                notes = slide.notes_slide.notes_text_frame.text.strip()

            parts: list[str] = []
            if body:
                parts.append("\n".join(body))
            for t in tables:
                parts.append("### Table\n\n" + t)
            if notes:
                parts.append("### Speaker notes\n\n" + notes)
            if image_count:
                parts.append(f"_({image_count} image(s) on this slide, not interpreted)_")
            md = "\n\n".join(parts).strip() or "_(no text on this slide)_"
            sections.append(
                make_section(
                    len(sections) + 1,
                    title or f"Slide {idx}",
                    f"Slide {idx}",
                    md,
                    slide=idx,
                    images=image_count,
                )
            )
        if not sections:
            raise ParseError("The presentation contains no slides.")
        return sections

    def to_document(self, path, original_filename, display_name=None):
        doc = super().to_document(path, original_filename, display_name)
        doc.metadata["slide_count"] = len(doc.sections)
        return doc
