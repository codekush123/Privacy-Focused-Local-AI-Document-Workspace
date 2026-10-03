"""Run the accuracy benchmark.

Two levels:

``retrieval_check``  no model needed, takes seconds. For every question, does
                     the retrieval step put the passage holding the answer in
                     front of the model? Measured with and without stemming.
``run_benchmark``    asks the loaded model every question through the real
                     pipeline (context strategy -> llama-server -> citations)
                     and scores the answers with ``scoring.py``.

Cases are ordered corpus language -> strategy -> question, so with full context
the long document prompt is identical from one question to the next and
llama-server answers from its prompt cache instead of re-reading everything.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Iterator

from app.config import PROJECT_ROOT, settings
from app.services.llm.client import LlamaServerError, llm_client
from app.services.llm.context_budget import ContextTooLarge
from app.services.llm.context_builder import build_prompt
from app.services.llm.context_strategy import RetrievalContextStrategy
from app.services.retrieval.bm25 import Bm25Index
from app.services.retrieval.chunker import Chunk, chunk_documents

from .scoring import matches_any, score_answer, strip_thinking
from .suite import LANGUAGES, Suite, load_suite

log = logging.getLogger(__name__)

# The corpus is small (about 13,000 characters per language), so with the
# application's default retrieval budget nearly everything would be sent. The
# benchmark retrieves about a third of the corpus instead, which is the
# situation retrieval exists for: a collection larger than the context window.
BENCH_TOP_K = 4
BENCH_MAX_CHARACTERS = 4000


@contextmanager
def _setting(name: str, value: Any) -> Iterator[None]:
    old = getattr(settings, name)
    setattr(settings, name, value)
    try:
        yield
    finally:
        setattr(settings, name, old)


def results_dir() -> Path:
    d = settings.benchmark_dir / "results"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ------------------------------------------------------------------ cases

@dataclass
class Case:
    question: dict[str, Any]
    corpus_language: str
    question_language: str
    strategy: str

    @property
    def text(self) -> str:
        return self.question["question"][self.question_language]

    @property
    def cross(self) -> bool:
        return self.corpus_language != self.question_language


@dataclass
class RunConfig:
    languages: list[str] = field(default_factory=lambda: list(LANGUAGES))
    strategies: list[str] = field(default_factory=lambda: ["full", "retrieval"])
    cross_lingual: bool = True
    categories: list[str] | None = None
    question_ids: list[str] | None = None
    limit: int | None = None  # at most this many questions per category (quick runs)
    max_output_tokens: int = 512
    temperature: float = 0.0
    stemming: bool = True
    label: str = ""


def build_cases(suite: Suite, cfg: RunConfig) -> list[Case]:
    questions = [q for q in suite.questions
                 if (not cfg.categories or q["category"] in cfg.categories)
                 and (not cfg.question_ids or q["id"] in cfg.question_ids)]
    if cfg.limit:
        per_cat: dict[str, int] = {}
        kept = []
        for q in questions:
            per_cat[q["category"]] = per_cat.get(q["category"], 0) + 1
            if per_cat[q["category"]] <= cfg.limit:
                kept.append(q)
        questions = kept
    cases: list[Case] = []
    for corpus_lang in cfg.languages:
        for strategy in cfg.strategies:
            for q in questions:
                cases.append(Case(q, corpus_lang, corpus_lang, strategy))
            if cfg.cross_lingual:
                for q in questions:
                    if q.get("cross"):
                        other = next(l for l in LANGUAGES if l != corpus_lang)
                        cases.append(Case(q, corpus_lang, other, strategy))
    return cases


# ------------------------------------------------------------- retrieval

def _evidence_targets(question: dict, lang: str) -> list[tuple[str, list[str], set[tuple[str, str]]]]:
    """(label, answer patterns, evidence locations) per thing that must be found."""
    def locs(evidence):
        return {(ev["doc"], ev["locator"][lang] if isinstance(ev["locator"], dict) else ev["locator"]) for ev in evidence}
    if question["category"] == "detail":
        return [(question["id"], question["answer"], locs(question["evidence"]))]
    return [(i["name"], i["match"], locs(i["evidence"])) for i in question.get("items", [])]


def _covered(chunks: list[Chunk], patterns: list[str], evidence: set[tuple[str, str]], doc_keys: dict[str, str]) -> bool:
    return any((doc_keys[c.document_id], c.locator) in evidence and matches_any(patterns, c.text) for c in chunks)


def retrieval_check(suite: Suite | None = None, ks: tuple[int, ...] = (1, 3, 5)) -> dict[str, Any]:
    """Recall of the retrieval step, without a model: plain BM25 against the
    language-aware version (stemming, Finnish prefixes, indexed section titles)."""
    suite = suite or load_suite()
    rows: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []
    for stemming in (False, True):
        with _setting("retrieval_stemming", stemming), _setting("retrieval_index_titles", stemming):
            for corpus_lang, corpus in suite.corpora.items():
                doc_keys = {v: k for k, v in corpus.doc_ids.items()}
                for question_lang in LANGUAGES:
                    recall_at = {k: [] for k in ks}
                    context_recall: list[float] = []
                    fallbacks = 0
                    sent_chars: list[int] = []
                    for q in suite.questions:
                        if q["category"] == "unanswerable":
                            continue
                        if question_lang != corpus_lang and not q.get("cross"):
                            continue
                        text = q["question"][question_lang]
                        targets = _evidence_targets(q, corpus_lang)
                        chunks = chunk_documents(corpus.documents, settings.retrieval_chunk_words,
                                                 settings.retrieval_overlap_paragraphs)
                        ranked = [c for c, _ in Bm25Index(chunks).search(text, max(ks))]
                        for k in ks:
                            hits = sum(_covered(ranked[:k], p, e, doc_keys) for _l, p, e in targets)
                            recall_at[k].append(hits / len(targets))
                        strategy = RetrievalContextStrategy(top_k=BENCH_TOP_K, max_characters=BENCH_MAX_CHARACTERS)
                        kept, info = strategy.select(corpus.documents, text)
                        if not kept:  # nothing matched: the app falls back to the full documents
                            fallbacks += 1
                            context_recall.append(1.0)
                            sent_chars.append(len(corpus.text))
                        else:
                            covered = [l for l, p, e in targets if _covered(kept, p, e, doc_keys)]
                            context_recall.append(len(covered) / len(targets))
                            sent_chars.append(info.passage_characters)
                            if len(covered) < len(targets):
                                details.append({
                                    "stemming": stemming, "corpus": corpus_lang, "question_language": question_lang,
                                    "id": q["id"], "question": text,
                                    "missed": [l for l, _p, _e in targets if l not in covered],
                                })
                    n = len(context_recall)
                    rows.append({
                        "stemming": stemming,
                        "corpus": corpus_lang,
                        "question_language": question_lang,
                        "questions": n,
                        **{f"recall@{k}": round(sum(v) / n, 3) for k, v in recall_at.items()},
                        "context_recall": round(sum(context_recall) / n, 3),
                        "fallbacks": fallbacks,
                        "share_of_corpus_sent": round(sum(sent_chars) / n / len(corpus.text), 3),
                    })
    return {
        "settings": {"top_k": BENCH_TOP_K, "max_characters": BENCH_MAX_CHARACTERS,
                     "chunk_words": settings.retrieval_chunk_words, "neighbours": settings.retrieval_neighbours},
        "rows": rows,
        "misses": details,
    }


# ------------------------------------------------------------- full run

def _git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT, capture_output=True,
                              text=True, timeout=5).stdout.strip() or None
    except Exception:  # noqa: BLE001 - informational only
        return None


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9.-]+", "-", text).strip("-")[:60] or "model"


def _case_key(question_id: str, corpus_language: str, question_language: str, strategy: str) -> tuple[str, ...]:
    return (question_id, corpus_language, question_language, strategy)


async def run_cases(
    cfg: RunConfig, suite: Suite | None = None, resume: str | None = None,
    only_strategies: list[str] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield {"type": "start"|"case"|"done", ...}. Results are saved after every case.

    ``resume`` continues an interrupted run: its saved configuration is reused
    and the questions it already answered are skipped. ``only_strategies``
    narrows a resumed run (answers for other strategies are dropped).
    """
    suite = suite or load_suite()
    info = await llm_client.server_info()
    if not info.reachable:
        raise LlamaServerError("llama-server is not running. Start a model before running the benchmark.")
    if resume:
        record = load_result(resume)
        if record.get("model") != info.model_name:
            raise LlamaServerError(
                f"Run {resume} used {record.get('model')}, but llama-server has {info.model_name} loaded."
            )
        saved = record["config"]
        cfg = RunConfig(**{k: v for k, v in saved.items() if k in RunConfig.__dataclass_fields__})
        if only_strategies:
            cfg.strategies = [s for s in cfg.strategies if s in only_strategies]
            record["cases"] = [r for r in record["cases"] if r["strategy"] in cfg.strategies]
            record["config"]["strategies"] = cfg.strategies
        run_id = record["id"]
        record["finished_at"] = None
    cases = build_cases(suite, cfg)
    if resume:
        record["total_cases"] = len(cases)
    else:
        started = datetime.now(timezone.utc)
        run_id = f"{started:%Y%m%d-%H%M%S}_{_slug(info.model_name or 'model')}"
        record = {
            "id": run_id,
            "suite": {"name": suite.data["name"], "version": suite.data["version"]},
            "model": info.model_name,
            "context_size": info.context_size,
            "started_at": started.isoformat(),
            "finished_at": None,
            "commit": _git_commit(),
            "config": {**asdict(cfg), "retrieval_top_k": BENCH_TOP_K, "retrieval_max_characters": BENCH_MAX_CHARACTERS},
            "total_cases": len(cases),
            "cases": [],
        }
    path = results_dir() / f"{run_id}.json"
    done = {_case_key(r["id"], r["corpus_language"], r["question_language"], r["strategy"])
            for r in record["cases"] if "error" not in r}
    # Errors (e.g. a server that went away) are retried on resume.
    record["cases"] = [r for r in record["cases"] if "error" not in r]
    yield {"type": "start", "id": run_id, "model": info.model_name, "total": len(cases), "already_done": len(done)}

    def save() -> None:
        record["summary"] = summarize(record["cases"])
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path)

    for n, case in enumerate(cases, start=1):
        if _case_key(case.question["id"], case.corpus_language, case.question_language, case.strategy) in done:
            continue
        corpus = suite.corpora[case.corpus_language]
        row: dict[str, Any] = {
            "id": case.question["id"],
            "category": case.question["category"],
            "corpus_language": case.corpus_language,
            "question_language": case.question_language,
            "strategy": case.strategy,
            "question": case.text,
        }
        t0 = time.perf_counter()
        try:
            with _setting("retrieval_stemming", cfg.stemming), \
                 _setting("retrieval_top_k", BENCH_TOP_K), \
                 _setting("retrieval_max_characters", BENCH_MAX_CHARACTERS):
                messages, check, strategy_info = await build_prompt(
                    corpus.documents, case.text, strategy=case.strategy, max_output_tokens=cfg.max_output_tokens,
                )
            raw = await llm_client.chat(messages, max_tokens=cfg.max_output_tokens, temperature=cfg.temperature)
            answer, thinking = strip_thinking(raw)
            score = score_answer(
                case.question, answer,
                documents=corpus.documents, corpus_language=case.corpus_language, doc_ids=corpus.doc_ids,
                universes=suite.universes, known=suite.known_numbers(case.text),
            )
            row.update({
                "answer": answer,
                "thinking_characters": thinking,
                "prompt_tokens": check.prompt_tokens,
                "strategy_used": strategy_info.used,
                "passages": strategy_info.passages,
                **score.to_dict(),
            })
        except ContextTooLarge as exc:
            row.update({"error": exc.check.message, "score": 0.0, "correct": False})
        except LlamaServerError as exc:
            row.update({"error": str(exc), "score": 0.0, "correct": False})
        row["seconds"] = round(time.perf_counter() - t0, 1)
        record["cases"].append(row)
        save()
        yield {"type": "case", "n": n, "total": len(cases), "case": row}

    record["finished_at"] = datetime.now(timezone.utc).isoformat()
    save()
    yield {"type": "done", "id": run_id, "summary": record["summary"]}


# --------------------------------------------------------------- summary

def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in rows if "error" not in r]
    detail = [r for r in ok if r["category"] == "detail"]
    lists = [r for r in ok if r["category"] == "list"]
    unans = [r for r in ok if r["category"] == "unanswerable"]
    answerable = detail + lists
    return {
        "cases": len(rows),
        "errors": len(rows) - len(ok),
        # One headline number: detail and unanswerable are right or wrong, a list counts its recall.
        "overall": _mean([r["score"] for r in ok]),
        "detail_accuracy": _mean([1.0 if r["correct"] else 0.0 for r in detail]),
        "list_recall": _mean([r["score"] for r in lists]),
        "list_precision": _mean([r["precision"] for r in lists if r.get("precision") is not None]),
        "abstention_accuracy": _mean([1.0 if r["correct"] else 0.0 for r in unans]),
        "false_abstention_rate": _mean([1.0 if (r["abstained"] and r["score"] == 0) else 0.0 for r in answerable]),
        "unsupported_number_rate": _mean([1.0 if r["unsupported_numbers"] else 0.0 for r in ok]),
        "prompt_leak_rate": _mean([1.0 if r.get("prompt_leak") else 0.0 for r in ok]),
        "citation_rate": _mean([1.0 if r["citations"] else 0.0 for r in answerable]),
        "citation_accuracy": _mean([1.0 if r["citation_hit"] else 0.0 for r in answerable]),
        "seconds_mean": _mean([r["seconds"] for r in ok]),
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        mode = "cross" if r["corpus_language"] != r["question_language"] else "same"
        for key in (
            "all",
            f"strategy={r['strategy']}",
            f"corpus={r['corpus_language']}",
            f"{r['strategy']}/{r['corpus_language']}/{mode}",
            f"{r['question_language']}->{r['corpus_language']}",
        ):
            groups.setdefault(key, []).append(r)
    return {k: _metrics(v) for k, v in sorted(groups.items())}


# ----------------------------------------------------------------- store

def list_results() -> list[dict[str, Any]]:
    out = []
    for p in sorted(results_dir().glob("*.json"), reverse=True):
        if p.stem == "retrieval_check":
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.append({
            "id": data.get("id", p.stem),
            "model": data.get("model"),
            "started_at": data.get("started_at"),
            "finished_at": data.get("finished_at"),
            "total_cases": data.get("total_cases"),
            "completed_cases": len(data.get("cases", [])),
            "config": data.get("config"),
            "summary": (data.get("summary") or {}).get("all"),
        })
    return out


def load_result(run_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", run_id):
        raise KeyError(run_id)
    p = results_dir() / f"{run_id}.json"
    if not p.is_file():
        raise KeyError(run_id)
    return json.loads(p.read_text(encoding="utf-8"))


def delete_result(run_id: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", run_id):
        raise KeyError(run_id)
    p = results_dir() / f"{run_id}.json"
    if not p.is_file():
        raise KeyError(run_id)
    p.unlink()
