"""Router agent: decide what the user actually wants, then pick the tool.

The router is a small schema-constrained call: it returns an intent, the
parameters that intent needs and a confidence, never free text. The
orchestrator then dispatches to an existing service, so the model chooses the
route but never performs the action itself.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import DocumentContent
from app.services.features.structured import ask_structured

Intent = Literal[
    "answer",             # a question about the selected documents
    "summarize",          # condensed overview
    "generate_docx",      # produce a Word document
    "generate_xlsx",      # produce an Excel workbook
    "generate_pptx",      # produce a PowerPoint deck
    "data_query",         # a question about rows/numbers of a CSV or Excel file
    "quiz",               # a quiz / self-test
    "translate",          # translate the documents
    "privacy_scan",       # find personal data
    "describe_images",    # look at the figures in the documents
]


class RouteSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: Intent
    reasoning: str = Field(description="One short sentence explaining the choice")
    confidence: int = Field(ge=0, le=100)
    task: str = Field(description="The request rewritten as a clear instruction for the chosen tool")
    language: str = Field(description="Target language for 'translate', otherwise an empty string")
    document_hint: str = Field(description="Name of the single document the request is about, or an empty string")
    needs_verification: bool = Field(description="True when the result is factual and should be fact-checked")


ROUTER_SYSTEM = (
    "You are the router of a local document assistant. You never answer the user's question yourself. "
    "You classify the request and choose exactly one tool. Reply only with JSON matching the schema."
)

ROUTER_PROMPT = """Available tools:
- answer: answer a question using the selected documents (text content)
- summarize: summarise the selected documents
- generate_docx: create a Word document (reports, quizzes with answer keys, notes, letters)
- generate_xlsx: create an Excel workbook (tables, comparisons, structured lists)
- generate_pptx: create a PowerPoint presentation (slides, decks)
- data_query: answer a question about the rows or numbers of a spreadsheet/CSV (averages, top N, filtering, charts)
- quiz: run an interactive quiz for self-testing
- translate: translate the selected documents into another language
- privacy_scan: find personal data (names, e-mails, ID numbers) in a document
- describe_images: look at the figures, charts or diagrams inside the documents

Selected documents:
{documents}

User request:
\"\"\"{request}\"\"\"

Choose the single best tool. Prefer data_query over answer when the request is about numbers in a spreadsheet.
Prefer a generate_* tool only when the user asks for a file, slides, a document or a table to download.
Set needs_verification to true for factual answers and summaries, false for file generation and interactive tools."""


def _describe_documents(documents: list[DocumentContent]) -> str:
    if not documents:
        return "(none selected)"
    lines = []
    for i, d in enumerate(documents, start=1):
        extra = ""
        if d.source_type.value in ("csv", "xlsx"):
            cols = d.metadata.get("columns") or d.metadata.get("sheets") or []
            extra = f", tabular data ({', '.join(map(str, cols))[:120]})" if cols else ", tabular data"
        figures = d.metadata.get("figures_described")
        if figures:
            extra += f", {figures} described figure(s)"
        lines.append(f"{i}. {d.display_name} - {d.source_type.value}, {len(d.sections)} section(s){extra}")
    return "\n".join(lines)


async def route(request: str, documents: list[DocumentContent]) -> RouteSpec:
    return await ask_structured(
        RouteSpec,
        ROUTER_PROMPT.format(documents=_describe_documents(documents), request=request.strip()[:4000]),
        None,  # the router sees only the document list, not their full content
        system_prompt=ROUTER_SYSTEM,
        what="route",
        max_tokens=500,
    )
