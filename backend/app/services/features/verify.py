"""Claim verification: fact-check an answer against the selected sources.

The answer is split into atomic claims by the model, and each claim is
labelled supported / partially supported / unsupported / contradicted with
the evidence sentence and its source locator. This turns the assistant into
a self-checking tool: the user can see which parts of an answer are actually
backed by their documents.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import DocumentContent

from .citations import Citation, extract_citations
from .structured import ask_structured


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim: str = Field(description="One atomic factual statement taken from the answer")
    verdict: Literal["supported", "partially_supported", "unsupported", "contradicted"]
    evidence: str = Field(default="", description="Short quote from the source that supports or contradicts the claim")
    source: str = Field(default="", description="Citation in the form [S1: Page 3] or empty if none")
    note: str = Field(default="", description="Short explanation")


class VerificationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claims: list[Claim]
    overall: str = Field(description="One or two sentences summarising how well the answer is grounded")


class VerificationResult(BaseModel):
    claims: list[Claim]
    overall: str
    counts: dict[str, int]
    grounding_score: int  # 0-100
    citations: list[Citation]


VERIFY_INSTRUCTIONS = """You are a strict fact-checker. Below is an ANSWER that an assistant gave about the selected source materials.

Split the ANSWER into its individual factual claims (typically 3-12). For each claim decide, using ONLY the source materials:
- supported: the sources state this clearly
- partially_supported: the sources state part of it or something close
- unsupported: the sources say nothing about it
- contradicted: the sources say something different

Quote the relevant source sentence as evidence and give its citation as [S<id>: <locator>].

ANSWER:
\"\"\"
{answer}
\"\"\""""


async def verify_answer(answer: str, documents: list[DocumentContent]) -> VerificationResult:
    spec = await ask_structured(
        VerificationSpec,
        VERIFY_INSTRUCTIONS.format(answer=answer.strip()[:12000]),
        documents,
        what="verification report",
        max_tokens=3000,
    )
    counts = {k: 0 for k in ("supported", "partially_supported", "unsupported", "contradicted")}
    for c in spec.claims:
        counts[c.verdict] += 1
    n = max(len(spec.claims), 1)
    score = round((counts["supported"] + 0.5 * counts["partially_supported"]) / n * 100)
    cites = extract_citations(" ".join(c.source for c in spec.claims if c.source), documents)
    return VerificationResult(
        claims=spec.claims, overall=spec.overall, counts=counts, grounding_score=score, citations=cites
    )
