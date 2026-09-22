"""Figure extraction and local vision-language description."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services.document_store import document_store
from app.services.llm.client import LlamaServerError
from app.services.vision import captioner
from app.services.vision.extractor import (
    ImageRecord,
    VisionError,
    extract_images,
    image_path,
    load_records,
    store_records,
    summary,
)

from .common import ensure_ai_allowed, resolve_documents, to_http

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/vision", tags=["vision"])

SUPPORTED = {"pdf", "pptx", "docx"}


def _payload(doc, records: list[ImageRecord]) -> dict[str, Any]:
    return {
        "document_id": doc.id,
        "document_name": doc.display_name,
        "images": [{**r.model_dump(), "url": r.url} for r in records],
        "summary": summary(records),
    }


def _get_records(doc_id: str) -> tuple[Any, list[ImageRecord]]:
    doc = resolve_documents([doc_id])[0]
    return doc, load_records(doc)


@router.get("/status")
async def vision_status() -> dict[str, Any]:
    from app.services.llm.client import llm_client

    info = await llm_client.server_info()
    return {
        "available": info.reachable and info.supports_vision,
        "connected": info.reachable,
        "supports_vision": info.supports_vision,
        "model_name": info.model_name,
        "hint": (
            "Restart llama-server with a multimodal projector to enable figure analysis, e.g. "
            "llama-server -m <model>.gguf --mmproj <mmproj>.gguf -c 16384 --jinja"
        ),
        "supported_formats": sorted(SUPPORTED),
    }


@router.get("/{doc_id}")
async def get_figures(doc_id: str) -> dict[str, Any]:
    doc, records = _get_records(doc_id)
    return {**_payload(doc, records), "supported": doc.source_type.value in SUPPORTED}


@router.post("/{doc_id}/extract")
async def extract(doc_id: str, render_all: bool = False) -> dict[str, Any]:
    """Find figures. ``render_all=true`` renders every page of a PDF, not only figure-like pages."""
    doc = resolve_documents([doc_id])[0]
    try:
        records = extract_images(doc, render_all=render_all)
    except VisionError as exc:
        raise HTTPException(422, str(exc)) from exc
    store_records(doc, records)
    document_store.save(doc)
    return _payload(doc, records)


class DescribeRequest(BaseModel):
    image_ids: list[str] = Field(default_factory=list, description="Empty = describe every figure that has no description yet")
    redescribe: bool = False


@router.post("/{doc_id}/describe")
async def describe(doc_id: str, body: DescribeRequest) -> dict[str, Any]:
    ensure_ai_allowed()
    doc, records = _get_records(doc_id)
    if not records:
        raise HTTPException(422, "No figures have been extracted from this document yet.")
    try:
        await captioner.ensure_vision_available()
    except captioner.VisionUnavailable as exc:
        raise HTTPException(409, str(exc)) from exc

    wanted = [r for r in records if (not body.image_ids or r.id in body.image_ids) and (body.redescribe or not r.described)]
    described, failures = 0, []
    for record in wanted:
        try:
            spec = await captioner.describe_image(doc, record)
            captioner.apply_to_record(record, spec)
            described += 1
        except LlamaServerError as exc:
            failures.append({"image_id": record.id, "error": str(exc)[:200]})
        except VisionError as exc:
            failures.append({"image_id": record.id, "error": str(exc)})

    captioner.merge_into_document(doc, records)
    store_records(doc, records)
    document_store.save(doc)
    log.info("Described %d/%d figure(s) in %s", described, len(wanted), doc.display_name)
    return {**_payload(doc, records), "described": described, "failures": failures}


class FigureUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    figure_type: str | None = None
    accepted: bool | None = None


@router.put("/{doc_id}/image/{image_id}")
async def update_figure(doc_id: str, image_id: str, body: FigureUpdate) -> dict[str, Any]:
    doc, records = _get_records(doc_id)
    record = next((r for r in records if r.id == image_id), None)
    if record is None:
        raise HTTPException(404, "Figure not found.")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(record, field, value)
    if body.description is not None:
        record.described = bool(body.description.strip())
    captioner.merge_into_document(doc, records)
    store_records(doc, records)
    document_store.save(doc)
    return _payload(doc, records)


class AskImageRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


@router.post("/{doc_id}/image/{image_id}/ask")
async def ask_image(doc_id: str, image_id: str, body: AskImageRequest) -> dict[str, str]:
    ensure_ai_allowed()
    doc, records = _get_records(doc_id)
    record = next((r for r in records if r.id == image_id), None)
    if record is None:
        raise HTTPException(404, "Figure not found.")
    try:
        await captioner.ensure_vision_available()
        return {"answer": await captioner.ask_about_image(doc, record, body.question)}
    except captioner.VisionUnavailable as exc:
        raise HTTPException(409, str(exc)) from exc
    except LlamaServerError as exc:
        raise to_http(exc) from exc


@router.get("/image/{doc_id}/{image_id}")
async def get_image(doc_id: str, image_id: str) -> FileResponse:
    _, records = _get_records(doc_id)
    record = next((r for r in records if r.id == image_id), None)
    if record is None:
        raise HTTPException(404, "Figure not found.")
    path = image_path(doc_id, record.filename)
    if not path.exists():
        raise HTTPException(404, "The image file is missing. Run extraction again.")
    return FileResponse(path, media_type="image/png")
