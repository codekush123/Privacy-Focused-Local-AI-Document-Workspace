"""Interactive study mode.

1. generate_quiz: the model produces a structured quiz (multiple choice,
   true/false and short-answer questions) from the selected documents.
2. grade_answer: closed questions are graded deterministically; free-text
   answers are graded by the model against the reference answer with a
   score and feedback - the AI acts as a tutor, not just a generator.
3. build_report: the finished session is turned into an Excel / Word report
   with the existing writers (no extra model call).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import DocumentContent
from app.schemas.artifacts import DocxBlock, DocxSpec, XlsxSheet, XlsxSpec
from app.services.writers.docx_writer import write_docx
from app.services.writers.xlsx_writer import write_xlsx

from .structured import ask_structured

QuestionType = Literal["multiple_choice", "true_false", "short_answer"]


class QuizQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: QuestionType
    question: str
    options: list[str] = Field(default_factory=list, description="4 options for multiple_choice, empty otherwise")
    answer: str = Field(description="Exact correct option text, 'True'/'False', or a model short answer")
    explanation: str = Field(description="Why this is the answer, one or two sentences")
    source: str = Field(description="Citation like [S1: Page 3]")
    difficulty: Literal["easy", "medium", "hard"] = "medium"


class QuizSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    questions: list[QuizQuestion]


class GradeSpec(BaseModel):
    # No schema minimum/maximum: numeric bounds slow llama.cpp's grammar down
    # considerably. The value is clamped in grade_answer() instead.
    model_config = ConfigDict(extra="forbid")
    correct: bool
    score: int = Field(description="Score from 0 to 100; partial credit is allowed")
    feedback: str = Field(description="One to three sentences of tutor feedback addressed to the student")


class GradeResult(BaseModel):
    correct: bool
    score: int
    feedback: str
    graded_by: Literal["rules", "ai"]


class AnswerRecord(BaseModel):
    question: str
    type: str
    user_answer: str
    correct_answer: str
    correct: bool
    score: int
    feedback: str = ""
    source: str = ""


QUIZ_INSTRUCTIONS = (
    "Create a quiz with exactly {count} questions based ONLY on the selected source materials. "
    "Mix of types: {types}. Difficulty: {difficulty}. "
    "For multiple_choice give exactly 4 plausible options and put the exact correct option text in 'answer'. "
    "For true_false give options ['True', 'False'] and answer 'True' or 'False'. "
    "For short_answer leave options empty and give a concise model answer. "
    "Every question must have a citation in 'source' pointing to where the answer is found. "
    "Questions must be answerable from the materials and must not repeat each other."
)

GRADE_SYSTEM = (
    "You are a fair but strict tutor grading one short-answer question. Compare the student's answer with the "
    "reference answer. Give full credit for answers that are correct in substance even if worded differently, "
    "partial credit for partially correct answers, and zero for wrong or empty answers. Be encouraging but honest."
)

GRADE_PROMPT = """Question: {question}
Reference answer: {reference}
Explanation (for you, the grader): {explanation}
Student's answer: {user_answer}

Grade the student's answer."""


async def generate_quiz(
    documents: list[DocumentContent],
    *,
    count: int = 8,
    types: list[str] | None = None,
    difficulty: str = "mixed",
) -> QuizSpec:
    types = types or ["multiple_choice", "true_false", "short_answer"]
    spec = await ask_structured(
        QuizSpec,
        QUIZ_INSTRUCTIONS.format(count=count, types=", ".join(types), difficulty=difficulty),
        documents,
        what="quiz",
        max_tokens=4000,
    )
    # Keep the requested shape even if the model over-delivers.
    spec.questions = [q for q in spec.questions if q.type in types][:count]
    for q in spec.questions:
        q.source = normalize_marker(q.source)
        if q.type == "true_false":
            q.options = ["True", "False"]
            q.answer = "True" if q.answer.strip().lower().startswith("t") else "False"
        if q.type == "multiple_choice" and q.answer not in q.options and q.options:
            # tolerate letter answers like "B" or "b)"
            m = re.match(r"^\s*([A-Da-d])[\).\s]*$", q.answer)
            if m:
                q.answer = q.options[min(ord(m.group(1).upper()) - 65, len(q.options) - 1)]
    return spec


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def normalize_marker(src: str) -> str:
    """Turn 'S1: Page 2' / '(S1: Page 2)' into '[S1: Page 2]'."""
    src = (src or "").strip().strip("()[]").strip()
    return f"[{src}]" if re.match(r"^S\d+\s*[:\-]", src) else src


async def grade_answer(q: QuizQuestion, user_answer: str) -> GradeResult:
    if q.type in ("multiple_choice", "true_false"):
        ok = _norm(user_answer) == _norm(q.answer)
        fb = "Correct. " + q.explanation if ok else f"Not quite - the correct answer is: {q.answer}. {q.explanation}"
        return GradeResult(correct=ok, score=100 if ok else 0, feedback=fb.strip(), graded_by="rules")
    if not user_answer.strip():
        return GradeResult(correct=False, score=0, feedback=f"No answer given. Reference answer: {q.answer}", graded_by="rules")
    spec = await ask_structured(
        GradeSpec,
        GRADE_PROMPT.format(question=q.question, reference=q.answer, explanation=q.explanation, user_answer=user_answer.strip()[:2000]),
        None,
        system_prompt=GRADE_SYSTEM,
        what="grade",
        max_tokens=400,
    )
    return GradeResult(correct=spec.correct, score=max(0, min(100, spec.score)), feedback=spec.feedback, graded_by="ai")


def build_report(title: str, records: list[AnswerRecord], sources: list[str], out_path: Path, kind: str) -> Path:
    total = sum(r.score for r in records)
    avg = round(total / len(records)) if records else 0
    correct = sum(1 for r in records if r.correct)
    if kind == "xlsx":
        rows = [
            [str(i + 1), r.question, r.type, r.user_answer, r.correct_answer, "yes" if r.correct else "no", str(r.score), r.feedback, r.source]
            for i, r in enumerate(records)
        ]
        spec = XlsxSpec(
            workbook_title=title,
            sheets=[
                XlsxSheet(
                    name="Results",
                    headers=["#", "Question", "Type", "Your answer", "Correct answer", "Correct", "Score", "Feedback", "Source"],
                    rows=rows,
                    notes=f"Score: {correct}/{len(records)} correct, average {avg}%",
                )
            ],
        )
        return write_xlsx(spec, out_path, sources)
    blocks = [
        DocxBlock(type="paragraph", text=f"Result: {correct} of {len(records)} correct, average score {avg}%."),
    ]
    for i, r in enumerate(records, start=1):
        blocks.append(DocxBlock(type="heading", level=2, text=f"{i}. {r.question}"))
        blocks.append(DocxBlock(type="bullets", items=[
            f"Your answer: {r.user_answer or '(none)'}",
            f"Correct answer: {r.correct_answer}",
            f"Result: {'correct' if r.correct else 'incorrect'} ({r.score}%)",
            f"Feedback: {r.feedback}" if r.feedback else "Feedback: -",
            f"Source: {r.source}" if r.source else "Source: -",
        ]))
    return write_docx(DocxSpec(title=title, subtitle="Study session report", blocks=blocks), out_path, sources)
