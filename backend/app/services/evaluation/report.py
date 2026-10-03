"""Markdown tables from saved benchmark results (pasted into the README)."""
from __future__ import annotations

import json
from typing import Any

from .runner import list_results, load_result, results_dir


def _pct(v: float | None) -> str:
    return "-" if v is None else f"{round(100 * v)} %"


def summary_line(m: dict[str, Any]) -> str:
    return (f"overall {_pct(m['overall'])} | details {_pct(m['detail_accuracy'])} | lists recall "
            f"{_pct(m['list_recall'])} precision {_pct(m['list_precision'])} | not-in-documents "
            f"{_pct(m['abstention_accuracy'])} | unsupported numbers {_pct(m['unsupported_number_rate'])} | "
            f"citations correct {_pct(m['citation_accuracy'])} | {m['seconds_mean']} s/question")


METRICS = [
    ("overall", "Overall"),
    ("detail_accuracy", "Small details"),
    ("list_recall", "Similar items: recall"),
    ("list_precision", "Similar items: precision"),
    ("abstention_accuracy", "Says 'not in documents'"),
    ("false_abstention_rate", "Wrongly says 'not found'"),
    ("unsupported_number_rate", "Answers with invented numbers"),
    ("citation_accuracy", "Cites the right location"),
    ("prompt_leak_rate", "Copies prompt text into the answer"),
]


def retrieval_table(result: dict[str, Any]) -> str:
    lines = [
        "| Retrieval | Question -> documents | Recall@1 | Recall@3 | Recall@5 | Passage reached the model | Share of corpus sent |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for r in result["rows"]:
        lines.append(
            f"| {'language-aware' if r['stemming'] else 'plain BM25'} | {r['question_language'].upper()} -> {r['corpus'].upper()} "
            f"| {_pct(r['recall@1'])} | {_pct(r['recall@3'])} | {_pct(r['recall@5'])} "
            f"| {_pct(r['context_recall'])} | {_pct(r['share_of_corpus_sent'])} |"
        )
    return "\n".join(lines)


def run_table(runs: list[dict[str, Any]], group: str) -> str:
    """One column per run (model), one row per metric, for one summary group."""
    usable = [r for r in runs if group in (r.get("summary") or {})]
    if not usable:
        return ""
    head = "| Metric | " + " | ".join(r["model"] or r["id"] for r in usable) + " |"
    lines = [head, "|---|" + "---:|" * len(usable)]
    for key, label in METRICS:
        lines.append(f"| {label} | " + " | ".join(_pct(r["summary"][group][key]) for r in usable) + " |")
    lines.append("| Seconds per question | " + " | ".join(str(r["summary"][group]["seconds_mean"]) for r in usable) + " |")
    lines.append("| Cases | " + " | ".join(str(r["summary"][group]["cases"]) for r in usable) + " |")
    return "\n".join(lines)


def markdown_report() -> str:
    runs = [load_result(r["id"]) for r in list_results()]
    runs = [r for r in runs if r.get("cases")]
    out = []
    retrieval = results_dir() / "retrieval_check.json"
    if retrieval.is_file():
        out += ["### Retrieval (no model)", "", retrieval_table(json.loads(retrieval.read_text(encoding="utf-8"))), ""]
    for group, title in [
        ("all", "All cases"),
        ("strategy=full", "Full context, all cases"),
        ("full/difficulty=standard", "Full context, standard questions"),
        ("full/difficulty=hard", "Full context, hard questions"),
        ("full/en/same", "Full context, English questions on English documents"),
        ("full/fi/same", "Full context, Finnish questions on Finnish documents"),
        ("retrieval/en/same", "Retrieval, English on English"),
        ("retrieval/fi/same", "Retrieval, Finnish on Finnish"),
        ("en->fi", "Cross-lingual: English questions on Finnish documents"),
        ("fi->en", "Cross-lingual: Finnish questions on English documents"),
    ]:
        table = run_table(runs, group)
        if table:
            out += [f"### {title}", "", table, ""]
    return "\n".join(out)
