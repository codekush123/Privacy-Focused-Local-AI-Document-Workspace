# TESTING.md

How this project is verified. Testing is treated as a first-class part of the work: the final
phase plans at least a quarter of its effort for tests, the benchmark and verification (the hours
log records the actual share), and every accuracy claim in the README is backed by a result file
in `benchmark/results/`.

## Verification layers

| Layer | What it proves | How to run | Needs a model? |
| --- | --- | --- | --- |
| 1. Unit and API tests (212) | parsers, writers, retrieval, citations, scoring, translation and every endpoint behave as specified | `cd backend; .venv\Scripts\python -m pytest -q` | no (9 tests run only when llama-server is up) |
| 2. Benchmark self-check | every expected answer is really in the documents, at the stated location, in both languages | `benchmark\run.py check` | no |
| 3. Retrieval check | the search step puts the answer's passage in front of the model (recall@k) | `benchmark\run.py retrieval` | no |
| 4. Model benchmark | the whole pipeline answers correctly, cites correctly and refuses when it should | `benchmark\run.py run ...` | yes |
| 5. Frontier reference | how far the local models are from frontier models on the same questions | `benchmark\run.py run --provider claude` / `--provider openai` | API key (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY`) |
| 6. Frontend checks | types and lint | `cd frontend; npm run build; npm run lint` | no |
| 7. Browser smoke test | the main flows work in a real browser: upload selects the document, Finnish answer with a verified citation, citation opens the source viewer, live answer check, translation keeps citations, verified timeline, Evaluation tab | `backend\.venv\Scripts\python scripts\ui_smoke_test.py` | yes (all three processes running) |

### 1. Unit and API tests (`backend/tests/`)

| File | Tests | Covers |
| --- | ---: | --- |
| `test_parsers.py` | 27 | every format keeps the marker phrase at its known locator (PDF page, PPTX slide, XLSX sheet, DOCX heading); HTML noise removal; multilingual characters; corrupt and unsupported files |
| `test_writers_and_context.py` | 26 | DOCX/XLSX/PPTX/CSV writers round-trip; full-context prompt building; multilingual prompt text; localhost policy; URL import safety (unsafe targets rejected) |
| `test_retrieval.py` | 22 | chunking keeps locators; BM25 ranking; retrieval/auto strategies; Finnish case endings match with stemming and miss without; language detection; citation format repair |
| `test_api.py` | 21 | upload/list/delete, file-name sanitising, URL-import rejection, uniform error shape, LOCAL ONLY blocks a remote endpoint; with a model: token counting, oversized context refused (not truncated), answering from a document |
| `test_vision_and_agent.py` | 18 | figure extraction and merging, vision endpoints, agent routing, verify-and-refine, file generation gate, streamed agent steps |
| `test_exports_and_launcher.py` | 14 | answer export to DOCX/PDF/LaTeX/Markdown/text; launcher path validation and command building, port handling, refusing to start over a foreign server |
| `test_features.py` | 11 | citation resolution; data-query plans executed in code (unsafe expressions rejected); privacy-guard patterns and consistent redaction; study reports |
| `test_answer_check.py` | 9 | live answer check: invented numbers flagged, numbers from the question and Finnish notation accepted, uncited statements and unresolved citations listed, refusals recognised |
| `test_timeline.py` | 13 | timeline verification: real English and Finnish dates verified, a date that belongs to another event or is invented flagged (also when generic words match), a wrong location or source number corrected, the 15-event cap, sorting, the endpoint and the Excel export |
| `test_evaluation.py` | 51 | benchmark scoring rules (EN/FI numbers, refusals, lists, citations), suite self-check, hard tier, retrieval check, translation keeps citations, evaluation API |

Tests that need a running model are marked and skipped automatically when llama-server is not
reachable. Fixtures are generated on first run by `tests/make_fixtures.py`.

### 4. The model benchmark

Full description and results: README -> [Evaluation report](README.md#evaluation-report).

- **Corpus:** four documents (PDF, DOCX, PPTX, XLSX) about a fictional company, in English and
  Finnish with identical facts. Fictional so that a correct answer can only come from the documents.
- **Questions:** 64 per language in two tiers.
  - *Standard* (42): small details next to distractors, "find all similar items" lists, and
    questions the documents cannot answer.
  - *Hard* (22): multi-step questions across documents, arithmetic over tables (sums, differences,
    averages, shares), largest/smallest value with a trap, negation, and near-miss traps. Added
    because the strongest local model scored 97 % on the standard tier - a benchmark that
    everything passes cannot rank models. Qwen3.5-4B scores 89 % on it.
  - 29 questions are also asked across languages (English question, Finnish documents and the reverse).
- **Scoring:** deterministic text rules, no LLM judge, so results are reproducible and auditable.
- **Scoring fixes** are applied to saved answers with `run.py rescore`; models are not re-run and
  expected answers are not changed.
- **Results** are written after every question to `benchmark/results/<timestamp>_<model>.json`
  and can be reviewed answer by answer in the app's Evaluation tab.

## When to run what

| You changed ... | Run at least |
| --- | --- |
| any Python code | layer 1 |
| a parser | layer 1, then layer 2 (the corpus is parsed with the real parsers) |
| retrieval / chunking | layers 1 and 3; compare with `benchmark/results/retrieval_check.json` |
| a prompt, context strategy or citation logic | layers 1 and 4 (`run --quick`, then a full run before reporting numbers) |
| `benchmark/make_questions.py` or `corpus_text.py` | regenerate (`make_questions.py`, `make_corpus.py`), then layers 2 and 4 |
| frontend | layer 6 and a manual click-through of the changed tab |

## Rules for the benchmark

- **Never edit expected answers to make a model pass.** Fix the question only if the self-check or
  a reviewer shows the question itself is wrong or ambiguous, and say so in the commit message.
- **Keep it hard enough.** If the best local model scores above ~95 % on a tier, that tier no
  longer separates models; add harder questions rather than celebrating.
- **Report like-for-like.** Compare models only on the same questions, strategy and settings; the
  report states which run each number comes from.
- **State the limits.** Small corpus, one run per model, settings tuned on the same benchmark -
  these are written down in the README, not hidden.

### 7. Browser smoke test (`scripts/ui_smoke_test.py`)

Drives Microsoft Edge (or Chromium) with Playwright through the flows a user and the demo video
rely on, and fails on any browser console error, failed request or HTTP error. Its first run on
9 October found four problems that no unit test could see, all fixed and now covered:

| Found in the browser | Cause | Fix |
| --- | --- | --- |
| Clicking a citation opened an empty browser tab instead of the source passage | the Markdown renderer's safe-URL filter blanked the app's `cite:` links | a URL filter that keeps only `cite:<n>` and passes everything else through the default (`services/text.ts`) |
| A newly uploaded document was not selected in `npm run dev` | React StrictMode runs state updaters twice in development; the "is new" check had a side effect | the check runs before the state update (`Workspace.tsx`) |
| "Vastaa suomeksi" was ignored when no document was selected | the language rule was only added to the with-documents prompt | applied to both prompts; unit test `test_answer_language_applies_with_and_without_documents` |
| A 404 on every page load | the page declared no icon, so the browser asked for `/favicon.ico` | `<link rel="icon">` in `index.html` |

## Manual checks before a release

1. Start Qwen3.5-4B from the Model launcher with "Disable thinking".
2. Import `demo_data/` and the Finnish benchmark documents; ask one English and one Finnish
   question; click a citation; translate an answer with _Suomeksi_; download it as Word.
3. Evaluation tab: run the retrieval check and a quick benchmark; open the answers of a run.
4. Stop llama-server and confirm the app reports it clearly instead of failing.
