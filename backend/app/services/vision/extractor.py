"""Extract figures from documents so a vision model can describe them.

Two kinds of figure are collected:

* **embedded images** - bitmaps stored inside a PDF, PPTX or DOCX file.
* **rendered pages/slides** - many charts in PDFs are vector drawings rather
  than bitmaps, and slides are layouts rather than pictures. Pages that carry
  little text or a lot of vector drawing are therefore rendered to an image so
  the chart itself can be looked at.

Every figure is normalised to PNG, downscaled to ``vision_max_image_px`` and
stored under ``data/images/<document_id>/``. Nothing leaves the machine.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pymupdf
from docx import Document as load_docx
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pydantic import BaseModel, Field

from app.config import settings
from app.models.document import DocumentContent
from app.utils.files import safe_child

log = logging.getLogger(__name__)

# Heuristics for "this page contains a figure that is not a bitmap".
# Deliberately conservative: a page is rendered only when it is mostly graphic
# (very little text) or contains a lot of vector drawing (a diagram). Pages of
# normal prose with a few rules or code-block backgrounds are not figures.
# When automatic detection is not enough the user can request every page.
SPARSE_TEXT_CHARS = 220
MANY_DRAWINGS = 60
# Drawing rectangles outside this size range are page backgrounds, clip boxes
# or hairlines rather than figure content.
MAX_DRAWING_AREA_RATIO = 0.6
MIN_DRAWING_AREA_RATIO = 0.0001
RENDER_DPI = 150


class ImageRecord(BaseModel):
    id: str
    document_id: str
    section_id: str | None = None
    locator: str = ""
    kind: str = "embedded"  # embedded | page_render | slide_render
    filename: str = ""
    width: int = 0
    height: int = 0
    described: bool = False
    figure_type: str = ""  # chart | diagram | photo | screenshot | table | formula | other
    title: str = ""
    description: str = ""
    text_in_image: str = ""
    data_points: list[str] = Field(default_factory=list)
    accepted: bool = True

    @property
    def url(self) -> str:
        return f"/api/vision/image/{self.document_id}/{self.id}"


class VisionError(Exception):
    pass


def images_dir_for(document_id: str) -> Path:
    d = safe_child(settings.images_dir, document_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def image_path(document_id: str, filename: str) -> Path:
    return safe_child(images_dir_for(document_id), filename)


def _save_pixmap(pix: pymupdf.Pixmap, out: Path) -> tuple[int, int]:
    """Downscale if needed, drop alpha/CMYK, write PNG. Returns (w, h)."""
    if pix.colorspace is None or pix.colorspace.n > 3 or pix.alpha:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    # shrink() halves the dimensions; repeat until the longest edge fits the limit
    limit = settings.vision_max_image_px
    while max(pix.width, pix.height) > limit and min(pix.width, pix.height) > 2:
        pix.shrink(1)
    out.write_bytes(pix.tobytes("png"))
    return pix.width, pix.height


def _pixmap_from_bytes(blob: bytes) -> pymupdf.Pixmap | None:
    try:
        return pymupdf.Pixmap(blob)
    except Exception:  # noqa: BLE001 - unsupported/corrupt image
        return None


def _too_small(w: int, h: int) -> bool:
    return min(w, h) < settings.vision_min_image_px


def _meaningful_drawings(page: pymupdf.Page) -> int:
    """Count vector items that could be figure content (not backgrounds or rules)."""
    try:
        drawings = page.get_drawings()
    except Exception:  # noqa: BLE001
        return 0
    page_area = page.rect.get_area() or 1
    n = 0
    for d in drawings:
        rect = d["rect"] & page.rect  # clip to the page; some items extend far beyond it
        if rect.is_empty or rect.width <= 0 or rect.height <= 0:
            continue
        ratio = rect.get_area() / page_area
        if MIN_DRAWING_AREA_RATIO <= ratio <= MAX_DRAWING_AREA_RATIO:
            n += 1
    return n


def _page_has_vector_figure(page: pymupdf.Page) -> bool:
    """True when the page most likely shows a chart or diagram drawn as vectors."""
    if len(page.get_text().strip()) < SPARSE_TEXT_CHARS:
        return True
    return _meaningful_drawings(page) > MANY_DRAWINGS


# --------------------------------------------------------------------- PDF --
def _extract_pdf(doc: DocumentContent, path: Path, render_all: bool = False) -> list[ImageRecord]:
    records: list[ImageRecord] = []
    out_dir = images_dir_for(doc.id)
    pdf = pymupdf.open(str(path))
    try:
        by_page = {s.metadata.get("page"): s for s in doc.sections if s.metadata.get("page")}
        for page in pdf:
            page_no = page.number + 1
            section = by_page.get(page_no)
            locator = section.locator if section else f"Page {page_no}"
            sid = section.section_id if section else None

            for i, info in enumerate(page.get_images(full=True), start=1):
                if len(records) >= settings.vision_max_images_per_doc:
                    break
                xref = info[0]
                try:
                    pix = pymupdf.Pixmap(pdf, xref)
                except Exception:  # noqa: BLE001
                    continue
                if _too_small(pix.width, pix.height):
                    continue
                name = f"p{page_no:04d}_img{i}.png"
                w, h = _save_pixmap(pix, out_dir / name)
                records.append(ImageRecord(
                    id=name[:-4], document_id=doc.id, section_id=sid, locator=locator,
                    kind="embedded", filename=name, width=w, height=h,
                ))

            if (render_all or _page_has_vector_figure(page)) and len(records) < settings.vision_max_images_per_doc:
                name = f"p{page_no:04d}_page.png"
                pix = page.get_pixmap(dpi=RENDER_DPI)
                w, h = _save_pixmap(pix, out_dir / name)
                records.append(ImageRecord(
                    id=name[:-4], document_id=doc.id, section_id=sid, locator=locator,
                    kind="page_render", filename=name, width=w, height=h,
                ))
    finally:
        pdf.close()
    return records


# -------------------------------------------------------------------- PPTX --
def _iter_shapes(shapes):
    for sh in shapes:
        if sh.shape_type == MSO_SHAPE_TYPE.GROUP:
            yield from _iter_shapes(sh.shapes)
        else:
            yield sh


def _extract_pptx(doc: DocumentContent, path: Path, render_all: bool = False) -> list[ImageRecord]:
    records: list[ImageRecord] = []
    out_dir = images_dir_for(doc.id)
    prs = Presentation(str(path))
    by_slide = {s.metadata.get("slide"): s for s in doc.sections if s.metadata.get("slide")}
    for idx, slide in enumerate(prs.slides, start=1):
        section = by_slide.get(idx)
        locator = section.locator if section else f"Slide {idx}"
        sid = section.section_id if section else None
        n = 0
        has_chart = False
        for sh in _iter_shapes(slide.shapes):
            if len(records) >= settings.vision_max_images_per_doc:
                break
            if getattr(sh, "has_chart", False) and sh.has_chart:
                has_chart = True
                continue
            if sh.shape_type != MSO_SHAPE_TYPE.PICTURE:
                continue
            try:
                blob = sh.image.blob
            except Exception:  # noqa: BLE001
                continue
            pix = _pixmap_from_bytes(blob)
            if pix is None or _too_small(pix.width, pix.height):
                continue
            n += 1
            name = f"s{idx:04d}_img{n}.png"
            w, h = _save_pixmap(pix, out_dir / name)
            records.append(ImageRecord(
                id=name[:-4], document_id=doc.id, section_id=sid, locator=locator,
                kind="embedded", filename=name, width=w, height=h,
            ))
        if has_chart:
            # python-pptx cannot rasterise native charts; record the gap honestly.
            log.info("Slide %d of %s contains a native chart that cannot be rendered locally", idx, doc.display_name)
    return records


# -------------------------------------------------------------------- DOCX --
def _extract_docx(doc: DocumentContent, path: Path, render_all: bool = False) -> list[ImageRecord]:
    records: list[ImageRecord] = []
    out_dir = images_dir_for(doc.id)
    d = load_docx(str(path))
    by_title = {s.title: s for s in doc.sections}
    current = doc.sections[0] if doc.sections else None
    n = 0
    for child in d.element.body.iterchildren():
        if child.tag != qn("w:p"):
            continue
        p = Paragraph(child, d)
        text = p.text.strip()
        if text and text in by_title:
            current = by_title[text]
        for blip in child.iter(qn("a:blip")):
            if len(records) >= settings.vision_max_images_per_doc:
                break
            rid = blip.get(qn("r:embed"))
            if not rid:
                continue
            try:
                part = d.part.related_parts[rid]
                blob = part.blob
            except Exception:  # noqa: BLE001
                continue
            pix = _pixmap_from_bytes(blob)
            if pix is None or _too_small(pix.width, pix.height):
                continue
            n += 1
            name = f"d{n:04d}_img.png"
            w, h = _save_pixmap(pix, out_dir / name)
            records.append(ImageRecord(
                id=name[:-4], document_id=doc.id,
                section_id=current.section_id if current else None,
                locator=current.locator if current else "Document",
                kind="embedded", filename=name, width=w, height=h,
            ))
    return records


EXTRACTORS = {"pdf": _extract_pdf, "pptx": _extract_pptx, "docx": _extract_docx}


def extract_images(doc: DocumentContent, render_all: bool = False) -> list[ImageRecord]:
    """Extract and store figures for a document. Idempotent: re-extraction replaces.

    ``render_all`` renders every PDF page instead of only the pages that look
    like figures - useful when a chart sits on a page full of text.
    """
    kind = doc.source_type.value
    if kind not in EXTRACTORS:
        raise VisionError("Image analysis supports PDF, PowerPoint and Word documents.")
    if not doc.source_path or not Path(doc.source_path).exists():
        raise VisionError("The original file for this document is no longer available.")
    remove_images(doc.id)
    records = EXTRACTORS[kind](doc, Path(doc.source_path), render_all)
    log.info("Extracted %d figure(s) from %s", len(records), doc.display_name)
    return records


def load_records(doc: DocumentContent) -> list[ImageRecord]:
    return [ImageRecord.model_validate(r) for r in doc.metadata.get("images", [])]


def store_records(doc: DocumentContent, records: list[ImageRecord]) -> None:
    doc.metadata["images"] = [r.model_dump() for r in records]


def image_bytes(record: ImageRecord) -> bytes:
    path = image_path(record.document_id, record.filename)
    if not path.exists():
        raise VisionError("The extracted image file is missing. Run extraction again.")
    return path.read_bytes()


def remove_images(document_id: str) -> None:
    d = settings.images_dir / document_id
    if not d.exists():
        return
    for f in d.glob("*"):
        try:
            f.unlink()
        except OSError:  # noqa: PERF203
            pass
    try:
        d.rmdir()
    except OSError:
        pass


def summary(records: list[ImageRecord]) -> dict[str, Any]:
    return {
        "total": len(records),
        "described": sum(1 for r in records if r.described),
        "by_kind": {k: sum(1 for r in records if r.kind == k) for k in {r.kind for r in records}},
    }
