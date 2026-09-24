"""Agentic workflow: Router -> Tool -> Verifier -> (optional) Refine.

Deliberately implemented as a small local state machine over the services this
application already has, instead of a general agent framework: every step is
explicit, every tool is a plain function, and the whole trace can be shown to
the user. Nothing is sent anywhere; each step is one call to the local model.

    route      the router agent picks one tool and rewrites the task
    execute    the tool runs (chat answer, file generation, data query, ...)
    verify     the verifier agent checks the answer against the sources
    refine     if grounding is weak, the answer is rewritten once using the
               verifier's findings, then verified again

Steps are yielded as they happen so the UI can show the agent thinking.
"""
from __future__ import annotations

import logging
import time
from typing import Any, AsyncIterator

from app.models.document import DocumentContent
from app.services.export_store import ExportInfo
from app.services.features import data_query, privacy_guard, verify
from app.services.features.citations import citation_stats, extract_citations
from app.services.generation import generate_artifact
from app.services.llm.client import llm_client
from app.services.llm.context_budget import ContextTooLarge
from app.services.llm.context_builder import build_prompt
from app.services.llm.prompts import QUICK_ACTIONS, TRANSLATE_PROMPT

from .router_agent import RouteSpec, route

log = logging.getLogger(__name__)

# Below this grounding score the answer is rewritten once with the verifier's notes.
REFINE_THRESHOLD = 70


class AgentError(Exception):
    pass


def _step(name: str, status: str, **data: Any) -> dict[str, Any]:
    return {"step": name, "status": status, **data}


async def _answer(task: str, documents: list[DocumentContent], max_tokens: int | None = None) -> tuple[str, dict[str, Any]]:
    messages, check, info = await build_prompt(documents, task, max_output_tokens=max_tokens)
    answer = await llm_client.chat(messages, max_tokens=max_tokens)
    return answer, {**check.to_dict(), "strategy_info": info.to_dict()}


REFINE_PROMPT = """The question below was answered, and the answer was then fact-checked against the source documents. Some statements were not supported.

Question:
\"\"\"{question}\"\"\"

Previous answer:
\"\"\"{answer}\"\"\"

Fact-check findings:
{findings}

Answer the question again. Keep only what the sources support, correct what was contradicted, and say explicitly if the documents do not contain part of the answer. Stay on the question - do not list unrelated facts just because they are supported. Keep the inline [S<id>: <locator>] citations."""


def _findings_text(result: verify.VerificationResult) -> str:
    lines = []
    for c in result.claims:
        if c.verdict in ("unsupported", "contradicted", "partially_supported"):
            lines.append(f"- [{c.verdict}] {c.claim}" + (f" (source says: \"{c.evidence}\")" if c.evidence else ""))
    return "\n".join(lines) or "- (no specific findings)"


async def run_agent(
    request: str,
    documents: list[DocumentContent],
    *,
    allow_files: bool = True,
    auto_verify: bool = True,
    max_output_tokens: int | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield trace events for one agent run. The last event is type 'result' or 'error'."""
    t0 = time.perf_counter()
    yield _step("router", "running", message="Deciding which tool fits the request…")

    try:
        spec: RouteSpec = await route(request, documents)
    except Exception as exc:  # noqa: BLE001 - fall back to a plain answer
        log.warning("Router failed (%s); falling back to 'answer'", exc)
        spec = RouteSpec(
            intent="answer", reasoning="The router was unavailable, answering directly.",
            confidence="low", task=request, language="", document_hint="", needs_verification=True,
        )
    if not allow_files and spec.intent.startswith("generate_"):
        spec.intent = "answer"
        spec.reasoning += " (file generation is switched off, answering in chat instead)"

    yield _step(
        "router", "done", intent=spec.intent, reasoning=spec.reasoning,
        confidence=spec.confidence, task=spec.task, tool=spec.intent,
    )

    tool_label = {
        "answer": "Answering from the documents",
        "summarize": "Summarising the documents",
        "generate_docx": "Generating a Word document",
        "generate_xlsx": "Generating an Excel workbook",
        "generate_pptx": "Generating a PowerPoint deck",
        "data_query": "Planning and running a query on the table",
        "quiz": "Preparing a quiz",
        "translate": f"Translating into {spec.language or 'the requested language'}",
        "privacy_scan": "Scanning for personal data",
        "describe_images": "Looking at the figures",
    }[spec.intent]
    yield _step("tool", "running", tool=spec.intent, message=tool_label)

    answer: str | None = None
    payload: dict[str, Any] = {}
    context: dict[str, Any] | None = None

    # For tools where the user's own wording *is* the query, the original request
    # is used: a rewritten task can silently change what is being asked.
    verbatim_task = spec.task if spec.intent in ("generate_docx", "generate_xlsx", "generate_pptx", "summarize", "translate") else request.strip()

    try:
        if spec.intent in ("answer", "summarize", "translate"):
            task = verbatim_task
            if spec.intent == "summarize":
                task = QUICK_ACTIONS["summarize"] + "\n\n" + spec.task
            elif spec.intent == "translate":
                task = TRANSLATE_PROMPT.format(language=spec.language or "English")
            answer, context = await _answer(task, documents, max_output_tokens)

        elif spec.intent.startswith("generate_"):
            kind = spec.intent.split("_", 1)[1]
            info: ExportInfo = await generate_artifact(kind, spec.task, documents)
            payload["export"] = info.model_dump(mode="json")
            answer = f"**{info.filename}** is ready ({info.size_bytes / 1024:.1f} KB)."

        elif spec.intent == "data_query":
            table_docs = [d for d in documents if d.source_type.value in ("csv", "xlsx")]
            if not table_docs:
                raise AgentError("This request needs a CSV or Excel document, but none is selected.")
            target = next((d for d in table_docs if spec.document_hint and spec.document_hint.lower() in d.display_name.lower()), table_docs[0])
            result = await data_query.ask_data(target, verbatim_task)
            payload["query"] = result.model_dump(mode="json")
            answer = f"{result.plan.explanation} ({result.row_count} of {result.total_rows} rows)"

        elif spec.intent == "quiz":
            payload["handoff"] = {"tab": "study", "task": verbatim_task}
            answer = "Open **Study mode** to run this quiz interactively - the questions are generated there so they can be graded one by one."

        elif spec.intent == "privacy_scan":
            target = next((d for d in documents if spec.document_hint and spec.document_hint.lower() in d.display_name.lower()), documents[0] if documents else None)
            if target is None:
                raise AgentError("Select a document to scan for personal data.")
            scan = await privacy_guard.scan_document(target, use_ai=True)
            payload["scan"] = scan.model_dump(mode="json")
            answer = f"Found {len(scan.findings)} item(s) of personal data in **{target.display_name}**. Open **Privacy Guard** to review and redact them."

        elif spec.intent == "describe_images":
            payload["handoff"] = {"tab": "figures", "task": verbatim_task}
            answer = "Open the **Figures** tab to extract and describe the images in the selected documents with the vision model."

    except ContextTooLarge as exc:
        yield _step("tool", "error", error=exc.check.message, suggestions=exc.check.suggestions)
        yield {"step": "error", "status": "done", "error": exc.check.message, "suggestions": exc.check.suggestions}
        return
    except Exception as exc:  # noqa: BLE001
        log.exception("Agent tool %s failed", spec.intent)
        msg = str(exc) if isinstance(exc, AgentError) else f"The step '{tool_label}' failed: {exc}"
        yield _step("tool", "error", error=msg)
        yield {"step": "error", "status": "done", "error": msg}
        return

    citations = extract_citations(answer or "", documents)
    yield _step(
        "tool", "done", tool=spec.intent, answer=answer, context=context,
        citations=[c.model_dump() for c in citations], citation_stats=citation_stats(citations), **payload,
    )

    # ---------------------------------------------------------------- verify
    verification = None
    if auto_verify and spec.needs_verification and answer and documents and spec.intent in ("answer", "summarize"):
        yield _step("verifier", "running", message="Checking every claim against the sources…")
        try:
            verification = await verify.verify_answer(answer, documents)
            yield _step(
                "verifier", "done", grounding_score=verification.grounding_score,
                counts=verification.counts, overall=verification.overall,
                verification=verification.model_dump(mode="json"),
            )
        except Exception as exc:  # noqa: BLE001 - verification is best effort
            log.warning("Verification failed: %s", exc)
            yield _step("verifier", "error", error=str(exc)[:200])

        # ------------------------------------------------------------ refine
        if verification is not None and verification.grounding_score < REFINE_THRESHOLD:
            yield _step(
                "refine", "running",
                message=f"Grounding is only {verification.grounding_score}% - rewriting the answer using the findings…",
            )
            try:
                improved, context = await _answer(
                    REFINE_PROMPT.format(
                        question=request.strip(),
                        answer=answer,
                        findings=_findings_text(verification),
                    ),
                    documents, max_output_tokens,
                )
                recheck = await verify.verify_answer(improved, documents)
                if recheck.grounding_score >= verification.grounding_score:
                    answer, verification = improved, recheck
                    citations = extract_citations(answer, documents)
                    yield _step(
                        "refine", "done", improved=True, grounding_score=recheck.grounding_score,
                        answer=answer, citations=[c.model_dump() for c in citations],
                        citation_stats=citation_stats(citations), verification=recheck.model_dump(mode="json"),
                    )
                else:
                    yield _step("refine", "done", improved=False, grounding_score=recheck.grounding_score,
                                message="The rewrite did not improve grounding; keeping the first answer.")
            except Exception as exc:  # noqa: BLE001
                log.warning("Refinement failed: %s", exc)
                yield _step("refine", "error", error=str(exc)[:200])

    yield {
        "step": "result",
        "status": "done",
        "intent": spec.intent,
        "answer": answer,
        "context": context,
        "citations": [c.model_dump() for c in citations],
        "citation_stats": citation_stats(citations),
        "verification": verification.model_dump(mode="json") if verification else None,
        "elapsed_seconds": round(time.perf_counter() - t0, 1),
        **payload,
    }
