"""Browser smoke test of the main user flows (Playwright, real browser).

What it checks, end to end through the UI:
  1. uploading a document selects it automatically;
  2. a question asked in English with "Vastaa suomeksi" is answered in Finnish,
     from the document, with a verified citation;
  3. clicking the citation opens the source viewer (not a new tab);
  4. "In English" adds a translated copy whose citation still resolves;
  5. the Evaluation tab loads and the retrieval check runs;
  plus: no browser console errors, failed requests or HTTP errors.

Needs three running processes - llama-server with a model, the backend (:8000)
and the frontend (:5173) - and Playwright:

    backend/.venv/Scripts/python -m pip install playwright
    backend/.venv/Scripts/python scripts/ui_smoke_test.py            # uses Microsoft Edge
    backend/.venv/Scripts/python scripts/ui_smoke_test.py --chromium # after `playwright install chromium`

The uploaded test document is removed again at the end. Screenshots are saved
to ui-smoke-shots/ (git-ignored). The first answer takes minutes on a CPU.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCUMENT = ROOT / "benchmark" / "corpus" / "en" / "annual_report_2025.pdf"
APP = "http://127.0.0.1:5173"
API = "http://127.0.0.1:8000"


def remove_test_document() -> None:
    with urllib.request.urlopen(f"{API}/api/documents") as r:
        for d in json.load(r):
            if d["display_name"] == DOCUMENT.name:
                urllib.request.urlopen(urllib.request.Request(f"{API}/api/documents/{d['id']}", method="DELETE"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chromium", action="store_true", help="use Playwright's Chromium instead of Microsoft Edge")
    ap.add_argument("--shots", default=str(ROOT / "ui-smoke-shots"), help="screenshot folder")
    args = ap.parse_args()
    from playwright.sync_api import sync_playwright

    shots = Path(args.shots)
    shots.mkdir(exist_ok=True)
    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        print(f"[{time.strftime('%H:%M:%S')}] {'PASS' if ok else 'FAIL'}  {what}", flush=True)
        if not ok:
            problems.append(what)

    remove_test_document()  # start clean
    with sync_playwright() as p:
        browser = p.chromium.launch(**({} if args.chromium else {"channel": "msedge"}), headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 950})
        page.on("console", lambda m: m.type == "error" and problems.append(f"console error: {m.text}"))
        page.on("requestfailed", lambda r: problems.append(f"request failed: {r.url}"))
        page.on("response", lambda r: r.status >= 400 and problems.append(f"HTTP {r.status}: {r.url}"))
        try:
            page.goto(f"{APP}/#chat")
            page.wait_for_selector(".tabs")

            page.set_input_files("input[type=file]", str(DOCUMENT))
            doc = page.locator(f"aside.side.left label:has-text('{DOCUMENT.name}') input")
            doc.wait_for(timeout=60000)
            page.wait_for_function("el => el.checked", arg=doc.element_handle(), timeout=10000)
            check(doc.is_checked(), "uploaded document is selected automatically")

            page.select_option("select[title*='Language of the answer']", "fi")
            page.fill(".composer textarea", "What was the company's revenue in 2025?")
            page.click(".composer button.btn.primary")
            page.wait_for_selector(".msg.assistant .msg-footer", timeout=900000)
            first = page.locator(".msg.assistant").first
            answer = first.locator(".bubble").inner_text()
            page.screenshot(path=shots / "1_finnish_answer.png", full_page=True)
            check("184,6" in answer, f"answer is in Finnish notation and from the document: {answer[:120]!r}")
            check("1/1 citations verified" in first.inner_text() or "citations verified" in first.inner_text(),
                  "answer has a verified citation")

            chip = first.locator(".cite-chip").first
            check(chip.count() == 1, "citation is rendered as a clickable chip")
            pages_before = len(page.context.pages)
            chip.click()
            page.wait_for_selector(".modal", timeout=10000)
            page.screenshot(path=shots / "2_source_viewer.png")
            check(len(page.context.pages) == pages_before and page.locator(".modal").count() == 1,
                  "clicking the citation opens the source viewer, not a new tab")
            page.click(".modal button:has-text('Close')")

            first.locator(".msg-footer").get_by_role("button", name="In English").click()
            page.wait_for_selector("text=English translation", timeout=600000)
            translated = page.locator(".msg.assistant").nth(1)
            text = translated.locator(".bubble").inner_text()
            page.screenshot(path=shots / "3_translation.png", full_page=True)
            check("184.6" in text, f"translation is in English: {text[:120]!r}")
            check(translated.locator(".cite-chip").count() >= 1, "translated answer keeps a clickable citation")

            page.click("button.tab:has-text('Evaluation')")
            page.wait_for_selector("text=suite self-check passed", timeout=60000)
            page.click("text=Run retrieval check")
            page.wait_for_selector("text=language-aware", timeout=120000)
            page.screenshot(path=shots / "4_evaluation.png", full_page=True)
            check(True, "Evaluation tab loads and the retrieval check runs")
        except Exception as exc:  # noqa: BLE001 - report every failure the same way
            page.screenshot(path=shots / "failure.png", full_page=True)
            problems.append(f"step failed: {exc}")
        finally:
            browser.close()
            remove_test_document()

    print("\nRESULT:", "all checks passed" if not problems else f"{len(problems)} problem(s)")
    for x in problems:
        print("  -", x)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
