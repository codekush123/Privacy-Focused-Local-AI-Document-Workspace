"""Benchmark scoring, the suite itself, answer translation and the evaluation API."""
from __future__ import annotations

import pytest

from app.services.evaluation import runner as runner_mod
from app.services.evaluation.runner import RunConfig, build_cases, retrieval_check, summarize
from app.services.evaluation.scoring import (
    is_abstention,
    leaked_prompt,
    matches,
    number_values,
    score_answer,
    strip_thinking,
    unsupported_numbers,
)
from app.services.evaluation.suite import load_suite, self_check
from app.services.features.translate import protect, restore

# ---------------------------------------------------------------- numbers


@pytest.mark.parametrize("token, values", [
    ("184.6", {184.6}),
    ("184,6", {184.6}),  # Finnish decimal comma
    ("1 148", {1148.0}),  # Finnish thousands space
    ("1,148", {1.148, 1148.0}),  # ambiguous: English thousands or Finnish decimal
    ("61.40", {61.4}),
    ("2025", {2025.0}),
])
def test_number_values(token, values):
    assert number_values(token) == values


@pytest.mark.parametrize("pattern, text, expected", [
    ("num:184.6", "Revenue was EUR 184.6 million [S1: Page 3].", True),
    ("num:184.6", "Liikevaihto oli 184,6 miljoonaa euroa.", True),
    ("num:184.6", "Revenue was EUR 171.3 million.", False),
    ("num:1148", "Yhtiö tuotti 1 148 GWh.", True),
    ("num:22", "22 days were lost in 2025.", True),
    ("num:22", "The figure was 2022.", False),  # no match inside a longer number
    ("pohjanka", "Pohjankankaan tuulipuisto", True),  # Finnish genitive via stem
    (r"re:koski(nen|se)", "projektipäällikkönä toimii Elina Koskinen", True),
    (r"re:koski(nen|se)", "Koskenniskan vesivoimalaitos", False),
])
def test_matches(pattern, text, expected):
    assert matches(pattern, text) is expected


# ------------------------------------------------------------- abstention


@pytest.mark.parametrize("answer", [
    "The documents do not mention a chief financial officer.",
    "This information is not provided in the sources.",
    "There is no information about employees in Sweden.",
    "Asiakirjoissa ei mainita talousjohtajaa.",
    "Liikevaihdosta vuonna 2023 ei ole tietoa lähteissä.",
    "Kuusiranta Energian liikevaihto 2023:ssa ei ole annettu tietoja.",
])
def test_abstention_detected(answer):
    assert is_abstention(answer)


@pytest.mark.parametrize("answer", [
    "Revenue was EUR 184.6 million [S1: Page 3].",
    "Liikevaihto oli 184,6 miljoonaa euroa [S1: Page 3].",
    "The CFO is Markus Lehtovaara.",
])
def test_abstention_not_detected_in_answers(answer):
    assert not is_abstention(answer)


def test_unsupported_numbers_ignore_citations_lists_and_small_counts():
    known = {184.6, 2025.0}
    answer = "1. Revenue was 184.6 [S3: Page 3].\n2. Three projects; profit 99.9 in 2025."
    assert unsupported_numbers(answer, known) == ["99.9"]


def test_thinking_is_stripped_and_prompt_leaks_detected():
    answer, thinking = strip_thinking("<think>let me see</think>The answer is 5.1.")
    assert answer == "The answer is 5.1." and thinking > 0
    assert leaked_prompt("The F1 score is the harmonic mean of precision and recall [S1: Page 3].")
    assert not leaked_prompt("The LTIF was 5.1 [S1: Page 6].")


# ------------------------------------------------------------------ suite


@pytest.fixture(scope="module")
def suite():
    return load_suite()


def test_suite_self_check_passes(suite):
    assert self_check(suite) == []


def test_suite_is_parallel_in_both_languages(suite):
    assert set(suite.corpora) == {"en", "fi"}
    for q in suite.questions:
        assert set(q["question"]) == {"en", "fi"}, q["id"]
    en, fi = (len(suite.corpora[l].documents) for l in ("en", "fi"))
    assert en == fi == 4


def _q(suite, qid):
    return next(q for q in suite.questions if q["id"] == qid)


def _score(suite, qid, answer, lang="en"):
    corpus = suite.corpora[lang]
    q = _q(suite, qid)
    return score_answer(q, answer, documents=corpus.documents, corpus_language=lang, doc_ids=corpus.doc_ids,
                        universes=suite.universes, known=suite.known_numbers(q["question"][lang]))


def test_detail_scoring_and_citation_hit(suite):
    right = _score(suite, "D01", "Revenue was EUR 184.6 million [S1: Page 3].")
    assert right.correct and right.citation_hit
    distractor = _score(suite, "D01", "Revenue was EUR 171.3 million [S1: Page 3].")
    assert not distractor.correct
    finnish = _score(suite, "D01", "Liikevaihto oli 184,6 miljoonaa euroa [S1: Page 3].", lang="fi")
    assert finnish.correct


def test_list_scoring_recall_and_precision(suite):
    s = _score(suite, "L01", "Wind farms: Pohjankangas, Lumivaara and Kivijärvi.")
    assert s.score == 0.5
    assert s.missed_items == ["Ristineva", "Tervaharju"]
    assert s.extra_items == ["Kivijärvi"]  # a solar park listed as a wind farm
    assert s.precision == pytest.approx(2 / 3)


def test_unanswerable_scoring(suite):
    assert _score(suite, "U02", "The documents do not name a chief financial officer.").correct
    hallucinated = _score(suite, "U02", "The CFO is Markus Lehtovaara [S1: Page 1].")
    assert not hallucinated.correct
    assert _score(suite, "U03", "Haukilahti is a solar park, not a wind farm.").correct  # corrects the false premise


def test_cases_are_grouped_for_prompt_caching(suite):
    cases = build_cases(suite, RunConfig(limit=1))
    keys = [(c.corpus_language, c.strategy) for c in cases]
    # each (corpus, strategy) block is contiguous, so the full-context prompt is reused
    assert keys == sorted(keys, key=lambda k: keys.index(k))
    assert any(c.cross for c in cases)


def test_summary_metrics():
    rows = [
        {"id": "D01", "category": "detail", "corpus_language": "en", "question_language": "en", "strategy": "full",
         "score": 1.0, "correct": True, "abstained": False, "precision": None, "unsupported_numbers": [],
         "citations": 1, "citation_hit": True, "prompt_leak": False, "seconds": 2.0},
        {"id": "U01", "category": "unanswerable", "corpus_language": "en", "question_language": "en", "strategy": "full",
         "score": 0.0, "correct": False, "abstained": False, "precision": None, "unsupported_numbers": ["160.2"],
         "citations": 0, "citation_hit": None, "prompt_leak": False, "seconds": 4.0},
    ]
    m = summarize(rows)["all"]
    assert m["overall"] == 0.5 and m["detail_accuracy"] == 1.0 and m["abstention_accuracy"] == 0.0
    assert m["unsupported_number_rate"] == 0.5 and m["citation_accuracy"] == 1.0 and m["seconds_mean"] == 3.0


def test_language_aware_retrieval_beats_plain_bm25_on_finnish(suite):
    rows = retrieval_check(suite)["rows"]
    pick = lambda stem: next(r for r in rows if r["stemming"] is stem and r["corpus"] == "fi" and r["question_language"] == "fi")
    assert pick(True)["recall@3"] > pick(False)["recall@3"]
    assert pick(True)["recall@5"] >= pick(False)["recall@5"]


# ------------------------------------------------------------ translation


def test_translation_protects_and_restores_citations():
    text, markers = protect("Revenue was 184.6 [S1: Page 3]. Turbines by Nordwind [S2: Heading: Project status].")
    assert "[S1" not in text and markers == ["[S1: Page 3]", "[S2: Heading: Project status]"]
    restored, kept, reattached = restore("Liikevaihto oli 184,6 [[C1]]. Voimalat toimittaa Nordwind [[ c2 ]].", markers)
    assert restored == "Liikevaihto oli 184,6 [S1: Page 3]. Voimalat toimittaa Nordwind [S2: Heading: Project status]."
    assert (kept, reattached) == (2, 0)


def test_translation_reattaches_dropped_citations():
    _, markers = protect("A [S1: Page 3]. B [S1: Page 4].")
    restored, kept, reattached = restore("A [[C1]]. B.", markers)
    assert restored.endswith("[S1: Page 4]") and (kept, reattached) == (1, 1)


# --------------------------------------------------------------------- API


def test_eval_suite_endpoint(client):
    r = client.get("/api/eval/suite")
    assert r.status_code == 200
    body = r.json()
    assert body["problems"] == [] and len(body["questions"]) == 42


def test_eval_retrieval_endpoint(client, tmp_path, monkeypatch):
    monkeypatch.setattr(runner_mod, "results_dir", lambda: tmp_path)
    monkeypatch.setattr("app.routers.evaluation.results_dir", lambda: tmp_path)
    r = client.post("/api/eval/retrieval")
    assert r.status_code == 200 and len(r.json()["rows"]) == 8
    assert (tmp_path / "retrieval_check.json").is_file()
    assert client.get("/api/eval/retrieval").status_code == 200


def test_eval_results_reject_bad_ids(client):
    assert client.get("/api/eval/results/..%2F..%2Fsecret").status_code == 404
    assert client.delete("/api/eval/results/does-not-exist").status_code == 404


def test_translate_requires_text(client):
    assert client.post("/api/chat/translate", json={"text": "", "language": "fi"}).status_code == 422
