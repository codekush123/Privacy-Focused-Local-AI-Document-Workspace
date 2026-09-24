"""Markdown answer exporters (docx / pdf / tex) and llama-server launcher validation."""
from __future__ import annotations

import pymupdf
import pytest

from app.services.llm.launcher import LauncherSettings, LlamaServerLauncher
from app.services.parsers import parse_file
from app.services.writers.markdown_export import (
    latex_escape,
    markdown_to_docx,
    markdown_to_latex,
    markdown_to_pdf,
    parse_markdown,
)

from .conftest import MULTILINGUAL

ANSWER = """# Quiz

Intro with **bold**, *italic* and `code`. """ + " ".join(MULTILINGUAL.values()) + """

## Questions

1. First question?
2. Second & third (50%)?

- point a
- point b

| Term | Meaning |
|---|---|
| Epoch | one pass |
| F1 | harmonic mean |

> quoted line

```
raw code
```
"""


def test_parse_markdown_blocks():
    kinds = [b.kind for b in parse_markdown(ANSWER)]
    assert kinds == ["heading", "paragraph", "heading", "numbered", "bullets", "table", "quote", "code"]
    table = [b for b in parse_markdown(ANSWER) if b.kind == "table"][0]
    assert table.rows[0] == ["Term", "Meaning"] and table.rows[2] == ["F1", "harmonic mean"]


def test_answer_to_docx(tmp_path):
    out = markdown_to_docx(ANSWER, tmp_path / "a.docx", title="My answer", sources=["lecture.pdf"])
    md = parse_file(out, "a.docx").full_markdown
    assert "My answer" in md and "1. First question?" in md and "* point a" in md
    assert "| F1 | harmonic mean |" in md and "lecture.pdf" in md
    for sample in MULTILINGUAL.values():
        assert sample in md


def test_answer_to_pdf(tmp_path):
    out = markdown_to_pdf(ANSWER, tmp_path / "a.pdf", title="My answer", sources=["lecture.pdf"])
    doc = pymupdf.open(out)
    text = "".join(p.get_text() for p in doc)
    assert doc.page_count >= 1
    assert "My answer" in text and "First question?" in text and "harmonic mean" in text
    assert MULTILINGUAL["finnish"] in text and MULTILINGUAL["russian"] in text


def test_answer_to_latex():
    tex = markdown_to_latex(ANSWER, title="My answer", sources=["lecture.pdf"])
    assert tex.startswith(r"\documentclass") and tex.rstrip().endswith(r"\end{document}")
    assert r"\section*{Quiz}" in tex and r"\begin{enumerate}" in tex and r"\begin{itemize}" in tex
    assert r"Second \& third (50\%)?" in tex  # special characters escaped
    assert r"\textbf{bold}" in tex and r"\emph{italic}" in tex and r"\texttt{code}" in tex
    assert r"\begin{longtable}{ll}" in tex and r"F1 & harmonic mean" in tex
    assert "\\begin{verbatim}\nraw code\n\\end{verbatim}" in tex
    assert latex_escape("a_b#c{d}") == r"a\_b\#c\{d\}"


@pytest.mark.parametrize("kind", ["docx", "pdf", "tex", "md", "txt"])
def test_save_text_endpoint_all_kinds(client, kind):
    r = client.post("/api/exports/save-text", json={"text": ANSWER, "kind": kind, "prompt": "quiz please", "title": "Quiz"})
    assert r.status_code == 200, r.text
    info = r.json()
    assert info["filename"].endswith("." + kind) and info["size_bytes"] > 0
    d = client.get(info["download_url"])
    assert d.status_code == 200
    if kind == "pdf":
        assert d.content.startswith(b"%PDF")
    if kind == "docx":
        assert d.content.startswith(b"PK")


# ---------------------------------------------------------------- launcher
def test_launcher_validation_and_command(tmp_path):
    bad = LauncherSettings(server_path=str(tmp_path / "nope" / "llama-server.exe"), model_path=str(tmp_path / "m.gguf"))
    problems = LlamaServerLauncher.validate_paths(bad)
    assert any("executable not found" in p for p in problems) and any("Model file not found" in p for p in problems)
    assert LlamaServerLauncher.validate_paths(LauncherSettings()) == [
        "Enter the path to your llama-server executable.",
        "Enter the path to a .gguf model file.",
    ]
    exe = tmp_path / "llama-server.exe"
    exe.write_bytes(b"")
    (tmp_path / "notgguf.bin").write_bytes(b"")
    wrong = LauncherSettings(server_path=str(exe), model_path=str(tmp_path / "notgguf.bin"))
    assert any("not a .gguf" in p for p in LlamaServerLauncher.validate_paths(wrong))
    model = tmp_path / "model.gguf"
    model.write_bytes(b"")
    ok = LauncherSettings(server_path=str(exe), model_path=str(model), context_size=4096, threads=4, gpu_layers=10, reasoning_budget_off=True, extra_args="--flash-attn on")
    assert LlamaServerLauncher.validate_paths(ok) == []
    cmd = LlamaServerLauncher().build_command(ok)
    assert cmd[0] == str(exe) and cmd[cmd.index("-c") + 1] == "4096"
    assert "--host" in cmd and cmd[cmd.index("--host") + 1] == "127.0.0.1"
    assert cmd[cmd.index("-t") + 1] == "4" and cmd[cmd.index("-ngl") + 1] == "10"
    assert "--reasoning-budget" in cmd and "--flash-attn" in cmd


def test_launcher_endpoints(client, tmp_path):
    s = client.get("/api/llm/launcher").json()
    assert {"settings", "running", "host", "port", "settings_file"} <= set(s)
    r = client.post("/api/llm/launcher/validate", json={"server_path": "x", "model_path": "y"})
    assert r.json()["ok"] is False and r.json()["problems"]
    r = client.post("/api/llm/launcher/start", json={"server_path": "x", "model_path": "y"})
    assert r.status_code == 400 and "not found" in r.json()["error"]
    r = client.put("/api/llm/launcher/settings", json={"server_path": str(tmp_path / "s.exe"), "model_path": str(tmp_path / "m.gguf"), "context_size": 2048})
    assert r.status_code == 200 and r.json()["settings"]["context_size"] == 2048
    assert client.post("/api/llm/launcher/stop").status_code == 400


def test_launcher_reports_a_foreign_server(client, monkeypatch, tmp_path):
    """A llama-server started outside the app must be reported, not shadowed."""
    from app.services.llm import launcher as mod

    monkeypatch.setattr(mod, "_endpoint_model", lambda timeout=2.0: r"C:\models\SomeOther.gguf")
    body = client.get("/api/llm/launcher").json()
    assert body["foreign_server"] is True and body["loaded_model"] == "SomeOther.gguf"


def test_launcher_refuses_to_start_over_a_foreign_server(client, monkeypatch, tmp_path):
    from app.services.llm import launcher as mod

    exe = tmp_path / "llama-server.exe"; exe.write_bytes(b"")
    model = tmp_path / "model.gguf"; model.write_bytes(b"")
    monkeypatch.setattr(mod, "_endpoint_busy", lambda timeout=2.0: True)
    monkeypatch.setattr(mod, "_endpoint_model", lambda timeout=2.0: r"C:\models\Other.gguf")
    r = client.post("/api/llm/launcher/start", json={"server_path": str(exe), "model_path": str(model)})
    assert r.status_code == 400
    msg = r.json()["error"]
    assert "already running" in msg and "Other.gguf" in msg and "not started from this app" in msg
