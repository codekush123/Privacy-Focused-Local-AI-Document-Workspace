"""Figure extraction / merging and the agent orchestrator.

The deterministic parts (extraction, markdown merging, routing fallbacks, tool
dispatch) are tested without a model; the vision-model tests run only when
llama-server is up with a multimodal projector.
"""
from __future__ import annotations

import httpx
import pytest

from app.config import settings
from app.models.document import DocumentContent, DocumentSection, SourceType
from app.services.agents import orchestrator
from app.services.agents.router_agent import RouteSpec, _describe_documents
from app.services.features.verify import Claim, VerificationResult
from app.services.parsers import parse_file
from app.services.vision import captioner
from app.services.vision.extractor import (
    ImageRecord,
    VisionError,
    extract_images,
    load_records,
    remove_images,
    store_records,
    summary,
)

from .conftest import requires_llama


def vision_available() -> bool:
    try:
        r = httpx.get(f"{settings.llm_base_url}/props", timeout=2)
        return bool((r.json().get("modalities") or {}).get("vision"))
    except Exception:  # noqa: BLE001
        return False


requires_vision = pytest.mark.skipif(not vision_available(), reason="llama-server has no vision projector loaded")


def _demo(name: str) -> DocumentContent:
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "demo_data" / name
    doc = parse_file(path, name)
    doc.source_path = str(path)
    return doc


# ---------------------------------------------------------------- extraction
@pytest.mark.parametrize(
    "name,expected_kind,expected_locator",
    [
        ("intro_machine_learning.pdf", "page_render", "Page 4"),
        ("neural_networks_lecture.docx", "embedded", "Heading: 5. Measured accuracy"),
        ("decision_trees_slides.pptx", "embedded", "Slide 6"),
    ],
)
def test_extract_finds_the_chart(name, expected_kind, expected_locator):
    doc = _demo(name)
    try:
        records = extract_images(doc)
        assert len(records) == 1, [r.model_dump() for r in records]
        r = records[0]
        assert r.kind == expected_kind and r.locator == expected_locator
        assert r.width > 100 and r.height > 100
        assert max(r.width, r.height) <= settings.vision_max_image_px
        from app.services.vision.extractor import image_path

        assert image_path(doc.id, r.filename).read_bytes()[:4] == b"\x89PNG"
        assert summary(records)["total"] == 1
    finally:
        remove_images(doc.id)


def test_extract_rejects_unsupported_type():
    doc = _demo("student_results.csv")
    with pytest.raises(VisionError):
        extract_images(doc)


def test_records_round_trip_through_metadata():
    doc = _demo("student_results.csv")
    rec = ImageRecord(id="a1", document_id=doc.id, locator="Page 1", filename="a1.png", width=300, height=200)
    store_records(doc, [rec])
    back = load_records(doc)
    assert back[0].id == "a1" and back[0].url == f"/api/vision/image/{doc.id}/a1"


# ------------------------------------------------------------------ merging
def _doc_with_sections() -> DocumentContent:
    return DocumentContent(
        id="d1", original_filename="x.pdf", source_type=SourceType.pdf, display_name="x.pdf",
        sections=[
            DocumentSection(section_id="s1", title="Page 1", locator="Page 1", markdown="Intro text."),
            DocumentSection(section_id="s2", title="Page 2", locator="Page 2", markdown="More text."),
        ],
    ).finalize()


def test_merge_inserts_and_refreshes_figure_blocks():
    doc = _doc_with_sections()
    rec = ImageRecord(id="i1", document_id="d1", section_id="s2", locator="Page 2", described=True,
                      figure_type="chart", title="Accuracy", description="Bars per model.",
                      text_in_image="k-NN 0.71", data_points=["k-NN: 0.71", "Neural net: 0.91"])
    captioner.merge_into_document(doc, [rec])
    assert "### Figure 1 - Accuracy" in doc.sections[1].markdown
    assert "Neural net: 0.91" in doc.full_markdown
    assert "Figure" not in doc.sections[0].markdown
    assert doc.metadata["figures_described"] == 1
    assert doc.character_count == len(doc.full_markdown)

    # re-merging must replace, not duplicate
    rec.description = "Updated description."
    captioner.merge_into_document(doc, [rec])
    assert doc.full_markdown.count("### Figure 1") == 1
    assert "Updated description." in doc.full_markdown

    # rejecting the description removes it again
    rec.accepted = False
    captioner.merge_into_document(doc, [rec])
    assert "### Figure" not in doc.full_markdown
    assert doc.metadata["figures_described"] == 0


def test_unmapped_figures_go_to_their_own_section():
    doc = _doc_with_sections()
    rec = ImageRecord(id="i9", document_id="d1", section_id=None, described=True, title="Logo", description="A logo.")
    captioner.merge_into_document(doc, [rec])
    assert doc.sections[-1].locator == "Figures"
    assert "A logo." in doc.full_markdown


# ------------------------------------------------------------------- vision
@requires_vision
def test_describe_chart_reads_values():
    doc = _demo("intro_machine_learning.pdf")
    try:
        records = extract_images(doc)
        import asyncio

        spec = asyncio.run(captioner.describe_image(doc, records[0]))
        assert spec.figure_type in ("chart", "diagram")
        joined = " ".join(spec.data_points) + " " + spec.description
        assert "0.91" in joined and "0.71" in joined
    finally:
        remove_images(doc.id)


def test_vision_status_endpoint(client):
    body = client.get("/api/vision/status").json()
    assert set(body) >= {"available", "supports_vision", "supported_formats"}
    assert body["supported_formats"] == ["docx", "pdf", "pptx"]


def test_vision_endpoints_reject_unsupported_document(client, fixtures):
    with open(fixtures / "sample.csv", "rb") as fh:
        doc = client.post("/api/documents/upload", files={"file": ("sample.csv", fh)}).json()
    r = client.post(f"/api/vision/{doc['id']}/extract")
    assert r.status_code == 422 and "PDF" in r.json()["error"]
    r = client.post(f"/api/vision/{doc['id']}/describe", json={})
    assert r.status_code == 422
    assert client.get("/api/vision/image/nope/x").status_code == 404


def test_extract_and_serve_image(client, fixtures):
    with open(fixtures / "sample.pdf", "rb") as fh:
        doc = client.post("/api/documents/upload", files={"file": ("sample.pdf", fh)}).json()
    body = client.post(f"/api/vision/{doc['id']}/extract").json()
    # the tiny fixture pages have little text, so they are rendered as figures
    assert body["summary"]["total"] >= 1
    img = body["images"][0]
    r = client.get(img["url"])
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    r = client.put(f"/api/vision/{doc['id']}/image/{img['id']}", json={"description": "Manual caption.", "title": "T"})
    assert r.status_code == 200
    full = client.get(f"/api/documents/{doc['id']}").json()
    assert "Manual caption." in full["full_markdown"]


# -------------------------------------------------------------------- agent
def test_router_document_description():
    docs = [_doc_with_sections()]
    text = _describe_documents(docs)
    assert "x.pdf" in text and "2 section(s)" in text
    assert _describe_documents([]) == "(none selected)"


@pytest.mark.anyio
async def test_agent_falls_back_to_answer_when_router_fails(monkeypatch):
    """If the router call fails the run must continue, not crash."""
    async def boom(*_a, **_k):
        raise RuntimeError("router offline")

    async def fake_answer(task, documents, max_tokens=None):
        return "The answer [S1: Page 1].", {"prompt_tokens": 10, "context_size": 100, "fits": True}

    monkeypatch.setattr(orchestrator, "route", boom)
    monkeypatch.setattr(orchestrator, "_answer", fake_answer)
    doc = _doc_with_sections()
    events = [e async for e in orchestrator.run_agent("what is this?", [doc], auto_verify=False)]
    kinds = [(e["step"], e["status"]) for e in events]
    assert ("router", "done") in kinds and ("tool", "done") in kinds
    assert events[-1]["step"] == "result"
    assert events[-1]["answer"].startswith("The answer")
    assert events[-1]["citation_stats"]["resolved"] == 1


@pytest.mark.anyio
async def test_agent_verifies_and_refines_low_grounding(monkeypatch):
    answers = iter(["First answer.", "Improved answer [S1: Page 1]."])
    scores = iter([40, 90])

    async def fake_answer(task, documents, max_tokens=None):
        return next(answers), {"prompt_tokens": 1, "context_size": 10, "fits": True}

    async def fake_route(request, documents):
        return RouteSpec(intent="answer", reasoning="q", confidence="high", task=request,
                         language="", document_hint="", needs_verification=True)

    async def fake_verify(answer, documents):
        score = next(scores)
        return VerificationResult(
            claims=[Claim(claim="c", verdict="unsupported" if score < 50 else "supported", evidence="", source="", note="")],
            overall="x", counts={"supported": 0, "partially_supported": 0, "unsupported": 1, "contradicted": 0},
            grounding_score=score, citations=[],
        )

    monkeypatch.setattr(orchestrator, "route", fake_route)
    monkeypatch.setattr(orchestrator, "_answer", fake_answer)
    monkeypatch.setattr(orchestrator.verify, "verify_answer", fake_verify)
    doc = _doc_with_sections()
    events = [e async for e in orchestrator.run_agent("q", [doc])]
    steps = [e["step"] for e in events]
    assert "verifier" in steps and "refine" in steps
    refine = next(e for e in events if e["step"] == "refine" and e["status"] == "done")
    assert refine["improved"] is True and refine["grounding_score"] == 90
    assert events[-1]["answer"].startswith("Improved")


@pytest.mark.anyio
async def test_agent_blocks_file_generation_when_disabled(monkeypatch):
    async def fake_route(request, documents):
        return RouteSpec(intent="generate_pptx", reasoning="deck", confidence="high", task=request,
                         language="", document_hint="", needs_verification=False)

    async def fake_answer(task, documents, max_tokens=None):
        return "text instead", {"prompt_tokens": 1, "context_size": 10, "fits": True}

    monkeypatch.setattr(orchestrator, "route", fake_route)
    monkeypatch.setattr(orchestrator, "_answer", fake_answer)
    events = [e async for e in orchestrator.run_agent("make slides", [_doc_with_sections()], allow_files=False, auto_verify=False)]
    router_done = next(e for e in events if e["step"] == "router" and e["status"] == "done")
    assert router_done["intent"] == "answer"


@pytest.mark.anyio
async def test_agent_data_query_needs_a_table(monkeypatch):
    async def fake_route(request, documents):
        return RouteSpec(intent="data_query", reasoning="numbers", confidence="medium", task=request,
                         language="", document_hint="", needs_verification=False)

    monkeypatch.setattr(orchestrator, "route", fake_route)
    events = [e async for e in orchestrator.run_agent("average score", [_doc_with_sections()])]
    assert events[-1]["step"] == "error" and "CSV or Excel" in events[-1]["error"]


def test_agent_endpoint_streams_steps(client, fixtures, monkeypatch):
    async def fake_route(request, documents):
        return RouteSpec(intent="answer", reasoning="q", confidence="medium", task=request,
                         language="", document_hint="", needs_verification=False)

    async def fake_answer(task, documents, max_tokens=None):
        return "Hello.", {"prompt_tokens": 1, "context_size": 10, "fits": True}

    monkeypatch.setattr(orchestrator, "route", fake_route)
    monkeypatch.setattr(orchestrator, "_answer", fake_answer)
    with open(fixtures / "sample.txt", "rb") as fh:
        doc = client.post("/api/documents/upload", files={"file": ("sample.txt", fh)}).json()
    with client.stream("POST", "/api/agent/run", json={"request": "hi", "document_ids": [doc["id"]]}) as r:
        assert r.status_code == 200
        text = "".join(r.iter_text())
    assert "event: step" in text and "event: result" in text and "Hello." in text


@requires_llama
def test_agent_tools_listed(client):
    body = client.get("/api/agent/tools").json()
    assert "answer" in body["intents"] and "generate_pptx" in body["intents"]
