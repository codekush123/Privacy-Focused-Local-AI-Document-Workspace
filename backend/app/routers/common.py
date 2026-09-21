"""Helpers shared by the AI routers."""
from __future__ import annotations

from fastapi import HTTPException

from app.models.document import DocumentContent
from app.services.document_store import document_store
from app.services.llm.client import LlamaServerError, LlamaServerUnavailable
from app.services.llm.context_budget import ContextTooLarge
from app.services.privacy.policy import PrivacyViolation, assert_llm_endpoint_allowed


def resolve_documents(ids: list[str]) -> list[DocumentContent]:
    try:
        docs = document_store.get_many(ids)
    except KeyError as exc:
        raise HTTPException(404, f"Document {exc.args[0]} was not found. It may have been deleted.") from exc
    bad = [d.display_name for d in docs if d.status != "ready"]
    if bad:
        raise HTTPException(422, f"These documents could not be processed and cannot be used: {', '.join(bad)}")
    return docs


def ensure_ai_allowed() -> None:
    try:
        assert_llm_endpoint_allowed()
    except PrivacyViolation as exc:
        raise HTTPException(403, str(exc)) from exc


def to_http(exc: Exception) -> HTTPException:
    """Translate service-layer errors into user-friendly HTTP errors."""
    if isinstance(exc, ContextTooLarge):
        c = exc.check
        return HTTPException(
            413,
            detail={"error": c.message, "suggestions": c.suggestions, "context": c.to_dict()},
        )
    if isinstance(exc, LlamaServerUnavailable):
        return HTTPException(503, str(exc))
    if isinstance(exc, LlamaServerError):
        return HTTPException(502, str(exc))
    if isinstance(exc, PrivacyViolation):
        return HTTPException(403, str(exc))
    return HTTPException(500, "An unexpected error occurred. Check the backend log for details.")
