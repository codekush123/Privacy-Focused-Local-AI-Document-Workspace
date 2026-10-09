"""Live answer check: the benchmark's verification rules, applied to every answer.

Runs in milliseconds and without a second model call, right after an answer
is generated (or translated):

- **numbers**: every number in the answer must occur in a selected document
  or in the question; anything else is flagged ("not found in the sources" -
  invented, or computed by the model);
- **citations**: each factual sentence should carry a citation, and every
  citation must point to a real section;
- **refusals**: an answer that says the documents do not contain the
  information is recognised and shown as such, not as a failure.

The same functions score the benchmark (``services/evaluation/scoring.py``),
so what a user sees on an answer is exactly what the evaluation measures.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from app.models.document import DocumentContent
from app.services.evaluation.scoring import is_abstention, known_numbers, strip_thinking, unsupported_numbers

from .citations import CITATION_RE, extract_citations, normalize_citations

Status = Literal["ok", "partly_cited", "review", "not_in_documents", "no_sources"]

# Sentence boundary: ., ! or ? followed by space and something that starts a sentence.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[\"'(*_]?[A-ZÅÄÖ0-9])")
_LIST_MARK = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
_TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{3,}")
MIN_WORDS = 5  # shorter fragments ("Yes.", "Summary:") are not checked for a citation
MAX_LISTED = 8


class AnswerCheck(BaseModel):
    status: Status
    summary: str
    numbers_total: int = 0
    unsupported_numbers: list[str] = []
    sentences_total: int = 0
    uncited_sentences: list[str] = []
    citations_total: int = 0
    unresolved_citations: list[str] = []
    says_not_in_documents: bool = False


def _units(answer: str) -> list[str]:
    """Sentences and list items / table rows of an answer, in reading order."""
    units: list[str] = []
    for line in answer.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or _TABLE_RULE.match(line):
            continue
        line = _LIST_MARK.sub("", line).strip()
        if line.startswith("|"):
            units.append(line.strip("|").strip())
            continue
        units.extend(part.strip() for part in _SENTENCE_END.split(line) if part.strip())
    return units


def _is_factual(unit: str) -> bool:
    text = CITATION_RE.sub("", unit).strip()
    if text.endswith(":") or len(text.split()) < MIN_WORDS:
        return False
    return not is_abstention(text)


def citation_coverage(answer: str) -> tuple[int, list[str]]:
    """(number of factual sentences, those without a citation).

    A citation standing alone after a sentence ("... in 2025. [S1: Page 3]")
    counts for that sentence.
    """
    units = _units(normalize_citations(answer))
    factual: list[tuple[str, bool]] = []
    for unit in units:
        only_citations = not CITATION_RE.sub("", unit).strip(" .;,")
        if only_citations:
            if factual:
                factual[-1] = (factual[-1][0], True)
            continue
        if _is_factual(unit):
            factual.append((unit, bool(CITATION_RE.search(unit))))
    return len(factual), [text for text, cited in factual if not cited]


def check_answer(answer: str, documents: list[DocumentContent], question: str = "") -> AnswerCheck:
    answer, _thinking = strip_thinking(answer)
    if not answer.strip():
        return AnswerCheck(status="no_sources", summary="No answer to check.")
    if not documents:
        return AnswerCheck(status="no_sources", summary="No documents selected, so the answer cannot be checked against sources.")

    known = known_numbers(*(d.full_markdown for d in documents), question)
    plain = CITATION_RE.sub(" ", normalize_citations(answer))
    numbers = [m for m in re.findall(r"\d[\d\s.,]*\d|\d", plain) if m.strip()]
    flagged = list(dict.fromkeys(unsupported_numbers(answer, known)))  # unique, in order

    sentences_total, uncited = citation_coverage(answer)
    cites = extract_citations(answer, documents)
    unresolved = [c.marker for c in cites if not c.found]
    refusal = is_abstention(answer)

    if flagged or unresolved:
        status: Status = "review"
        parts = []
        if flagged:
            parts.append(f"{len(flagged)} number{'s' if len(flagged) != 1 else ''} not found in the sources")
        if unresolved:
            parts.append(f"{len(unresolved)} citation{'s' if len(unresolved) != 1 else ''} not matching a section")
        summary = "Check this answer: " + " and ".join(parts) + "."
    elif refusal and not cites:
        status, summary = "not_in_documents", "The answer says the selected documents do not contain this."
    elif uncited:
        status = "partly_cited"
        summary = (f"All numbers are in the sources; {sentences_total - len(uncited)} of {sentences_total} "
                   "statements cite a source.")
    else:
        status = "ok"
        summary = ("All numbers are in the sources and every statement cites a source."
                   if sentences_total else "All numbers are in the sources.")
    return AnswerCheck(
        status=status,
        summary=summary,
        numbers_total=len(numbers),
        unsupported_numbers=flagged,
        sentences_total=sentences_total,
        uncited_sentences=[s[:240] for s in uncited[:MAX_LISTED]],
        citations_total=len(cites),
        unresolved_citations=unresolved[:MAX_LISTED],
        says_not_in_documents=refusal,
    )
