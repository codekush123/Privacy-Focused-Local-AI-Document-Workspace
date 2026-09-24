"""Chunking, BM25 ranking and the switchable context strategies."""
from __future__ import annotations

import pytest

from app.models.document import DocumentContent, DocumentSection, SourceType
from app.services.llm.context_strategy import (
    AutoContextStrategy,
    FullContextStrategy,
    RetrievalContextStrategy,
    available_strategies,
    get_strategy,
)
from app.services.retrieval.bm25 import Bm25Index, content_terms, tokenize
from app.services.retrieval.chunker import chunk_documents

from .conftest import MULTILINGUAL, requires_llama


def _doc(sections: list[tuple[str, str]], name: str = "doc.pdf", doc_id: str = "d1") -> DocumentContent:
    return DocumentContent(
        id=doc_id, original_filename=name, source_type=SourceType.pdf, display_name=name,
        sections=[
            DocumentSection(section_id=f"s{i}", title=loc, locator=loc, markdown=text)
            for i, (loc, text) in enumerate(sections, start=1)
        ],
    ).finalize()


LECTURE = _doc([
    ("Page 1", "Machine learning studies algorithms that improve with experience.\n\n"
               "Supervised learning uses labelled input output pairs for prediction."),
    ("Page 2", "Overfitting means the model learns noise instead of the pattern.\n\n"
               "Cross validation repeats the split and averages the results."),
    ("Page 3", "The F1 score is the harmonic mean of precision and recall.\n\n"
               "Precision is TP divided by TP plus FP, recall is TP over TP plus FN."),
])


# --------------------------------------------------------------- chunking
def test_chunks_keep_their_locator():
    chunks = chunk_documents([LECTURE], target_words=20, overlap_paragraphs=1)
    assert chunks, "expected chunks"
    assert {c.locator for c in chunks} == {"Page 1", "Page 2", "Page 3"}
    assert all(c.document_index == 1 and c.document_name == "doc.pdf" for c in chunks)
    assert all(c.section_id for c in chunks)
    # order is per document and strictly increasing
    assert [c.order for c in chunks] == sorted(c.order for c in chunks)


def test_chunker_never_splits_across_sections():
    chunks = chunk_documents([LECTURE], target_words=5, overlap_paragraphs=0)
    for c in chunks:
        assert c.text in LECTURE.sections[int(c.section_id[1:]) - 1].markdown


def test_chunker_terminates_on_a_paragraph_larger_than_the_target():
    """Regression: an oversized paragraph used to be re-added as overlap forever."""
    huge = " ".join(f"word{i}" for i in range(2000))
    doc = _doc([("Page 1", f"{huge}\n\nshort tail paragraph\n\n{huge}")])
    chunks = chunk_documents([doc], target_words=50, overlap_paragraphs=1)
    assert 2 <= len(chunks) <= 6
    assert any("short tail paragraph" in c.text for c in chunks)


def test_tables_stay_in_one_chunk():
    table = "| a | b |\n| --- | --- |\n" + "\n".join(f"| {i} | {i * 2} |" for i in range(40))
    doc = _doc([("Sheet: Data", table)])
    chunks = chunk_documents([doc], target_words=20, overlap_paragraphs=0)
    assert len(chunks) == 1 and chunks[0].text.count("\n") == table.count("\n")


# ------------------------------------------------------------------- bm25
def test_tokenize_handles_scripts_and_stopwords():
    assert tokenize("The Quick brown-fox!") == ["quick", "brown", "fox"]
    assert tokenize("a of the is") == []
    for lang, sample in MULTILINGUAL.items():
        assert tokenize(sample), f"{lang} produced no tokens"
    assert tokenize("你好世界") == ["你", "好", "世", "界"]  # CJK indexed per character
    assert content_terms("summarize this") == ["summarize"]
    assert content_terms("what is it?") == []


def test_bm25_ranks_the_relevant_passage_first():
    chunks = chunk_documents([LECTURE], target_words=30, overlap_paragraphs=0)
    index = Bm25Index(chunks)
    top = index.search("What is the F1 score formula?", top_k=1)
    assert top and "harmonic mean" in top[0][0].text
    assert index.search("precision and recall", top_k=1)[0][0].locator == "Page 3"
    assert index.search("overfitting noise", top_k=1)[0][0].locator == "Page 2"
    assert index.search("zzzznothing", top_k=3) == []


# ------------------------------------------------------------- strategies
def test_retrieval_selects_only_matching_passages_and_keeps_the_source_format():
    messages, info = RetrievalContextStrategy(top_k=2, neighbours=0).build([LECTURE], "What is the F1 score formula?")
    system = messages[0]["content"]
    assert info.used == "retrieval" and 0 < info.passages < info.passages_available
    assert "harmonic mean" in system
    assert "Cross validation" not in system  # an unrelated passage was left out
    # the <source> / locator shape is identical to full context, so citations still work
    assert '<source id="1" name="doc.pdf">' in system and "## Page 3" in system
    assert info.locators == ["doc.pdf - Page 3"]
    assert [m["role"] for m in messages] == ["system", "user"]


def test_retrieval_falls_back_when_the_question_has_no_searchable_terms():
    messages, info = RetrievalContextStrategy().build([LECTURE], "summarise this for me")
    assert info.used == "full"
    assert "no searchable terms" in info.reason or "no passage matched" in info.reason
    assert "Cross validation" in messages[0]["content"]  # everything is there


def test_retrieval_respects_the_character_budget():
    _m, info = RetrievalContextStrategy(max_characters=400, neighbours=0, top_k=5).build([LECTURE], "precision recall F1")
    assert info.passage_characters <= 400 and info.passages >= 1
    # A budget smaller than any single passage still returns the best one rather
    # than quietly falling back to the entire document.
    _m2, tiny = RetrievalContextStrategy(max_characters=10, neighbours=0, top_k=5).build([LECTURE], "precision recall F1")
    assert tiny.used == "retrieval" and tiny.passages == 1


def test_retrieval_keeps_multiple_documents_apart():
    other = _doc([("Slide 1", "Gini index and entropy measure impurity when splitting a tree.")],
                 name="trees.pptx", doc_id="d2")
    messages, info = RetrievalContextStrategy(top_k=3, neighbours=0).build([LECTURE, other], "Which impurity measures split a tree?")
    system = messages[0]["content"]
    assert '<source id="2" name="trees.pptx">' in system and "Gini" in system
    assert info.used == "retrieval"


def test_auto_switches_on_size():
    small = AutoContextStrategy(threshold_characters=10**6).build([LECTURE], "F1 score")[1]
    large = AutoContextStrategy(threshold_characters=10).build([LECTURE], "F1 score")[1]
    assert small.used == "full" and "small" in small.reason
    assert large.used == "retrieval" and "large" in large.reason
    assert small.name == large.name == "auto"


def test_full_context_is_unchanged():
    messages, info = FullContextStrategy().build([LECTURE], "anything")
    assert info.used == "full"
    for section in LECTURE.sections:
        assert section.markdown.split("\n")[0] in messages[0]["content"]


def test_strategy_registry():
    assert get_strategy("full").name == "full"
    assert get_strategy("retrieval").name == "retrieval"
    assert get_strategy("auto").name == "auto"
    with pytest.raises(ValueError):
        get_strategy("nope")
    assert {s["id"] for s in available_strategies()} == {"full", "retrieval", "auto"}


def test_no_documents_is_handled():
    messages, _info = RetrievalContextStrategy().build([], "hello")
    assert [m["role"] for m in messages] == ["system", "user"]


# -------------------------------------------------------------------- API
def test_strategies_endpoint(client):
    body = client.get("/api/context/strategies").json()
    assert {s["id"] for s in body["strategies"]} == {"full", "retrieval", "auto"}
    assert body["default"] in {"full", "retrieval", "auto"}


@requires_llama
def test_context_check_reports_the_strategy(client, fixtures):
    with open(fixtures / "sample.pdf", "rb") as fh:
        doc = client.post("/api/documents/upload", files={"file": ("sample.pdf", fh)}).json()
    body = client.post("/api/context/check", json={
        "prompt": "What is the verification phrase?", "document_ids": [doc["id"]], "strategy": "retrieval",
    }).json()
    assert body["strategy"] == "retrieval"
    assert "strategy_info" in body and body["strategy_info"]["used"] in ("retrieval", "full")


@requires_llama
def test_compare_endpoint_reports_the_saving(client, fixtures):
    with open(fixtures / "sample.pdf", "rb") as fh:
        doc = client.post("/api/documents/upload", files={"file": ("sample.pdf", fh)}).json()
    body = client.post("/api/context/compare", json={
        "prompt": "What is the verification phrase?", "document_ids": [doc["id"]],
    }).json()
    assert body["full"]["prompt_tokens"] > 0 and body["retrieval"]["prompt_tokens"] > 0
    assert body["saving"]["tokens"] == body["full"]["prompt_tokens"] - body["retrieval"]["prompt_tokens"]
    # The fixture is three short pages, so retrieval's fixed overhead is not worth
    # it and the endpoint must say so rather than claim a saving.
    assert body["recommended"] == "full" and "no more than" in body["note"]


# ---------------------------------------------------- citation robustness
def test_markdown_style_citations_are_repaired():
    from app.services.features.citations import extract_citations, normalize_citations

    bad = "[The F1 score is the harmonic mean of precision and recall.](S1: Page 3)"
    assert normalize_citations(bad) == "The F1 score is the harmonic mean of precision and recall. [S1: Page 3]"
    cites = extract_citations(bad, [LECTURE])
    assert len(cites) == 1 and cites[0].found and cites[0].resolved_locator == "Page 3"
    # ordinary Markdown links must be left alone
    link = "See [the documentation](https://example.com/page) for details."
    assert normalize_citations(link) == link
    # already-correct citations are untouched
    good = "The F1 score is the harmonic mean [S1: Page 3]."
    assert normalize_citations(good) == good
