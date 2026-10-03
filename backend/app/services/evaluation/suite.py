"""Load the benchmark suite: the bilingual corpus and its questions.

The corpus files live in ``benchmark/corpus/<lang>/`` and are parsed with the
application's own parsers, so the benchmark measures the real pipeline
(parsing -> context strategy -> model -> citations), not a shortcut. They are
parsed in memory and never added to the user's document library.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import settings
from app.models.document import DocumentContent
from app.services.parsers import parse_file

from .scoring import known_numbers, matches_any

LANGUAGES = ("en", "fi")
LANGUAGE_NAMES = {"en": "English", "fi": "Finnish"}


@dataclass
class Corpus:
    language: str
    documents: list[DocumentContent]  # in the suite's fixed order
    doc_ids: dict[str, str]  # "report" -> document id

    @property
    def text(self) -> str:
        return "\n".join(d.full_markdown for d in self.documents)


@dataclass
class Suite:
    data: dict[str, Any]
    corpora: dict[str, Corpus]

    @property
    def questions(self) -> list[dict[str, Any]]:
        return self.data["questions"]

    @property
    def universes(self) -> dict[str, dict[str, list[str]]]:
        return self.data.get("universes", {})

    def known_numbers(self, question_text: str):
        return known_numbers(*(c.text for c in self.corpora.values()), question_text)

    def summary(self) -> dict[str, Any]:
        by_cat: dict[str, int] = {}
        for q in self.questions:
            by_cat[q["category"]] = by_cat.get(q["category"], 0) + 1
        return {
            "name": self.data["name"],
            "version": self.data["version"],
            "questions": len(self.questions),
            "cross_lingual": sum(1 for q in self.questions if q.get("cross")),
            "by_category": by_cat,
            "languages": list(self.corpora),
            "documents": {
                lang: [{"name": d.display_name, "sections": len(d.sections), "characters": d.character_count}
                       for d in c.documents]
                for lang, c in self.corpora.items()
            },
        }


def suite_dir() -> Path:
    return settings.benchmark_dir


@lru_cache(maxsize=1)
def load_suite() -> Suite:
    root = suite_dir()
    data = json.loads((root / "questions.json").read_text(encoding="utf-8"))
    corpora: dict[str, Corpus] = {}
    for lang in LANGUAGES:
        docs, ids = [], {}
        for key in data["document_order"]:
            filename = data["documents"][key][lang]
            path = root / "corpus" / lang / filename
            doc = parse_file(path, filename)
            doc.id = f"bench-{lang}-{key}"  # stable ids keep results comparable
            docs.append(doc)
            ids[key] = doc.id
        corpora[lang] = Corpus(lang, docs, ids)
    return Suite(data, corpora)


def self_check(suite: Suite | None = None) -> list[str]:
    """Problems with the suite itself: every expected answer must really be in
    the documents, at the location the question claims, in both languages."""
    suite = suite or load_suite()
    problems: list[str] = []
    for lang, corpus in suite.corpora.items():
        sections = {(d.id, s.locator): s.markdown for d in corpus.documents for s in d.sections}
        for q in suite.questions:
            if q["category"] == "unanswerable":
                continue
            targets = [(q["id"], q["answer"], q["evidence"])] if q["category"] == "detail" else [
                (f'{q["id"]}/{i["name"]}', i["match"], i["evidence"]) for i in q["items"]
            ]
            for label, patterns, evidence in targets:
                hit = False
                for ev in evidence:
                    loc = ev["locator"][lang] if isinstance(ev["locator"], dict) else ev["locator"]
                    key = (corpus.doc_ids[ev["doc"]], loc)
                    if key not in sections:
                        problems.append(f"{lang} {label}: locator {loc!r} not found in {ev['doc']}")
                        continue
                    hit = hit or matches_any(patterns, sections[key])
                if not hit:
                    problems.append(f"{lang} {label}: answer not found at any evidence location")
    return problems
