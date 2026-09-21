"""Interactive AI feature endpoints: verification, study mode, ask-your-data, privacy guard."""
from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.schemas.artifacts import XlsxSheet, XlsxSpec
from app.services.document_store import document_store
from app.services.export_store import ExportInfo, export_store
from app.services.features import data_query, privacy_guard, study, verify
from app.services.features.citations import Citation, extract_citations, source_map
from app.services.features.structured import StructuredOutputFailed
from app.services.llm.client import LlamaServerError
from app.services.llm.context_budget import ContextTooLarge
from app.services.writers.markdown_export import markdown_to_docx, markdown_to_pdf
from app.services.writers.simple_writers import write_text
from app.services.writers.xlsx_writer import write_xlsx

from .common import ensure_ai_allowed, resolve_documents, to_http

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["features"])


def _ai_errors(exc: Exception) -> HTTPException:
    if isinstance(exc, StructuredOutputFailed):
        return HTTPException(502, str(exc))
    if isinstance(exc, (ContextTooLarge, LlamaServerError)):
        return to_http(exc)
    if isinstance(exc, (data_query.DataQueryError,)):
        return HTTPException(422, str(exc))
    log.exception("Feature request failed")
    return HTTPException(500, "The request failed. Check the backend log.")


# ------------------------------------------------------------- citations --
class CitationRequest(BaseModel):
    answer: str
    document_ids: list[str] = Field(default_factory=list)


@router.post("/citations/resolve")
async def resolve_citations(body: CitationRequest) -> dict[str, Any]:
    docs = resolve_documents(body.document_ids)
    cites = extract_citations(body.answer, docs)
    return {"citations": [c.model_dump() for c in cites], "source_map": [s.model_dump() for s in source_map(docs)]}


# ---------------------------------------------------------------- verify --
class VerifyRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=30000)
    document_ids: list[str] = Field(min_length=1)


@router.post("/verify", response_model=verify.VerificationResult)
async def verify_answer(body: VerifyRequest) -> verify.VerificationResult:
    ensure_ai_allowed()
    docs = resolve_documents(body.document_ids)
    try:
        return await verify.verify_answer(body.answer, docs)
    except Exception as exc:  # noqa: BLE001
        raise _ai_errors(exc) from exc


# ----------------------------------------------------------------- study --
class QuizRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1)
    count: int = Field(default=8, ge=1, le=25)
    types: list[study.QuestionType] = Field(default_factory=lambda: ["multiple_choice", "true_false", "short_answer"])
    difficulty: Literal["easy", "medium", "hard", "mixed"] = "mixed"


@router.post("/study/quiz", response_model=study.QuizSpec)
async def study_quiz(body: QuizRequest) -> study.QuizSpec:
    ensure_ai_allowed()
    docs = resolve_documents(body.document_ids)
    try:
        return await study.generate_quiz(docs, count=body.count, types=list(body.types), difficulty=body.difficulty)
    except Exception as exc:  # noqa: BLE001
        raise _ai_errors(exc) from exc


class GradeRequest(BaseModel):
    question: study.QuizQuestion
    user_answer: str = Field(default="", max_length=4000)


@router.post("/study/grade", response_model=study.GradeResult)
async def study_grade(body: GradeRequest) -> study.GradeResult:
    ensure_ai_allowed()
    try:
        return await study.grade_answer(body.question, body.user_answer)
    except Exception as exc:  # noqa: BLE001
        raise _ai_errors(exc) from exc


class ReportRequest(BaseModel):
    title: str = "Study session"
    records: list[study.AnswerRecord]
    document_ids: list[str] = Field(default_factory=list)
    kind: Literal["xlsx", "docx"] = "xlsx"


@router.post("/study/report", response_model=ExportInfo)
async def study_report(body: ReportRequest) -> ExportInfo:
    docs = resolve_documents(body.document_ids) if body.document_ids else []
    info, path = export_store.reserve(f"study_session.{body.kind}", body.kind, [d.display_name for d in docs], body.title)
    study.build_report(body.title, body.records, [d.display_name for d in docs], path, body.kind)
    return export_store.commit(info)


# ------------------------------------------------------------------ data --
class DataQueryRequest(BaseModel):
    document_id: str
    question: str = Field(min_length=1, max_length=2000)
    sheet: str | None = None


@router.get("/data/{doc_id}/info")
async def data_info(doc_id: str, sheet: str | None = None) -> dict[str, Any]:
    doc = resolve_documents([doc_id])[0]
    try:
        t = data_query.load_table(doc, sheet)
    except data_query.DataQueryError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"name": t.name, "columns": t.columns, "row_count": len(t.rows), "sheets": t.sheets, "preview": t.rows[:5]}


@router.post("/data/query", response_model=data_query.QueryResult)
async def data_ask(body: DataQueryRequest) -> data_query.QueryResult:
    ensure_ai_allowed()
    doc = resolve_documents([body.document_id])[0]
    try:
        return await data_query.ask_data(doc, body.question, body.sheet)
    except Exception as exc:  # noqa: BLE001
        raise _ai_errors(exc) from exc


class DataExportRequest(BaseModel):
    title: str = "Query result"
    columns: list[str]
    rows: list[list[Any]]
    document_id: str | None = None
    note: str = ""


@router.post("/data/export", response_model=ExportInfo)
async def data_export(body: DataExportRequest) -> ExportInfo:
    docs = resolve_documents([body.document_id]) if body.document_id else []
    spec = XlsxSpec(
        workbook_title=body.title,
        sheets=[XlsxSheet(name="Result", headers=body.columns, rows=[["" if v is None else str(v) for v in r] for r in body.rows], notes=body.note)],
    )
    info, path = export_store.reserve("query_result.xlsx", "xlsx", [d.display_name for d in docs], body.title)
    write_xlsx(spec, path, [d.display_name for d in docs])
    return export_store.commit(info)


# --------------------------------------------------------------- privacy --
class ScanRequest(BaseModel):
    document_id: str
    use_ai: bool = True


@router.post("/privacy/scan", response_model=privacy_guard.ScanResult)
async def privacy_scan(body: ScanRequest) -> privacy_guard.ScanResult:
    doc = resolve_documents([body.document_id])[0]
    if body.use_ai:
        ensure_ai_allowed()
    try:
        return await privacy_guard.scan_document(doc, use_ai=body.use_ai)
    except Exception as exc:  # noqa: BLE001
        raise _ai_errors(exc) from exc


class RedactRequest(BaseModel):
    document_id: str
    items: list[privacy_guard.RedactionItem]
    export: Literal["none", "md", "txt", "docx", "pdf"] = "none"
    add_to_library: bool = True


@router.post("/privacy/redact")
async def privacy_redact(body: RedactRequest) -> dict[str, Any]:
    doc = resolve_documents([body.document_id])[0]
    text, mapping = privacy_guard.redact_text(doc.full_markdown, body.items)
    result: dict[str, Any] = {"replacements": mapping, "preview": text[:3000], "characters": len(text)}
    if body.add_to_library:
        new_doc = document_store.add_text(text, f"{doc.display_name} (redacted)")
        result["document"] = {"id": new_doc.id, "display_name": new_doc.display_name}
    if body.export != "none":
        name = f"{doc.display_name.rsplit('.', 1)[0]}_redacted.{body.export}"
        info, path = export_store.reserve(name, body.export, [doc.display_name], "redacted copy")
        if body.export in ("md", "txt"):
            write_text(text, path)
        elif body.export == "docx":
            markdown_to_docx(text, path, title=f"{doc.display_name} (redacted)")
        else:
            markdown_to_pdf(text, path, title=f"{doc.display_name} (redacted)")
        result["export"] = export_store.commit(info).model_dump(mode="json")
    log.info("Redacted %s: %d item(s)", doc.display_name, len(mapping))
    return result


__all__ = ["router", "Citation"]
