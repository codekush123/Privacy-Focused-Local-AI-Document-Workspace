"""File generation and export download endpoints."""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.schemas.api import GenerateRequest, SaveTextRequest
from app.services.export_store import ExportInfo, export_store
from app.services.generation import GenerationFailed, generate_artifact, save_text_export
from app.services.llm.client import LlamaServerError
from app.services.llm.context_budget import ContextTooLarge

from .common import ensure_ai_allowed, resolve_documents, to_http

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["generate"])

MEDIA_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "csv": "text/csv; charset=utf-8",
    "md": "text/markdown; charset=utf-8",
    "txt": "text/plain; charset=utf-8",
    "pdf": "application/pdf",
    "tex": "application/x-tex; charset=utf-8",
}


@router.post("/generate/{kind}", response_model=ExportInfo)
async def generate(kind: Literal["docx", "xlsx", "pptx", "csv"], body: GenerateRequest) -> ExportInfo:
    ensure_ai_allowed()
    docs = resolve_documents(body.document_ids)
    try:
        return await generate_artifact(kind, body.prompt, docs, filename=body.filename)
    except (ContextTooLarge, LlamaServerError) as exc:
        raise to_http(exc) from exc
    except GenerationFailed as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/exports/save-text", response_model=ExportInfo)
async def save_text(body: SaveTextRequest) -> ExportInfo:
    docs = resolve_documents(body.document_ids) if body.document_ids else []
    try:
        return save_text_export(
            body.text, body.kind, body.filename, [d.display_name for d in docs], body.prompt, title=body.title
        )
    except GenerationFailed as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/exports", response_model=list[ExportInfo])
async def list_exports() -> list[ExportInfo]:
    return export_store.list()


@router.get("/exports/{export_id}")
async def download(export_id: str) -> FileResponse:
    info = export_store.get(export_id)
    if info is None:
        raise HTTPException(404, "Export not found.")
    path = export_store.path_for(info)
    if not path.exists():
        raise HTTPException(404, "The exported file no longer exists.")
    return FileResponse(
        path,
        media_type=MEDIA_TYPES.get(info.kind, "application/octet-stream"),
        filename=info.filename,
    )


@router.delete("/exports/{export_id}", status_code=204)
async def delete_export(export_id: str) -> None:
    if not export_store.delete(export_id):
        raise HTTPException(404, "Export not found.")


@router.delete("/exports", status_code=200)
async def clear_exports() -> dict:
    return {"deleted": export_store.clear()}
