"""API tests. Tests marked ``requires_llama`` run only when llama-server is up."""
from __future__ import annotations

import pytest

from .conftest import PHRASE, requires_llama


def _upload(client, fixtures, name):
    with open(fixtures / name, "rb") as fh:
        r = client.post("/api/documents/upload", files={"file": (name, fh)})
    assert r.status_code == 201, r.text
    return r.json()


def test_health_and_privacy(client):
    assert client.get("/api/health").json()["status"] == "ok"
    p = client.get("/api/privacy").json()
    assert p["mode"] == "LOCAL ONLY"
    assert p["llm_endpoint_is_local"] is True
    assert p["cloud_ai_apis"] is False and p["telemetry"] is False


def test_llm_status_shape(client):
    s = client.get("/api/llm/status").json()
    assert {"connected", "endpoint", "max_output_tokens", "safety_reserve"} <= set(s)


def test_upload_list_get_delete(client, fixtures):
    d = _upload(client, fixtures, "sample.pdf")
    assert d["source_type"] == "pdf" and d["section_count"] == 3
    docs = client.get("/api/documents").json()
    assert [x["id"] for x in docs] == [d["id"]]
    full = client.get(f"/api/documents/{d['id']}").json()
    assert PHRASE in full["full_markdown"]
    preview = client.get(f"/api/documents/{d['id']}", params={"preview_chars": 30}).json()
    assert len(preview["full_markdown"]) == 30
    assert client.delete(f"/api/documents/{d['id']}").status_code == 204
    assert client.get("/api/documents").json() == []
    assert client.delete(f"/api/documents/{d['id']}").status_code == 404


def test_delete_removes_local_files(client, fixtures):
    from pathlib import Path

    d = _upload(client, fixtures, "sample.docx")
    full = client.get(f"/api/documents/{d['id']}").json()
    src = Path(full["source_path"])
    assert src.exists()
    client.delete(f"/api/documents/{d['id']}")
    assert not src.exists()


def test_clear_all(client, fixtures):
    _upload(client, fixtures, "sample.txt")
    _upload(client, fixtures, "sample.csv")
    assert client.delete("/api/documents").json()["deleted"] == 2


def test_upload_rejections(client):
    r = client.post("/api/documents/upload", files={"file": ("evil.exe", b"MZ")})
    assert r.status_code == 415 and "not supported" in r.json()["error"]
    r = client.post("/api/documents/upload", files={"file": ("empty.txt", b"")})
    assert r.status_code == 400
    r = client.post("/api/documents/upload", files={"file": ("broken.pptx", b"not a zip")})
    assert r.status_code == 422
    assert "could not be opened" in r.json()["error"]


def test_filename_sanitized(client):
    r = client.post("/api/documents/upload", files={"file": ("../../evil name.txt", b"hello")})
    assert r.status_code == 201
    assert r.json()["display_name"] == "evil name.txt"


def test_paste_text(client):
    r = client.post("/api/documents/text", json={"text": "pasted " + PHRASE, "name": "note"})
    assert r.status_code == 201 and r.json()["source_type"] == "text"


@pytest.mark.parametrize("url", ["file:///c:/windows/win.ini", "http://localhost:8000/", "http://10.1.1.1/", "javascript:alert(1)"])
def test_url_import_rejects_unsafe(client, url):
    r = client.post("/api/documents/url", json={"url": url})
    assert r.status_code == 422


def test_unknown_document_id_in_chat(client):
    r = client.post("/api/chat", json={"prompt": "hi", "document_ids": ["nope"], "stream": False})
    assert r.status_code == 404


def test_error_shape_is_uniform(client):
    r = client.post("/api/chat", json={"prompt": ""})
    assert r.status_code == 422 and "error" in r.json()


def test_local_only_blocks_remote_endpoint(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "llm_base_url", "https://api.example.com")
    s = client.get("/api/llm/status").json()
    assert s["ai_requests_allowed"] is False and s["connected"] is False
    r = client.post("/api/chat", json={"prompt": "hi", "stream": False})
    assert r.status_code == 403


def test_exports_empty_and_404(client):
    assert client.get("/api/exports").json() == []
    assert client.get("/api/exports/missing").status_code == 404
    assert client.delete("/api/exports/missing").status_code == 404


def test_save_text_export(client):
    r = client.post("/api/exports/save-text", json={"text": "# Answer\nhello", "kind": "md", "prompt": "q"})
    assert r.status_code == 200
    info = r.json()
    d = client.get(info["download_url"])
    assert d.status_code == 200 and d.text.startswith("# Answer")
    assert client.delete(f"/api/exports/{info['id']}").status_code == 204


# ---------------------------------------------------------------- with LLM
@requires_llama
def test_llm_status_reports_model_and_context(client):
    s = client.get("/api/llm/status").json()
    assert s["connected"] and s["model_name"] and s["context_size"] > 0
    assert s["allowed_prompt_tokens"] == s["context_size"] - s["max_output_tokens"] - s["safety_reserve"]


@requires_llama
def test_context_check_counts_tokens(client, fixtures):
    d = _upload(client, fixtures, "sample.pdf")
    r = client.post("/api/context/check", json={"prompt": "Q?", "document_ids": [d["id"]]})
    assert r.status_code == 200
    c = r.json()
    assert c["fits"] is True and c["prompt_tokens"] > 50 and c["strategy"] == "full_context"


@requires_llama
def test_oversized_context_is_refused_not_truncated(client, monkeypatch):
    from app.config import settings

    # Force the budget to be tiny so a small document cannot fit.
    monkeypatch.setattr(settings, "max_output_tokens", 1)
    monkeypatch.setattr(settings, "context_safety_reserve", 10**9)
    r = client.post("/api/documents/text", json={"text": "word " * 500, "name": "big"})
    doc_id = r.json()["id"]
    r = client.post("/api/context/check", json={"prompt": "Q?", "document_ids": [doc_id]})
    assert r.json()["fits"] is False and r.json()["suggestions"]
    r = client.post("/api/chat", json={"prompt": "Q?", "document_ids": [doc_id], "stream": False})
    assert r.status_code == 413
    body = r.json()
    assert "exceed" in body["error"].lower() or "require" in body["error"].lower()
    assert body["suggestions"]
    r = client.post("/api/generate/docx", json={"prompt": "Q?", "document_ids": [doc_id]})
    assert r.status_code == 413


@requires_llama
def test_chat_answers_from_document(client, fixtures):
    d = _upload(client, fixtures, "sample.pdf")
    r = client.post(
        "/api/chat",
        json={"prompt": "Quote the verification phrase exactly.", "document_ids": [d["id"]], "stream": False, "max_output_tokens": 600},
    )
    assert r.status_code == 200, r.text
    assert "BLUE ELEPHANT" in r.json()["answer"].upper()
    assert r.json()["context"]["fits"] is True
