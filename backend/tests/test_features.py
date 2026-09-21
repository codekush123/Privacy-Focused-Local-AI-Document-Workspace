"""Interactive features: citations, query-plan execution, privacy guard, study reports.
Deterministic parts are tested without a model; AI parts run only with llama-server."""
from __future__ import annotations

import pytest

from app.services.features import data_query as dq
from app.services.features.citations import extract_citations, find_section, source_map
from app.services.features.privacy_guard import RedactionItem, pattern_scan, redact_text
from app.services.features.study import AnswerRecord, build_report
from app.services.parsers import parse_file

from .conftest import requires_llama


def mkplan(**kw) -> dq.QueryPlan:
    base = dict(computed=[], filters=[], group_by="", aggregates=[], select=[], sort=[], limit=0, chart=dq.Chart(), explanation="")
    base.update(kw)
    return dq.QueryPlan(**base)


# --------------------------------------------------------------- citations
def test_citations_resolve_to_sections(fixtures):
    pdf = parse_file(fixtures / "sample.pdf", "sample.pdf")
    pptx = parse_file(fixtures / "sample.pptx", "sample.pptx")
    answer = "Fact A [S1: Page 3]. Fact B [S2: Slide 2]. Loose [S2: slide 2 - second slide]. Bad [S1: Page 42]. Missing [S7: Page 1]."
    cites = extract_citations(answer, [pdf, pptx])
    by = {c.marker: c for c in cites}
    assert by["[S1: Page 3]"].found and by["[S1: Page 3]"].section_id == "s3"
    assert by["[S2: Slide 2]"].found and by["[S2: Slide 2]"].resolved_locator == "Slide 2"
    assert by["[S2: slide 2 - second slide]"].found
    assert not by["[S1: Page 42]"].found and by["[S1: Page 42]"].document_id == pdf.id
    assert not by["[S7: Page 1]"].found and by["[S7: Page 1]"].document_id is None
    assert len(cites) == 5  # de-duplicated by marker
    sm = source_map([pdf, pptx])
    assert sm[0].index == 1 and sm[0].locators == ["Page 1", "Page 2", "Page 3"]
    assert find_section(pptx, "Second Slide") is not None


# ------------------------------------------------------------- data query
@pytest.fixture()
def students(fixtures):
    doc = parse_file(fixtures / "sample.xlsx", "sample.xlsx")
    doc.source_path = str(fixtures / "sample.xlsx")
    return doc


def test_load_table_and_describe(students):
    t = dq.load_table(students)
    assert t.columns == ["Name", "Score", "Grade"] and t.rows[0] == ["Ada", 95, "A"]
    assert t.sheets == ["Students", "Results"]
    desc = dq.describe_table(t)
    assert "Score (number)" in desc and "Rows: 2" in desc
    t2 = dq.load_table(students, sheet="Results")
    assert t2.columns == ["Key", "Value"]


def test_execute_plan_sort_filter_limit_computed(students):
    t = dq.load_table(students)
    plan = mkplan(
        computed=[dq.Computed(name="half", expression="Score / 2")],
        filters=[dq.Filter(column="Score", op=">=", value="80")],
        select=["Name", "half"],
        sort=[dq.Sort(column="half", descending=True)],
        limit=5,
        explanation="test",
    )
    r = dq.execute_plan(t, plan)
    assert r.columns == ["Name", "half"] and r.rows == [["Ada", 47.5]] and r.total_rows == 1


def test_execute_plan_group_by_and_ops():
    t = dq.Table(name="t", columns=["country", "score", "name"], rows=[["FI", 90, "a"], ["FI", 70, "b"], ["SE", 50, "c"], ["SE", None, "d"]])
    plan = mkplan(
        group_by="country",
        aggregates=[dq.Aggregate(column="score", func="avg", alias="avg"), dq.Aggregate(column="name", func="count", alias="n"), dq.Aggregate(column="score", func="max")],
        sort=[dq.Sort(column="avg", descending=True)],
        explanation="",
    )
    r = dq.execute_plan(t, plan)
    assert r.columns == ["country", "avg", "n", "max_score"]
    assert r.rows == [["FI", 80.0, 2, 90], ["SE", 50.0, 2, 50]]
    # text ops
    r2 = dq.execute_plan(t, mkplan(filters=[dq.Filter(column="name", op="in", value="a, c")], select=["name"], explanation=""))
    assert [x[0] for x in r2.rows] == ["a", "c"]
    r3 = dq.execute_plan(t, mkplan(filters=[dq.Filter(column="country", op="contains", value="s")], explanation=""))
    assert r3.row_count == 2
    # overall aggregate without group_by
    r4 = dq.execute_plan(t, mkplan(aggregates=[dq.Aggregate(column="score", func="sum", alias="total")], explanation=""))
    assert r4.rows == [[210]]


def test_execute_plan_rejects_unknown_columns_and_unsafe_expressions():
    t = dq.Table(name="t", columns=["a"], rows=[[1]])
    with pytest.raises(dq.DataQueryError):
        dq.execute_plan(t, mkplan(sort=[dq.Sort(column="zzz")], explanation=""))
    with pytest.raises(dq.DataQueryError):
        dq.execute_plan(t, mkplan(select=["nope"], explanation=""))
    for expr in ["().__class__", "__import__('os')", "a.real", "abs(a)", "a + 'x'"]:
        with pytest.raises(dq.DataQueryError):
            dq.execute_plan(t, mkplan(computed=[dq.Computed(name="x", expression=expr)], explanation=""))
    ok = dq.execute_plan(t, mkplan(computed=[dq.Computed(name="x", expression="(a + 1) * 2.5")], explanation=""))
    assert ok.rows == [[1, 5.0]]


# ---------------------------------------------------------- privacy guard
SAMPLE = (
    "Contact Aino Virtanen at aino.virtanen@example.fi or +358 40 123 4567. HETU 010190-123A. "
    "IBAN FI21 1234 5600 0007 85. Card 4111 1111 1111 1111. Server 192.168.1.10. Not a card: 1234 5678 9012 3456. "
    "Page 3 of 12, year 2024."
)


def test_pattern_scan_categories():
    found = {f.category: f.text for f in pattern_scan(SAMPLE)}
    assert found["email"] == "aino.virtanen@example.fi"
    assert found["phone"] == "+358 40 123 4567"
    assert found["id_number"] == "010190-123A"
    assert found["iban"] == "FI21 1234 5600 0007 85"
    assert found["credit_card"] == "4111 1111 1111 1111"  # Luhn-valid only
    assert found["ip_address"] == "192.168.1.10"
    assert len([f for f in pattern_scan(SAMPLE) if f.category == "credit_card"]) == 1
    assert not any("2024" in f.text or "Page" in f.text for f in pattern_scan(SAMPLE))


def test_redaction_is_consistent_and_longest_first():
    items = [RedactionItem(text="Aino", category="person"), RedactionItem(text="Aino Virtanen", category="person"),
             RedactionItem(text="aino.virtanen@example.fi", category="email", replacement="<mail>")]
    text, mapping = redact_text("Aino Virtanen (Aino) wrote to aino.virtanen@example.fi. AINO again.", items)
    assert text == "[PERSON-1] ([PERSON-2]) wrote to <mail>. [PERSON-2] again."
    assert mapping["Aino Virtanen"] == "[PERSON-1]" and mapping["aino.virtanen@example.fi"] == "<mail>"


def test_privacy_endpoints_without_ai(client, fixtures):
    r = client.post("/api/documents/text", json={"text": SAMPLE, "name": "contacts"})
    doc_id = r.json()["id"]
    s = client.post("/api/privacy/scan", json={"document_id": doc_id, "use_ai": False}).json()
    assert s["ai_used"] is False and any(f["category"] == "email" for f in s["findings"])
    items = [{"text": f["text"], "category": f["category"], "replacement": ""} for f in s["findings"]]
    r = client.post("/api/privacy/redact", json={"document_id": doc_id, "items": items, "export": "docx", "add_to_library": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "aino.virtanen@example.fi" not in body["preview"] and "[EMAIL-1]" in body["preview"]
    assert body["document"]["display_name"] == "contacts (redacted)"
    assert body["export"]["filename"].endswith("_redacted.docx")
    docs = client.get("/api/documents").json()
    assert len(docs) == 2


# ------------------------------------------------------------------- study
def test_study_report_writers(tmp_path):
    recs = [AnswerRecord(question="Q1?", type="short_answer", user_answer="x", correct_answer="y", correct=False, score=30, feedback="Almost", source="[S1: Page 1]"),
            AnswerRecord(question="Q2?", type="true_false", user_answer="True", correct_answer="True", correct=True, score=100)]
    x = build_report("Session", recs, ["a.pdf"], tmp_path / "s.xlsx", "xlsx")
    d = build_report("Session", recs, ["a.pdf"], tmp_path / "s.docx", "docx")
    md_x = parse_file(x, "s.xlsx").full_markdown
    md_d = parse_file(d, "s.docx").full_markdown
    assert "| 1 | Q1? | short_answer | x | y | no | 30 | Almost |" in md_x and "average 65%" in md_x
    assert "1 of 2 correct" in md_d and "Feedback: Almost" in md_d


def test_study_and_data_endpoints_validate(client, fixtures):
    r = client.post("/api/study/report", json={"title": "t", "records": [], "kind": "docx"})
    assert r.status_code == 200
    r = client.post("/api/data/query", json={"document_id": "nope", "question": "x"})
    assert r.status_code == 404
    with open(fixtures / "sample.csv", "rb") as fh:
        doc = client.post("/api/documents/upload", files={"file": ("sample.csv", fh)}).json()
    info = client.get(f"/api/data/{doc['id']}/info").json()
    assert info["columns"] == ["Name", "Score", "Grade"] and info["row_count"] == 5
    r = client.post("/api/data/export", json={"title": "t", "columns": ["a"], "rows": [[1], [None]], "document_id": doc["id"]})
    assert r.status_code == 200 and r.json()["kind"] == "xlsx"


# ------------------------------------------------------------ with llama
@requires_llama
def test_data_query_with_model(client, fixtures):
    with open(fixtures / "sample.xlsx", "rb") as fh:
        doc = client.post("/api/documents/upload", files={"file": ("sample.xlsx", fh)}).json()
    r = client.post("/api/data/query", json={"document_id": doc["id"], "question": "Who has the highest score?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["plan"]["explanation"] and body["rows"]
    assert any("Ada" in str(row) for row in body["rows"])
