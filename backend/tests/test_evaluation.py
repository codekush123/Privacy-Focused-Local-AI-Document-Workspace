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
    # contractions, as frontier models write them
    "The sources don't contain a revenue figure for 2023.",
    "The sources don't say anything about employees in Sweden.",
    "The sources don't give a contract number for the Hietasaari transformer order.",
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
                        universes=suite.universes, known=suite.known_numbers(q["question"][lang], q))


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


def test_list_precision_ignores_contrast_remarks_outside_the_list(suite):
    answer = ("The wind farms not yet in operation are:\n"
              "* Ristineva wind farm [S4: Sheet: Sites]\n"
              "* Tervaharju wind farm [S4: Sheet: Sites]\n\n"
              "Pohjankangas and Lumivaara are already in operation.")
    s = _score(suite, "H09", answer)
    assert s.correct and s.extra_items == [] and s.precision == 1.0
    wrong = _score(suite, "H09", "* Ristineva\n* Tervaharju\n* Lumivaara")
    assert wrong.extra_items == ["Lumivaara"] and not wrong.correct
    # bold lines and table rows count as list items too
    bold = ("Two are not yet in operation:\n\n**Ristineva wind farm** - under construction.\n\n"
            "**Tervaharju wind farm** - in permitting.\n\nThe other two, Pohjankangas and Lumivaara, are in operation.")
    assert _score(suite, "H09", bold).extra_items == []
    table = "| Site | Status |\n| --- | --- |\n| Ristineva | Under construction |\n| Tervaharju | Permitting |"
    assert _score(suite, "H09", table).correct


def test_unanswerable_scoring(suite):
    assert _score(suite, "U02", "The documents do not name a chief financial officer.").correct
    hallucinated = _score(suite, "U02", "The CFO is Markus Lehtovaara [S1: Page 1].")
    assert not hallucinated.correct
    assert _score(suite, "U03", "Haukilahti is a solar park, not a wind farm.").correct  # corrects the false premise


def test_hard_tier_is_harder_by_construction(suite):
    hard = [q for q in suite.questions if q.get("difficulty") == "hard"]
    assert len(hard) == 22
    # computed answers are flagged so the self-check and number metric treat them correctly
    assert {q["id"] for q in hard if q.get("derived")} == {"H01", "H02", "H07", "H08", "H10", "H14", "H17", "H19", "H22"}
    assert any(q["category"] == "unanswerable" for q in hard)


def test_computed_answer_is_not_an_invented_number(suite):
    s = _score(suite, "H01", "The operating wind farms have 150 MW in total [S4: Sheet: Sites].")
    assert s.correct and s.unsupported_numbers == []


def test_difficulty_filter(suite):
    cases = build_cases(suite, RunConfig(difficulties=["hard"], strategies=["full"], cross_lingual=False))
    assert {c.question["id"][0] for c in cases} == {"H"} and len(cases) == 44


def test_frontier_provider_needs_no_llama_server(suite):
    from app.services.evaluation.frontier import DEFAULT_MODELS, _split_system, make_answerer

    system, rest = _split_system([{"role": "system", "content": "S"}, {"role": "user", "content": "Q"}])
    assert system == "S" and rest == [{"role": "user", "content": "Q"}]
    assert set(DEFAULT_MODELS) == {"claude", "openai"}
    with pytest.raises(ValueError):
        make_answerer("someone-else")


def test_the_app_api_cannot_start_a_frontier_run(client):
    """LOCAL ONLY: only the benchmark command line may reach a cloud model.
    The Evaluation tab's run request has no provider field, and an attempt to
    pass one is ignored - the run would use the local llama-server."""
    from app.routers.evaluation import RunRequest

    assert "provider" not in RunRequest.model_fields
    assert "frontier_model" not in RunRequest.model_fields
    assert "provider" not in RunRequest(provider="claude").model_dump()


def test_benchmark_budget_does_not_touch_global_settings():
    from app.config import settings
    from app.services.evaluation.runner import BENCH_MAX_CHARACTERS, BENCH_TOP_K, _bench_strategy

    before = (settings.retrieval_top_k, settings.retrieval_max_characters)
    s = _bench_strategy("retrieval")
    assert (s.top_k, s.max_characters) == (BENCH_TOP_K, BENCH_MAX_CHARACTERS)
    assert (settings.retrieval_top_k, settings.retrieval_max_characters) == before
    assert _bench_strategy("full").name == "full"


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
    assert body["problems"] == [] and len(body["questions"]) == 64
    assert body["by_difficulty"] == {"standard": 42, "hard": 22}


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
