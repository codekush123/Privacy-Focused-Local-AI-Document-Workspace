"""Document library endpoints: upload, paste, URL import, list, preview, delete."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, UploadFile

from app.config import settings
from app.models.document import DocumentContent, DocumentSummary
from app.schemas.api import TextImportRequest, UrlImportRequest
from app.services.document_store import document_store
from app.services.parsers import SUPPORTED_EXTENSIONS, ParseError
from app.utils.files import extension_of, sanitize_filename

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("", response_model=list[DocumentSummary])
async def list_documents() -> list[DocumentSummary]:
    return document_store.list()


@router.get("/supported")
async def supported() -> dict:
    return {"extensions": list(SUPPORTED_EXTENSIONS), "max_upload_bytes": settings.max_upload_bytes}


@router.post("/upload", response_model=DocumentSummary, status_code=201)
async def upload(file: UploadFile) -> DocumentSummary:
    name = sanitize_filename(file.filename or "upload")
    ext = extension_of(name)
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            415, f"This file type (.{ext or '?'}) is not supported. Supported: {', '.join(SUPPORTED_EXTENSIONS)}."
        )
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, f"The file is larger than the {settings.max_upload_bytes // (1024 * 1024)} MB upload limit.")
    if not data:
        raise HTTPException(400, "The uploaded file is empty.")
    try:
        doc = document_store.add_upload(name, data)
    except ParseError as exc:
        raise HTTPException(422, str(exc)) from exc
    return DocumentSummary.from_document(doc)


@router.post("/text", response_model=DocumentSummary, status_code=201)
async def import_text(body: TextImportRequest) -> DocumentSummary:
    try:
        doc = document_store.add_text(body.text, body.name)
    except ParseError as exc:
        raise HTTPException(422, str(exc)) from exc
    return DocumentSummary.from_document(doc)


@router.post("/url", response_model=DocumentSummary, status_code=201)
async def import_url(body: UrlImportRequest) -> DocumentSummary:
    """Explicit network operation: fetches exactly one URL and parses it locally."""
    try:
        doc = await document_store.add_url(body.url)
    except ParseError as exc:
        raise HTTPException(422, str(exc)) from exc
    return DocumentSummary.from_document(doc)


@router.get("/{doc_id}", response_model=DocumentContent)
async def get_document(doc_id: str, preview_chars: int | None = None) -> DocumentContent:
    doc = document_store.get(doc_id)
    if doc is None:
        raise HTTPException(404, "Document not found.")
    if preview_chars:
        preview = doc.model_copy()
        preview.full_markdown = doc.full_markdown[:preview_chars]
        preview.sections = []
        return preview
    return doc


@router.get("/{doc_id}/sections")
async def document_sections(doc_id: str) -> list[dict]:
    """Sections with locators - used to show the passage behind a citation."""
    doc = document_store.get(doc_id)
    if doc is None:
        raise HTTPException(404, "Document not found.")
    return [
        {"section_id": s.section_id, "title": s.title, "locator": s.locator, "markdown": s.markdown}
        for s in doc.sections
    ]


@router.delete("/{doc_id}", status_code=204)
async def delete_document(doc_id: str) -> None:
    if not document_store.delete(doc_id):
        raise HTTPException(404, "Document not found.")


@router.delete("", status_code=200)
async def clear_documents() -> dict:
    return {"deleted": document_store.clear()}
