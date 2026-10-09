"""Live answer check: numbers, citations and refusals checked against the sources."""
from __future__ import annotations

import pytest

from app.services.evaluation.suite import load_suite
from app.services.features.answer_check import check_answer, citation_coverage


@pytest.fixture(scope="module")
def en_docs():
    return load_suite().corpora["en"].documents


@pytest.fixture(scope="module")
def fi_docs():
    return load_suite().corpora["fi"].documents


def test_fully_sourced_answer_passes(en_docs):
    c = check_answer("Revenue was EUR 184.6 million in 2025 [S1: Page 3]. In 2024 it was EUR 171.3 million "
                     "[S1: Page 3].", en_docs, "What was the revenue?")
    assert c.status == "ok" and c.unsupported_numbers == [] and c.uncited_sentences == []
    assert c.citations_total == 1 and c.sentences_total == 2


def test_invented_number_is_flagged(en_docs):
    c = check_answer("Revenue was EUR 184.6 million [S1: Page 3]. Operating profit rose to EUR 25.4 million "
                     "thanks to strong demand.", en_docs)
    assert c.status == "review" and c.unsupported_numbers == ["25.4"]
    assert "not found in the sources" in c.summary


def test_numbers_from_the_question_are_known(en_docs):
    c = check_answer("The documents do not report revenue for 2023.", en_docs, "What was the revenue in 2023?")
    assert c.unsupported_numbers == [] and c.status == "not_in_documents"


def test_finnish_notation_and_citation_on_its_own_line(fi_docs):
    c = check_answer("Kuusiranta Energian liikevaihto oli 184,6 miljoonaa euroa vuonna 2025.\n[S1: Page 3]", fi_docs)
    assert c.status == "ok" and c.uncited_sentences == []


def test_unresolved_citation_and_uncited_statement(en_docs):
    answer = ("## Delayed projects\n\n- **Ristineva wind farm** is four months late [S1: Page 4].\n"
              "- Haukilahti solar park is six weeks late.\n\nSee the minutes for details [S7: Page 99].")
    c = check_answer(answer, en_docs)
    assert c.status == "review"
    assert c.unresolved_citations == ["[S7: Page 99]"]
    assert c.uncited_sentences == ["Haukilahti solar park is six weeks late."]


def test_partly_cited_answer(en_docs):
    c = check_answer("The CEO is Markus Lehtovaara [S1: Page 1]. The board is chaired by Anneli Saarinen "
                     "according to the governance page.", en_docs)
    assert c.status == "partly_cited" and len(c.uncited_sentences) == 1


def test_headings_short_fragments_and_list_intros_are_not_statements():
    total, uncited = citation_coverage("# Summary\n\nYes.\n\nThe delayed projects are:\n- Ristineva [S1: Page 4]")
    assert total == 0 and uncited == []  # "Ristineva" alone is too short to count as a statement


def test_no_documents_means_no_check():
    assert check_answer("Paris is the capital of France.", []).status == "no_sources"


def test_thinking_is_ignored(en_docs):
    c = check_answer("<think>maybe 999.9?</think>Revenue was EUR 184.6 million [S1: Page 3].", en_docs)
    assert c.unsupported_numbers == []
