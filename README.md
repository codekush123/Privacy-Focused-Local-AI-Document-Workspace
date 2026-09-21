# Privacy-Focused Local AI Document Workspace (prototype)

A local, desktop-style web application that imports common document formats, converts them into
one normalized Markdown representation, sends the **full content** of the selected documents to a
**locally running LLM** (llama.cpp `llama-server`), and turns the model's answers directly into
downloadable **Word, Excel and PowerPoint** files. No document ever leaves the computer.

> A user can locally import several common document types, use their contents as context for a
> local language model, ask the model to transform or analyze those documents, and directly
> receive useful Word, Excel, or PowerPoint files without sending their private documents to a
> cloud AI provider.

**Status:** prototype (university project, prototype deadline 27 September). All required
workflows work; see [Known limitations](#known-limitations) for what is deliberately not done yet.

---

## Contents

1. [What it does](#what-it-does)
2. [Supported formats](#supported-formats)
3. [Architecture](#architecture)
4. [Prerequisites](#prerequisites)
5. [Setup and running](#setup-and-running)
6. [Using the application](#using-the-application)
7. [Privacy design](#privacy-design)
8. [Configuration](#configuration)
9. [Tests](#tests)
10. [API overview](#api-overview)
11. [Known limitations](#known-limitations)
12. [Project layout](#project-layout)

---

## What it does

* Import PDF, Word, PowerPoint, Excel, CSV, HTML, Markdown, plain text, pasted text or a web URL.
* Every source is converted **locally** into Markdown with locators (`Page 4`, `Slide 7`,
  `Sheet: Results`, `Heading: Introduction`, `Rows 1-100`) so the model can cite where facts come from.
* Select one or more documents and chat with them. The **complete** selected content is sent to
  the model (full-context prompting, no retrieval/RAG in the prototype).
* Before every request the backend renders the real prompt with the model's chat template, counts
  tokens with llama-server's own `/tokenize`, reserves room for the answer, and **refuses** requests
  that do not fit the active context window. Documents are never silently truncated.
* Ask for a Word document, Excel workbook or PowerPoint deck: the model is forced to return JSON
  matching a schema (llama.cpp grammar-constrained output), the JSON is validated with Pydantic,
  and a real `.docx` / `.xlsx` / `.pptx` file is written with python-docx / openpyxl / python-pptx
  and offered for download. Any chat answer can also be downloaded as **Word, PDF, LaTeX,
  Markdown or plain text** with one click (converted locally, no second model call); tables as `.csv`.
* A visible **privacy panel** shows the mode (LOCAL ONLY), runtime, endpoint, model, active context
  size and whether any network access is needed.

### Interactive AI features

| Feature | What the AI does | What the app adds on top |
|---|---|---|
| **Grounded citations** | answers cite `[S1: Page 3]` after every fact | citations are parsed, matched to real sections and rendered as clickable chips that open the exact passage; unmatched citations are flagged; "n/m citations verified" per answer |
| **Fact-check** | splits an answer into claims and labels each supported / partly / unsupported / contradicted with a quoted evidence sentence | grounding score, claim table, evidence linked to its source passage |
| **Study mode** | writes a quiz (multiple choice, true/false, short answer) with a source per question; grades free-text answers as a tutor with feedback | one-question-at-a-time session, rule-based grading for closed questions, score tracking, Excel / Word session report |
| **Ask your data** | turns a question about a CSV/XLSX into a *query plan* (computed columns, filters, group-by, aggregates, sort, limit, chart) | the plan is executed deterministically in Python on the real table, so every number is exact; plan shown for transparency; bar/line chart; Excel export |
| **Privacy Guard** | finds context-dependent personal data (names, addresses, organisations, IDs) | regex layer for e-mail / phone / IBAN / card (Luhn) / Finnish HETU / IP; review table (keep, recategorise, custom replacement); consistent placeholders like `[PERSON-1]`; redacted copy exported and/or added to the library to chat with safely |
| **Translate & export** | translates whole documents preserving headings, lists and tables | one-click download as Word / PDF / LaTeX / Markdown |
| **Quick actions** | summarize, quiz, study notes, compare, action items, explain simply | insert ready-made prompts |

## Supported formats

| Input | Parser | Output | Writer |
|---|---|---|---|
| `.txt`, `.md`, pasted text | built-in (UTF-8 with fallback detection) | `.docx` | python-docx |
| `.html`, `.htm`, web URL (http/https) | BeautifulSoup + markdownify | `.xlsx` | openpyxl |
| `.csv`, `.tsv` | csv (delimiter sniffing) | `.pptx` | python-pptx |
| `.docx` | python-docx | `.pdf` (from an answer) | PyMuPDF Story |
| `.pdf` | PyMuPDF / PyMuPDF4LLM (optional OCR hook) | `.tex` (LaTeX, from an answer) | built-in |
| | | `.csv`, `.md`, `.txt` | built-in |
| `.xlsx`, `.xlsm` | openpyxl (read-only, cached values, no macros) | | |
| `.pptx` | python-pptx | | |

## Architecture

```
 Browser (React + TypeScript + Vite, :5173)
   │  /api (proxied)
   ▼
 FastAPI backend (Python 3.11+, :8000)
   ├─ services/parsers   one parser per format  → DocumentContent (sections + Markdown)
   ├─ services/document_store   data/uploads + data/converted (JSON), delete = remove both
   ├─ services/llm
   │    ├─ client.py           LlamaServerClient: the ONLY place that talks HTTP to llama-server
   │    ├─ context_strategy.py ContextStrategy → FullContextStrategy (RetrievalContextStrategy later)
   │    ├─ context_budget.py   render prompt → /tokenize → compare with active n_ctx
   │    └─ prompts.py          system prompt, <source> wrapping, prompt-injection guidance
   ├─ services/generation.py   prompt → schema-constrained JSON → Pydantic → writer → data/exports
   ├─ services/writers         docx / xlsx / pptx / csv / txt / md
   └─ services/privacy         LOCAL ONLY policy (endpoint must be localhost), status report
   │
   ▼  localhost only
 llama-server (llama.cpp, :8080)   /health  /props  /tokenize  /apply-template  /v1/chat/completions
```

Key design decisions

* **Full-context prompting** is the default and only strategy in the prototype. Custom RAG, vector
  databases and embeddings are intentionally out of scope; `ContextStrategy` is the extension point.
* **Accurate token counting**: prompts are rendered with `/apply-template` and counted with
  `/tokenize`; `characters / 4` estimates are not used for decisions.
* **Context budget** = active `n_ctx` (from `/props`) − reserved output tokens (default 4096) −
  safety reserve (default 1024). If the prompt does not fit, the user gets the exact numbers and
  suggestions (select fewer documents, start llama-server with `-c` larger, use a larger-context model).
* **Structured output**: file generation never parses free-form text. The JSON schema of the
  Pydantic spec (`DocxSpec`, `XlsxSpec`, `PptxSpec`) is passed as `response_format` to llama-server.
* **Source boundaries**: each document is wrapped in `<source id="n" name="...">…</source>` and the
  system prompt tells the model that source content is data, not instructions.

## Prerequisites

* **Python 3.11 or newer** (developed and tested on 3.14)
* **Node.js 20 or newer** (tested on 24) with npm
* **llama.cpp `llama-server`** – binaries from <https://github.com/ggml-org/llama.cpp/releases>
  (or the copy bundled with LM Studio, see `scripts/example_llama_server_command.md`)
* A **GGUF instruct model**, e.g. Qwen2.5-7B-Instruct-Q4_K_M, Llama-3.x-Instruct, Gemma, Phi.
  On a laptop without a GPU a 3–4B model is a good compromise between speed and quality.
* Windows, Linux and macOS should all work; the scripts are provided for PowerShell and bash.

## Setup and running

Three processes run side by side: llama-server, the backend and the frontend.

### 1. Start llama-server (two options)

**Option A - from the app (recommended).** Start the backend and frontend (steps 2 and 3), open
the UI and use the **Model launcher** panel on the right. Enter the path to *your*
`llama-server` executable and *your* `.gguf` model, optionally context size / threads / GPU
layers, and click **Start llama-server**. The paths are stored only on your machine in
`data/llm_settings.json` (git-ignored), so nothing machine-specific ever lands in the repository.
The panel also shows the server log and lets you stop the server again.

**Option B - manually.** Start it yourself in a terminal; the app detects it automatically:

```powershell
llama-server.exe -m "C:\path\to\your-model.gguf" -c 16384 --host 127.0.0.1 --port 8080 --jinja
```

or `scripts\start_llama_server_example.ps1` / `scripts/start_llama_server_example.sh`, which
prompt for the two paths (or read `LLAMA_SERVER_EXE` and `LLAMA_MODEL_PATH`).

* `-c` is the **active context**; the application reads it and uses it as the budget.
* `--jinja` uses the model's own chat template (recommended for JSON output).
* Add `-ngl 99` for GPU offload with CUDA/Vulkan/Metal builds.
* More examples: `scripts/example_llama_server_command.md`.

### 2. Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

or simply `scripts\start_backend.ps1` (`scripts/start_backend.sh`). The API is documented at
<http://127.0.0.1:8000/docs>.

### 3. Frontend

```powershell
cd frontend
npm install
npm run dev
```

or `scripts\start_frontend.ps1`. Open <http://127.0.0.1:5173>. The dev server proxies `/api` to
the backend, so everything is served from one local origin.

### Demo data

`demo_data/` contains a small, coherent teaching set (introductory machine learning): a PDF
handout, a DOCX lecture, a PPTX deck, a CSV/XLSX results sheet and an HTML glossary. Regenerate
with `backend\.venv\Scripts\python demo_data\make_demo_data.py`.

## Using the application

1. **Documents (left)** – drag files onto the drop zone, paste text, or import a URL. Newly
   imported documents are selected automatically; tick/untick to choose which ones the model sees.
   `preview` shows the exact Markdown the model receives. `remove` / `Clear all documents` delete
   the original upload and the converted content.
2. **Chat (middle)** – type a question or use a quick action (Summarize, Generate quiz, Study notes,
   Compare). The context usage (`18,432 / 65,536 tokens`) is shown before you send. Answers stream in.
3. **Download an answer** – under every answer: *Word (.docx)*, *PDF*, *LaTeX (.tex)*,
   *Markdown (.md)*, *Text (.txt)*. The conversion happens locally from the answer's Markdown.
4. **Output mode** – switch the selector from *Answer in chat* to *Generate Word / Excel /
   PowerPoint / CSV* and describe what you want, e.g.
   *"Create 10 quiz questions based only on the provided teaching materials. Include an answer key."*
   The file appears in **Exports (right)** with a Download button.
5. **Model (right)** – llama-server status, model name, active and trained context size, reserved
   output tokens and the live context usage bar.
6. **Model launcher (right)** – enter your own llama-server / model paths and start or stop the
   server from the UI.
7. **Privacy (left, bottom)** – LOCAL ONLY badge, endpoint, model, "Network needed: No (URL import only)".

## Privacy design

Default mode is **LOCAL ONLY**:

* The LLM endpoint must be a loopback address; a non-localhost `LDW_LLM_BASE_URL` blocks all AI
  requests (HTTP 403) and the UI shows a red warning instead of a green badge.
* There are no cloud AI APIs, API keys, analytics or telemetry anywhere in the code.
* Parsing, tokenization, inference and file generation all happen on this machine. Uploaded files,
  converted Markdown and generated files live in `data/` and can be deleted from the UI.
* Logs contain file names, types, sizes, timings, token counts and errors – never document text.
* **Web URL import is the only network operation.** It runs only after an explicit click, shows a
  clear notice, accepts only `http(s)://`, rejects private/loopback/link-local targets and malformed
  URLs, enforces a timeout and a size limit, follows at most five (re-validated) redirects and never
  crawls linked pages. The fetched page is then parsed locally like any HTML file.

Input safety: upload size limit (50 MB default), extension allow-list, sanitized file names,
server-generated IDs, no user-controlled paths, Office files opened read-only without macro or
formula execution, JavaScript in HTML never executed.

## Configuration

Environment variables (or `backend/.env`, see `backend/.env.example`), all prefixed `LDW_`:

| Variable | Default | Meaning |
|---|---|---|
| `LDW_LLM_BASE_URL` | `http://127.0.0.1:8080` | llama-server endpoint |
| `LDW_LOCAL_ONLY` | `true` | require a localhost endpoint |
| `LDW_MAX_OUTPUT_TOKENS` | `4096` | tokens reserved for the answer |
| `LDW_CONTEXT_SAFETY_RESERVE` | `1024` | extra safety margin |
| `LDW_FALLBACK_CONTEXT_SIZE` | `8192` | used only if `/props` reports no `n_ctx` |
| `LDW_MAX_UPLOAD_BYTES` | `52428800` | upload limit |
| `LDW_URL_FETCH_TIMEOUT_SECONDS` / `LDW_URL_MAX_BYTES` | `15` / `5 MB` | URL import limits |
| `LDW_DATA_DIR` | `<repo>/data` | local storage directory |
| `LDW_PDF_OCR` | `false` | try PyMuPDF OCR on image-only PDF pages (needs Tesseract) |

## Tests

```powershell
cd backend
.venv\Scripts\python -m pytest -q
```

* Parser tests: every fixture (TXT, MD, HTML, CSV, DOCX, PDF, XLSX, PPTX) contains the phrase
  `BLUE ELEPHANT 1947` at a known place (PDF page 3, PPTX slide 2, XLSX sheet "Results", …) and the
  tests assert it appears in the normalized Markdown at that locator.
* Multilingual smoke test: English, Finnish, Chinese, Arabic and Russian text survives
  input → parsing → Markdown → prompt. (This checks character handling only, not answer quality.)
* Writer round-trips: generated DOCX/XLSX/PPTX files are re-parsed and checked.
* API tests: upload/list/preview/delete, unsupported types, corrupt files, SSRF rejections,
  uniform error shape, LOCAL ONLY enforcement, export download.
* Tests marked `requires_llama` (status, token counting, oversized-context refusal, answering from a
  document) run automatically when llama-server is reachable and are skipped otherwise.

Fixtures are generated by `tests/make_fixtures.py` on first run. Frontend: `npm run build`
type-checks, `npm run lint` lints.

## API overview

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | backend health |
| GET | `/api/llm/status` | llama-server reachability, model, active context, budget |
| GET | `/api/privacy` | privacy status |
| GET/PUT/POST | `/api/llm/launcher`, `/settings`, `/validate`, `/start`, `/stop` | start/stop llama-server with user-provided paths |
| GET/POST | `/api/documents`, `/upload`, `/text`, `/url` | list / import documents |
| GET | `/api/documents/{id}?preview_chars=N` | normalized content |
| DELETE | `/api/documents/{id}`, `/api/documents` | delete one / all |
| POST | `/api/context/check` | token count vs. active context for a selection |
| POST | `/api/chat` | chat (SSE streaming by default, `stream:false` for JSON) |
| GET | `/api/chat/quick-actions` | quick-action prompts |
| POST | `/api/generate/{docx\|xlsx\|pptx\|csv}` | structured generation → file |
| POST | `/api/exports/save-text` | save an answer as `.docx` / `.pdf` / `.tex` / `.md` / `.txt` |
| GET | `/api/documents/{id}/sections` | sections with locators (citation viewer) |
| POST | `/api/verify` | fact-check an answer against selected documents |
| POST | `/api/study/quiz`, `/grade`, `/report` | study mode |
| GET/POST | `/api/data/{id}/info`, `/api/data/query`, `/api/data/export` | ask your data |
| POST | `/api/privacy/scan`, `/api/privacy/redact` | privacy guard |
| GET/DELETE | `/api/exports`, `/api/exports/{id}` | list / download / delete generated files |

Errors always have the shape `{"error": "...", "suggestions": [...], "context": {...}}` with plain
language messages (`llama-server is not running.`, `The selected documents require approximately
78,000 tokens but the active model context is 65,536 tokens.`, `This file type is not supported.`).

## Known limitations

* **No custom RAG.** Everything selected goes into the prompt; what fits is limited by the active
  llama-server context (`-c`). Large spreadsheets or long books will need retrieval or context
  reduction in the final project.
* **Citations and fact-checks are only as good as the model.** Small models sometimes cite the
  wrong section; the app flags citations that do not match any section, and the fact-check is a
  second model opinion, not ground truth.
* **Model quality depends on the local model.** Small CPU-only models are slow (tens of seconds to
  minutes per request on a laptop) and may make factual or arithmetic mistakes. Reasoning models
  emit `<think>` blocks, which the UI shows collapsed.
* **Office formatting is basic.** Generated files use simple styles (headings, lists, tables,
  bold header rows, frozen headers, title/content slide layouts). Complex visual formatting of
  imported files is not preserved – the goal is semantic content extraction.
* **Images are not interpreted** in PDF, DOCX or PPTX. Image-only PDF pages are reported as such;
  OCR is an optional hook (`LDW_PDF_OCR=true`, needs Tesseract) and was not extensively tested.
* **Excel formulas are not evaluated**; cached values stored in the file are used and a note is
  attached when formulas are present. Very large sheets are capped at 20,000 rows per sheet with a
  visible note.
* **URL import needs the network** and cannot read JavaScript-rendered pages.
* **LaTeX export** is a `.tex` source file, not a compiled PDF; compile it with `pdflatex`
  (`xelatex`/`lualatex` for non-Latin scripts such as Chinese or Arabic).
* **Single user, no authentication, no cloud deployment** – by design for the prototype.
* **Multilingual accuracy is untested**; only character round-tripping is verified.
* LM Studio comparison and the full-context vs. retrieval evaluation are planned for the final
  project; the prototype is structured (same documents, same model, `ContextStrategy` interface)
  so that comparison can be added without redesign.

## Project layout

```
backend/
  app/
    main.py, config.py
    models/document.py          DocumentContent, DocumentSection
    schemas/api.py, artifacts.py  API models; DocxSpec/XlsxSpec/PptxSpec for structured output
    routers/                    system, documents, chat, generate
    services/
      parsers/                  txt/md, html + url_fetcher, csv, docx, pdf, xlsx, pptx
      writers/                  docx, xlsx, pptx, markdown_export (answer -> docx/pdf/tex), simple (csv/md/txt)
      llm/                      client, prompts, context_strategy, context_budget, launcher
      privacy/                  policy
      features/                 citations, verify, study, data_query, privacy_guard, structured
      document_store.py, export_store.py, generation.py
    utils/                      files (sanitizing, ids), logging
  tests/                        pytest suite + fixture generator
  requirements.txt
frontend/
  src/components/               DocumentPanel, ChatPanel (+SourceViewer), StudyPanel, DataPanel,
                                PrivacyGuardPanel, LauncherPanel, StatusPanels (Privacy, Model, Exports)
  src/pages/Workspace.tsx       three-column layout
  src/services/api.ts           API client + SSE streaming
  src/types/api.ts
data/                           uploads/, converted/, exports/, llm_settings.json (all git-ignored)
demo_data/                      demo teaching materials + generator
scripts/                        start_backend, start_frontend, example_llama_server_command
```
