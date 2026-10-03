# Privacy-Focused Local AI Document Workspace (prototype)

A local, desktop-style web application that imports common document formats, converts them into
one normalized Markdown representation, sends the **full content** of the selected documents to a
**locally running LLM** (llama.cpp `llama-server`), and turns the model's answers directly into
downloadable **Word, Excel and PowerPoint** files. No document ever leaves the computer.

> A user can locally import several common document types, use their contents as context for a
> local language model, ask the model to transform or analyze those documents, and directly
> receive useful Word, Excel, or PowerPoint files without sending their private documents to a
> cloud AI provider.

The application works in **English and Finnish**: it can answer in either language regardless of
the documents' language, translate any answer, and its accuracy in both languages is measured with
the project's own benchmark (see the [evaluation report](#evaluation-report)).

---

## Contents

1. [What it does](#what-it-does)
2. [Supported formats](#supported-formats)
3. [Evaluation report](#evaluation-report)
4. [Architecture](#architecture)
5. [Prerequisites](#prerequisites)
6. [Setup and running](#setup-and-running)
7. [Using the application](#using-the-application)
8. [Privacy design](#privacy-design)
9. [Configuration](#configuration)
10. [Tests](#tests)
11. [API overview](#api-overview)
12. [Known limitations](#known-limitations)
13. [Project layout](#project-layout)

---

## What it does

- Import PDF, Word, PowerPoint, Excel, CSV, HTML, Markdown, plain text, pasted text or a web URL.
- Every source is converted **locally** into Markdown with locators (`Page 4`, `Slide 7`,
  `Sheet: Results`, `Heading: Introduction`, `Rows 1-100`) so the model can cite where facts come from.
- Select one or more documents and chat with them. How the documents become a prompt is a
  **switchable strategy**: _full context_ (everything), _retrieval_ (only the matching passages) or
  _automatic_ (full while it is small, retrieval once it is not). Both build the same
  `<source>` blocks with the same locators, so citations work identically either way.
- Before every request the backend renders the real prompt with the model's chat template, counts
  tokens with llama-server's own `/tokenize`, reserves room for the answer, and **refuses** requests
  that do not fit the active context window. Documents are never silently truncated.
- Ask for a Word document, Excel workbook or PowerPoint deck: the model is forced to return JSON
  matching a schema (llama.cpp grammar-constrained output), the JSON is validated with Pydantic,
  and a real `.docx` / `.xlsx` / `.pptx` file is written with python-docx / openpyxl / python-pptx
  and offered for download. Any chat answer can also be downloaded as **Word, PDF, LaTeX,
  Markdown or plain text** with one click (converted locally, no second model call); tables as `.csv`.
- A visible **privacy panel** shows the mode (LOCAL ONLY), runtime, endpoint, model, active context
  size and whether any network access is needed.

### Interactive AI features

| Feature                       | What the AI does                                                                                                                                                                | What the app adds on top                                                                                                                                                                                                                           |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Grounded citations**        | answers cite `[S1: Page 3]` after every fact                                                                                                                                    | citations are parsed, matched to real sections and rendered as clickable chips that open the exact passage; unmatched citations are flagged; "n/m citations verified" per answer                                                                   |
| **Fact-check**                | splits an answer into claims and labels each supported / partly / unsupported / contradicted with a quoted evidence sentence                                                    | grounding score, claim table, evidence linked to its source passage                                                                                                                                                                                |
| **Study mode**                | writes a quiz (multiple choice, true/false, short answer) with a source per question; grades free-text answers as a tutor with feedback                                         | one-question-at-a-time session, rule-based grading for closed questions, score tracking, Excel / Word session report                                                                                                                               |
| **Ask your data**             | turns a question about a CSV/XLSX into a _query plan_ (computed columns, filters, group-by, aggregates, sort, limit, chart)                                                     | the plan is executed deterministically in Python on the real table, so every number is exact; plan shown for transparency; bar/line chart; Excel export                                                                                            |
| **Privacy Guard**             | finds context-dependent personal data (names, addresses, organisations, IDs)                                                                                                    | regex layer for e-mail / phone / IBAN / card (Luhn) / Finnish HETU / IP; review table (keep, recategorise, custom replacement); consistent placeholders like `[PERSON-1]`; redacted copy exported and/or added to the library to chat with safely  |
| **Translate & export**        | translates whole documents preserving headings, lists and tables                                                                                                                | one-click download as Word / PDF / LaTeX / Markdown                                                                                                                                                                                                |
| **Finnish answers**           | answers in Finnish (or English) whatever the language of the documents; translates any finished answer with one click (_Suomeksi_ / _In English_)                              | citation markers are replaced by placeholders before translation and restored afterwards, so a translated answer keeps working, clickable citations; markers the model drops are re-attached and reported                                        |
| **Evaluation**                | answers the benchmark questions through the normal pipeline                                                                                                                     | bilingual benchmark with deterministic scoring, model-free retrieval check, live runs, side-by-side model comparison and a review of every wrong answer                                                                                           |
| **Quick actions**             | summarize, quiz, study notes, compare, action items, explain simply                                                                                                             | insert ready-made prompts                                                                                                                                                                                                                          |
| **Figures (vision)**          | a local vision-language model reads charts, diagrams and photos inside PDF/PPTX/DOCX and returns a structured description with the values it can read off a chart               | bitmaps _and_ vector charts are collected (pages with vector drawing are rendered), descriptions are reviewed, then merged into the document text so chat, citations, quiz and export can use them; single figures can also be questioned directly |
| **Agent (router + verifier)** | a router agent classifies the request and picks one tool; the verifier agent fact-checks the result and, when grounding is weak, the answer is rewritten once from the findings | tools are the app's own services, so the model chooses the route but never performs the action; the full trace (decision, confidence, tool, grounding score, refinement) is shown                                                                  |

## Supported formats

| Input                                 | Parser                                         | Output                         | Writer        |
| ------------------------------------- | ---------------------------------------------- | ------------------------------ | ------------- |
| `.txt`, `.md`, pasted text            | built-in (UTF-8 with fallback detection)       | `.docx`                        | python-docx   |
| `.html`, `.htm`, web URL (http/https) | BeautifulSoup + markdownify                    | `.xlsx`                        | openpyxl      |
| `.csv`, `.tsv`                        | csv (delimiter sniffing)                       | `.pptx`                        | python-pptx   |
| `.docx`                               | python-docx                                    | `.pdf` (from an answer)        | PyMuPDF Story |
| `.pdf`                                | PyMuPDF / PyMuPDF4LLM (optional OCR hook)      | `.tex` (LaTeX, from an answer) | built-in      |
|                                       |                                                | `.csv`, `.md`, `.txt`          | built-in      |
| `.xlsx`, `.xlsm`                      | openpyxl (read-only, cached values, no macros) |                                |               |
| `.pptx`                               | python-pptx                                    |                                |               |

## Evaluation report

This section reports how accurately the application answers questions about documents, in
English and in Finnish. Two models were run on the full benchmark - the old default
Qwen2.5-3B and the recommended Qwen3.5-4B - and Gemma-4-E4B on a matched sample, for the
reason explained in [Gemma-4-E4B](#gemma-4-e4b). The benchmark, its scoring and every result
file are part of the repository, so each number below can be reproduced with one command
(see [Reproducing the results](#reproducing-the-results)).

### Summary

| Full context, all 118 questions per model          | Qwen2.5-3B (old default) | **Qwen3.5-4B (new default)** |
| --------------------------------------------------- | -----------------------: | ---------------------------: |
| Overall score                                       |                     65 % |                     **97 %** |
| Small details found exactly                         |                     83 % |                     **97 %** |
| Similar items: recall (found them all?)             |                     51 % |                    **100 %** |
| Similar items: precision                            |                     85 % |                     **88 %** |
| Unanswerable questions answered "not in documents" |                     25 % |                     **92 %** |
| Answers with a number found in no document          |                      3 % |                      **0 %** |
| Citation points to the section holding the answer   |                     42 % |                     **97 %** |
| English questions, English documents                |                     80 % |                    **100 %** |
| Finnish questions, Finnish documents                |                     58 % |                     **95 %** |
| Average time per question (CPU only)                |                    8.3 s |                       18.5 s |

Main findings:

1. **Replacing Qwen2.5-3B was necessary.** It answered English questions reasonably well (80 %)
   but Finnish ones poorly (58 %). Above all, it **invented an answer to every unanswerable
   Finnish question** (0 % correct refusals): it named the CEO as the finance director, gave the
   wind-farm contract number for the battery project, and reported 2024 figures as 2023 figures.
2. **Qwen3.5-4B closes the language gap** (100 % English, 95 % Finnish), finds every item in the
   "find all similar items" questions, cites the right section 97 % of the time and refuses
   correctly in 92 % of unanswerable cases. It is the new default.
3. **Gemma-4-E4B is accurate but impractical on this hardware.** On a matched sample it was as
   accurate as Qwen3.5-4B on facts, but with thinking switched off it writes its reasoning into
   the answer itself, at about 3 tokens per second: roughly two minutes per answer, and some
   answers ran out of length before reaching the conclusion.
4. **The price is speed.** On this CPU-only laptop Qwen3.5-4B reads a prompt about four times
   more slowly than Qwen2.5-3B. Asking several questions about the same documents stays fast,
   because llama-server reuses the cached prompt; the first question about a new selection is
   the slow one.
5. **The benchmark changed the application.** It exposed weak Finnish retrieval and a prompt
   flaw; both were fixed and re-measured (see [What the benchmark changed](#what-the-benchmark-changed)).

### Gemma-4-E4B

The professor named Qwen3.5-4B and Gemma-4-E4B as suitable models, so both were tested.

**Behaviour.** Gemma-4-E4B ignores llama.cpp's "thinking off" switch (`--reasoning-budget 0`) in
a specific way: it does not think silently, it **writes its reasoning into the answer** - _"The user
is asking for ... Source 1 ... Source 2 does not mention ..."_ - and only then the answer. An extra
system-prompt rule ("answer directly, do not describe your search") removed this on a short
prompt but not with the documents in context. Without the switch it thinks in a separate channel,
which is cleaner but just as slow.

**Speed.** Gemma reads prompts quickly (about 60 tokens/s, three times faster than Qwen3.5-4B on
this CPU) but writes slowly (about 3 tokens/s against 7) and writes about 300 tokens per answer.
A full run would have taken about five hours, against one for Qwen3.5-4B, so Gemma was measured on
a **matched sample**: the same four questions (a detail, a second detail, a similar-items list and
an unanswerable question) in English and in Finnish, compared with Qwen3.5-4B's answers to exactly
the same eight cases.

| Same 8 cases, full context                  | Qwen3.5-4B | Gemma-4-E4B |
| ------------------------------------------- | ---------: | ----------: |
| Overall score                               |      100 % |        94 % |
| Small details                               |      100 % |       100 % |
| Similar items: recall                       |      100 % |        75 % |
| Unanswerable refused correctly              |      100 % |       100 % |
| Citation points to the answer               |      100 % |        67 % |
| Seconds per question (incl. first, uncached) |         74 |         143 |

Two of Gemma's eight answers ended with _"**Plan:** state the LTIF for 2025 ..."_ - the
512-token limit was used up by the narration before the final answer was written; they count as
correct only because the number appears inside the narration. A user would see the whole narration
in the chat.

**Decision:** Qwen3.5-4B is the default. Gemma-4-E4B remains supported (the launcher accepts any
GGUF model) and is a reasonable choice on a machine with a GPU, where its writing speed matters
less.

### What was tested and why

The professor's feedback asked for three things, and each maps to a question type:

| Requirement                                      | Question type          | Count | Example (English / Finnish)                                                                                                         |
| ------------------------------------------------ | ---------------------- | ----: | ----------------------------------------------------------------------------------------------------------------------------------- |
| Retrieval of similar items - did it find them all? | Similar items (lists)  |     8 | _Which projects are delayed or behind schedule?_ / _Mitkä hankkeet ovat viivästyneet tai aikataulusta jäljessä?_                     |
| Retrieval of very small details                  | Small details          |    26 | _What was the lost-time injury frequency (LTIF) in 2025?_ / _Mikä oli tapaturmataajuus (LTIF) vuonna 2025?_                          |
| Did it hallucinate?                              | Not in the documents   |     8 | _Who is the company's chief financial officer?_ / _Kuka on yhtiön talousjohtaja?_                                                   |
| At least English and Finnish                     | Every question in both |     - | 17 questions are also asked **across** languages (English question on Finnish documents and the reverse)                          |

Every question is asked in English on the English documents and in Finnish on the Finnish
documents (84 cases), plus the 17 cross-lingual questions in both directions (34 cases): **118
cases per model and context strategy**.

### Test documents

The corpus describes a **fictional** energy company, _Kuusiranta Energy Ltd / Kuusiranta Energia
Oy_. Because the company does not exist, a model cannot answer from what it learned in training:
every correct answer must come from the documents, and every invented one is a hallucination.

| Document                                  | Format | English file                           | Finnish file                            | Sections                |
| ----------------------------------------- | ------ | -------------------------------------- | --------------------------------------- | ----------------------- |
| Annual report 2025                        | PDF    | `annual_report_2025.pdf`               | `vuosikertomus_2025.pdf`                | 9 pages                 |
| Steering group minutes 4/2025             | Word   | `steering_group_minutes_4_2025.docx`   | `ohjausryhman_poytakirja_4_2025.docx`   | 6 headings + table      |
| Strategy 2026-2030                        | PowerPoint | `strategy_2026_2030.pptx`          | `strategia_2026_2030.pptx`              | 7 slides                |
| Site and incident register                | Excel  | `site_register.xlsx`                   | `kohderekisteri.xlsx`                   | 2 sheets                |

The two language versions contain exactly the same facts (about 13,000 characters each), written
the way a native document would write them: Finnish uses decimal commas (`184,6`), space-grouped
thousands (`1 148`), `day.month.year` dates and its own case endings (_Pohjankankaan
tuulipuistossa_). The facts were planted deliberately:

- **similar items are scattered** across documents and formats - the four delayed projects are
  spread over the report, the minutes and the slides; the four wind farms over the spreadsheet and
  the report;
- **small details sit next to a distractor** - the 2025 revenue next to the 2024 revenue, the
  company's selling price on the page after the Nordic system price, the 2026 hedging share in
  the same sentence as the 2027 share;
- **unanswerable questions are plausible** - revenue for 2023 when only 2024 and 2025 are
  reported, a contract number that exists for another project, the number of turbines of a wind
  farm whose capacity (but not turbine count) is given, a "wind farm" that is really a solar park.

The text is in [`benchmark/corpus_text.py`](benchmark/corpus_text.py), the questions and expected
answers in [`benchmark/questions.json`](benchmark/questions.json).

### How answers are scored

Scoring is **deterministic**: no second language model judges the answers. Every rule is a plain
text check, so the same answer always gets the same score and every verdict can be audited.

| Metric                         | Rule                                                                                                                                                                                                                                  |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Small detail correct           | the expected value appears in the answer. Numbers match in English and Finnish notation (`184.6` = `184,6`; `1,148` = `1 148`); names match by stem (`Koskinen` / `Koskisen`); dates in every common English and Finnish form |
| Similar items: recall          | share of the expected items the answer names                                                                                                                                                                                         |
| Similar items: precision       | for site and supplier lists, share of named items that are correct (any other site or supplier mentioned counts against it)                                                                                                          |
| Unanswerable: correct          | the answer says the documents do not contain it (about 20 English and Finnish phrasings are recognised), or corrects a false premise                                                                                                   |
| Number found in no document    | the answer contains a number that occurs in no document and not in the question (citations, list numbering and counts up to 12 are ignored)                                                                                         |
| Citation correct               | at least one citation resolves to a section that really contains the answer                                                                                                                                                          |
| Overall                        | mean over all cases: details and unanswerable count 1 or 0, a list counts its recall                                                                                                                                                 |

A **self-check** (`benchmark/run.py check`, also a unit test) verifies that every expected answer
really is present, at the stated location, in both language versions.

### Procedure

- Hardware: laptop with an AMD Ryzen 5 5500U (6 cores), 16 GB RAM, **no GPU offload**.
- Runtime: llama.cpp `llama-server` (bundled with LM Studio), `-c 16384 --jinja -t 6 -ngl 0`,
  **thinking disabled** (`--reasoning-budget 0`). All models as **Q4_K_M** GGUF.
- Temperature 0, at most 512 answer tokens, the application's normal system prompt.
- All four documents of one language are selected for every question, always in the same order,
  so the prompt is identical between questions and llama-server reuses its prompt cache.
- Questions go through the **real pipeline**: parsers → context strategy → token budget check →
  llama-server → citation resolution. Nothing is shortcut for the benchmark.
- Models compared with **full context** (all documents sent). Retrieval was measured separately,
  with and without a model (below).

### Results by language

| Overall score (full context)             | Qwen2.5-3B | Qwen3.5-4B |
| ---------------------------------------- | ---------: | ---------: |
| English question → English documents     |       80 % |      100 % |
| Finnish question → Finnish documents     |       58 % |       95 % |
| English question → Finnish documents     |       60 % |      100 % |
| Finnish question → English documents     |       52 % |       88 % |

| Unanswerable questions refused correctly | Qwen2.5-3B | Qwen3.5-4B |
| ---------------------------------------- | ---------: | ---------: |
| English                                  |       38 % |      100 % |
| Finnish                                  |        0 % |       88 % |

Finnish remains the harder language for every model, and a Finnish question about English
documents is the hardest combination: the model has to translate while it searches.

### Retrieval: does the right passage reach the model?

Retrieval sends only the best-matching passages instead of whole documents. Measured **without a
model** (`benchmark/run.py retrieval`, a few seconds): for every answerable question, is the
passage that holds the answer among those retrieved? Passages are about 180 words; the
benchmark retrieves 4 best matches plus neighbours within 4,000 characters (about 30 % of the
corpus), to simulate a collection that does not fit into the context window.

| Retrieval      | Question → documents | Recall@1 | Recall@3 | Recall@5 | Answer reached the model | Share of corpus sent |
| -------------- | -------------------- | -------: | -------: | -------: | -----------------------: | -------------------: |
| plain BM25     | EN → EN              |     65 % |     84 % |     90 % |                     96 % |                 31 % |
| plain BM25     | FI → FI              |     66 % |     75 % |     90 % |                     93 % |                 29 % |
| language-aware | EN → EN              |     67 % | **90 %** | **98 %** |                 **98 %** |                 28 % |
| language-aware | FI → FI              |     73 % | **88 %** | **100 %** |                **96 %** |                 29 % |
| language-aware | EN → FI              |     23 % |     38 % |     54 % |                     69 % |                 35 % |
| language-aware | FI → EN              |      8 % |     27 % |     27 % |                     92 %\* |                 73 % |

\* mostly because nothing matched and the application fell back to sending everything.

With a model (Qwen2.5-3B, the only model run with both strategies), retrieval scored **91 %**
overall on English (full context: 80 %) and **55 %** on Finnish (full context: 58 %). Fewer,
better-targeted passages helped the small model in English; in Finnish, the model's own language
weakness dominated.

**Conclusion:** retrieval works well within one language once it is language-aware. Across
languages, keyword search cannot match an English question to Finnish text; the application
therefore defaults to full context for small selections (`auto`), and the limitation is documented.

### What the benchmark changed

| Problem found by the benchmark                                                                                                                              | Change                                                                                                    | Measured effect                                                                             |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| Finnish case endings broke keyword search: _tuulipuistoon_ did not match _tuulipuistossa_                                                                   | Snowball stemming per document language (English, Finnish)                                                | Finnish questions now match inflected forms (unit-tested)                                   |
| Finnish compounds and consonant gradation defeat the stemmer: _käyttöönottopäivä_ vs _käyttöönotto_, _Pohjankangas_ vs _Pohjankankaan_                      | Long Finnish words also index their first 6 letters                                                      | Finnish recall@5 90 % → **100 %**                                                           |
| Slide titles and Word headings were not searchable, so "key risks" did not find the slide titled _Key risks_                                                 | Section titles indexed with each passage                                                                  | English recall@3 84 % → **90 %**; Finnish recall@3 75 % → **88 %** (with the two above)     |
| Small models copied the citation **example sentence** from the system prompt into answers (_"The F1 score is the harmonic mean ..."_)                       | Citation format shown with placeholders; leakage is now a benchmark metric                               | Copied prompt text: **0 %** of answers for the new models                                   |
| Qwen2.5-3B: 0 % correct refusals in Finnish, 58 % overall in Finnish                                                                                        | Default model changed to Qwen3.5-4B                                                                       | Finnish 58 % → **95 %**; Finnish refusals 0 % → **88 %**                                    |

The retrieval settings were chosen on this benchmark, so the retrieval gains are probably
somewhat optimistic for other documents; the model comparison does not depend on them (it uses
full context).

### Typical errors

The remaining errors of Qwen3.5-4B are few and specific (all answers are in the result file and
in the Evaluation tab):

- **Wrong small number in Finnish:** _"Ristinevan tuulipuistoon on valmiina kahdeksan voimalan
  perustuksesta"_ - eight instead of six foundations.
- **Unit confused with count:** asked how many turbines Tervaharju will have, it answered _"78
  voimalaa"_ - 78 is the capacity in MW.
- **Role confusion across languages:** asked in Finnish about the English documents, it named
  the CEO as the finance director.
- **Precision losses are partly a scoring artefact:** a list answer that says _"Kivijärvi is a
  solar park, not a wind farm"_ still counts Kivijärvi as listed.

### Limitations of this evaluation

- **Small corpus:** 4 documents and 42 questions per language. Differences of a few percentage
  points between models are within noise; the large gaps (Finnish 58 % → 95 %, refusals 25 % →
  92 %) are not.
- **One run per model** at temperature 0. Greedy decoding is close to deterministic, but no
  repeated runs were made.
- **Text matching has blind spots.** An answer that is right but phrased unusually can be scored
  wrong, and the "number in no document" metric cannot see a _real_ number used in the wrong place
  (2024 revenue reported as 2023); that case is caught by the unanswerable questions instead.
- **The Finnish text was written for the benchmark**;
  it is not a real Finnish company report.
- **Retrieval settings were tuned on the same benchmark** (see above).
- **Gemma-4-E4B was measured on 8 cases only**, so its numbers indicate behaviour, not a
  reliable score.
- **Speed numbers are from one CPU-only laptop**; any GPU changes them completely.

### Reproducing the results

```powershell
# from the repository root, with the backend virtual environment
backend\.venv\Scripts\python benchmark\run.py check        # validate the suite (no model)
backend\.venv\Scripts\python benchmark\run.py retrieval    # retrieval table (no model, seconds)

# start llama-server with the model to test, then:
backend\.venv\Scripts\python benchmark\run.py run --strategies full          # 118 cases
backend\.venv\Scripts\python benchmark\run.py run --quick                    # 2 per category, a few minutes
backend\.venv\Scripts\python benchmark\run.py run --resume <run-id>          # continue an interrupted run
backend\.venv\Scripts\python benchmark\run.py report       # Markdown tables of all saved runs
```

The same runs can be started, followed and compared in the **Evaluation** tab. Results are saved
after every question in `benchmark/results/<timestamp>_<model>.json`.

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
   │    ├─ context_strategy.py full context, retrieval (BM25) or automatic
   │    ├─ context_budget.py   render prompt → /tokenize → compare with active n_ctx
   │    └─ prompts.py          system prompt, <source> wrapping, prompt-injection guidance
   ├─ services/generation.py   prompt → schema-constrained JSON → Pydantic → writer → data/exports
   ├─ services/writers         docx / xlsx / pptx / csv / txt / md / pdf / tex
   ├─ services/retrieval       locator-preserving chunks, BM25 with English/Finnish stemming
   ├─ services/features        citations, verify, study, data_query, privacy_guard, translate
   ├─ services/evaluation      benchmark suite, deterministic scoring, runner, report
   ├─ services/vision          figure extraction (PyMuPDF/python-pptx/python-docx) → VLM description → merge
   ├─ services/agents          router agent + orchestrator (route → tool → verify → refine)
   └─ services/privacy         LOCAL ONLY policy (endpoint must be localhost), status report
   │
   ▼  localhost only
 llama-server (llama.cpp, :8080)   /health  /props  /tokenize  /apply-template  /v1/chat/completions
```

Key design decisions

- **Two comparable context strategies.** `FullContextStrategy` sends every selected document;
  `RetrievalContextStrategy` ranks locator-preserving passages with BM25 and sends only the best
  ones. Retrieval is deliberately **lexical and dependency-free** - no vector database, no
  embedding model to download, no extra process - which keeps the privacy story intact and makes
  the ranking deterministic, so the same question always retrieves the same passages. Ranking is
  language-aware: Snowball stemming per document language, prefix terms for long Finnish words
  (compounds and consonant gradation defeat the stemmer) and section titles indexed with each
  passage; the benchmark measured each of these choices. `auto` picks
  between them by size. Measured on a 28,000-character paper: retrieval sends **53% fewer tokens**
  and answers in 14 s instead of 32 s, with the same answer and the same resolved citation.
  `POST /api/context/compare` reports both costs side by side and recommends one - including
  saying plainly when a selection is too small for retrieval to be worth its overhead.
- **Accurate token counting**: prompts are rendered with `/apply-template` and counted with
  `/tokenize`; `characters / 4` estimates are not used for decisions.
- **Context budget** = active `n_ctx` (from `/props`) − reserved output tokens (default 4096) −
  safety reserve (default 1024). If the prompt does not fit, the user gets the exact numbers and
  suggestions (select fewer documents, start llama-server with `-c` larger, use a larger-context model).
- **Structured output**: file generation never parses free-form text. The JSON schema of the
  Pydantic spec (`DocxSpec`, `XlsxSpec`, `PptxSpec`) is passed as `response_format` to llama-server.
- **Source boundaries**: each document is wrapped in `<source id="n" name="...">…</source>` and the
  system prompt tells the model that source content is data, not instructions.
- **Agents without an agent framework**: the router/verifier loop is a ~250-line local state machine
  over the existing services rather than LangGraph/CrewAI. Every step is an explicit function call,
  the trace is inspectable, and no extra dependency tree (or cloud-oriented default) is pulled in.
- **Vision as text**: figure descriptions are written back into the document's Markdown, so a single
  pipeline (context budget, citations, verification, export) covers text and images alike.

## Prerequisites

- **Python 3.11 or newer** (developed and tested on 3.14)
- **Node.js 20 or newer** (tested on 24) with npm
- **llama.cpp `llama-server`** – binaries from <https://github.com/ggml-org/llama.cpp/releases>
  (or the copy bundled with LM Studio, see `scripts/example_llama_server_command.md`)
- A **GGUF instruct model**. Recommended: **Qwen3.5-4B** (`Qwen3.5-4B-Q4_K_M.gguf`, ~2.7 GB);
  alternative: **Gemma-4-E4B-it** (Q4_K_M). Start either with thinking disabled
  (`--reasoning-budget 0`, or the "Disable thinking" box in the Model launcher). The older
  Qwen2.5-3B-Instruct still runs but is no longer recommended: the
  [evaluation report](#evaluation-report) shows its Finnish answers are much weaker.
- **Optional, for the Figures tab:** the model's projector file. Qwen3.5-4B ships one
  (`mmproj-Qwen3.5-4B-BF16.gguf`), so the same small model can also read charts and images when
  started with `--mmproj <projector>.gguf`. The Model launcher has a field for it. Without it every
  other feature works and the Figures tab explains what is missing.
- Windows, Linux and macOS should all work; the scripts are provided for PowerShell and bash.

## Setup and running

Three processes run side by side: llama-server, the backend and the frontend.

### 1. Start llama-server (two options)

**Option A - from the app (recommended).** Start the backend and frontend (steps 2 and 3), open
the UI and use the **Model launcher** panel on the right. Enter the path to _your_
`llama-server` executable and _your_ `.gguf` model, optionally context size / threads / GPU
layers, and click **Start llama-server**. The paths are stored only on your machine in
`data/llm_settings.json` (git-ignored), so nothing machine-specific ever lands in the repository.
The panel also shows the server log and lets you stop the server again.

**Only one llama-server can hold the endpoint at a time.** If a server is already running (for
example one you started in a terminal), the Model launcher says so and names the model it has
loaded; stop that one first, then start the model you want from the app.

**Option B - manually.** Start it yourself in a terminal; the app detects it automatically:

```powershell
llama-server.exe -m "C:\path\to\your-model.gguf" -c 16384 --host 127.0.0.1 --port 8080 --jinja
```

or `scripts\start_llama_server_example.ps1` / `scripts/start_llama_server_example.sh`, which
prompt for the two paths (or read `LLAMA_SERVER_EXE` and `LLAMA_MODEL_PATH`).

- `-c` is the **active context**; the application reads it and uses it as the budget.
- `--jinja` uses the model's own chat template (recommended for JSON output).
- Add `-ngl 99` for GPU offload with CUDA/Vulkan/Metal builds.
- More examples: `scripts/example_llama_server_command.md`.

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
   The selector next to _Send_ sets the answer language: _same as question_, _English_ or
   _Vastaa suomeksi_ (Finnish), independent of the documents' language.
3. **Translate or download an answer** – under every answer: _Translate: Suomeksi / In English_
   adds a translated copy with working citations; _Download as_ Word (.docx), PDF, LaTeX (.tex),
   Markdown (.md) or Text (.txt). The conversion happens locally from the answer's Markdown.
4. **Output mode** – switch the selector from _Answer in chat_ to _Generate Word / Excel /
   PowerPoint / CSV_ and describe what you want, e.g.
   _"Create 10 quiz questions based only on the provided teaching materials. Include an answer key."_
   The file appears in **Exports (right)** with a Download button.
5. **Model (right)** – llama-server status, model name, active and trained context size, reserved
   output tokens and the live context usage bar.
6. **Model launcher (right)** – enter your own llama-server / model paths and start or stop the
   server from the UI.
7. **Agent tab** – type what you want in plain language. The router agent picks the tool
   (answer, summarise, generate a file, query a table, privacy scan, figures, quiz, translate),
   the tool runs, and the verifier agent fact-checks the result; if grounding is below 70% the
   answer is rewritten once from the findings. Every step is listed with its confidence.
8. **Figures tab** – “Find figures” collects embedded images and renders pages that contain vector
   charts; “Describe” sends each figure to the local vision model and merges the result into the
   document. Click a figure to enlarge it and ask a question about it directly.
9. **Evaluation tab** – the accuracy benchmark: run the model-free retrieval check, run the
   question set against the loaded model (quick or full, chosen languages and strategies) with live
   progress, compare runs side by side and read every answer that was scored wrong, with the reason.
10. **Privacy (left, bottom)** – LOCAL ONLY badge, endpoint, model, "Network needed: No (URL import only)".

## Privacy design

Default mode is **LOCAL ONLY**:

- The LLM endpoint must be a loopback address; a non-localhost `LDW_LLM_BASE_URL` blocks all AI
  requests (HTTP 403) and the UI shows a red warning instead of a green badge.
- There are no cloud AI APIs, API keys, analytics or telemetry anywhere in the code.
- Parsing, tokenization, inference and file generation all happen on this machine. Uploaded files,
  converted Markdown and generated files live in `data/` and can be deleted from the UI.
- Logs contain file names, types, sizes, timings, token counts and errors – never document text.
- **Web URL import is the only network operation.** It runs only after an explicit click, shows a
  clear notice, accepts only `http(s)://`, rejects private/loopback/link-local targets and malformed
  URLs, enforces a timeout and a size limit, follows at most five (re-validated) redirects and never
  crawls linked pages. The fetched page is then parsed locally like any HTML file.

Input safety: upload size limit (50 MB default), extension allow-list, sanitized file names,
server-generated IDs, no user-controlled paths, Office files opened read-only without macro or
formula execution, JavaScript in HTML never executed.

## Configuration

Environment variables (or `backend/.env`, see `backend/.env.example`), all prefixed `LDW_`:

| Variable                                              | Default                 | Meaning                                                   |
| ----------------------------------------------------- | ----------------------- | --------------------------------------------------------- |
| `LDW_LLM_BASE_URL`                                    | `http://127.0.0.1:8080` | llama-server endpoint                                     |
| `LDW_LOCAL_ONLY`                                      | `true`                  | require a localhost endpoint                              |
| `LDW_MAX_OUTPUT_TOKENS`                               | `1024`                  | tokens reserved for the answer                            |
| `LDW_CONTEXT_STRATEGY`                                | `auto`                  | `full`, `retrieval` or `auto`                             |
| `LDW_RETRIEVAL_TOP_K`                                 | `8`                     | passages ranked per question                              |
| `LDW_RETRIEVAL_MAX_CHARACTERS`                        | `12000`                 | size budget for retrieved passages                        |
| `LDW_RETRIEVAL_AUTO_THRESHOLD_CHARACTERS`             | `12000`                 | below this, `auto` sends everything                       |
| `LDW_CONTEXT_SAFETY_RESERVE`                          | `1024`                  | extra safety margin                                       |
| `LDW_FALLBACK_CONTEXT_SIZE`                           | `8192`                  | used only if `/props` reports no `n_ctx`                  |
| `LDW_MAX_UPLOAD_BYTES`                                | `52428800`              | upload limit                                              |
| `LDW_URL_FETCH_TIMEOUT_SECONDS` / `LDW_URL_MAX_BYTES` | `15` / `5 MB`           | URL import limits                                         |
| `LDW_DATA_DIR`                                        | `<repo>/data`           | local storage directory                                   |
| `LDW_PDF_OCR`                                         | `false`                 | try PyMuPDF OCR on image-only PDF pages (needs Tesseract) |
| `LDW_RETRIEVAL_STEMMING`                              | `true`                  | English/Finnish stemming in retrieval                     |
| `LDW_RETRIEVAL_PREFIX_CHARS`                          | `6`                     | prefix term for long Finnish words (`0` = off)            |
| `LDW_RETRIEVAL_INDEX_TITLES`                          | `true`                  | index slide titles and headings with each passage         |
| `LDW_BENCHMARK_DIR`                                   | `<repo>/benchmark`      | benchmark corpus, questions and results                   |

## Tests

```powershell
cd backend
.venv\Scripts\python -m pytest -q
```

- Parser tests: every fixture (TXT, MD, HTML, CSV, DOCX, PDF, XLSX, PPTX) contains the phrase
  `BLUE ELEPHANT 1947` at a known place (PDF page 3, PPTX slide 2, XLSX sheet "Results", …) and the
  tests assert it appears in the normalized Markdown at that locator.
- Multilingual smoke test: English, Finnish, Chinese, Arabic and Russian text survives
  input → parsing → Markdown → prompt. (Answer quality is measured by the benchmark, not here.)
- Retrieval tests: Finnish case endings match with stemming and miss without it; language
  detection; section titles are searchable.
- Benchmark tests: the suite self-check (every expected answer is really in both language
  versions, at the stated location), number parsing in English and Finnish formats, refusal
  detection in both languages, list recall/precision, citation scoring, and the model-free
  retrieval check (language-aware retrieval must beat plain BM25 on Finnish).
- Translation tests: citation markers survive translation, and dropped markers are re-attached.
- Writer round-trips: generated DOCX/XLSX/PPTX files are re-parsed and checked.
- API tests: upload/list/preview/delete, unsupported types, corrupt files, SSRF rejections,
  uniform error shape, LOCAL ONLY enforcement, export download.
- Tests marked `requires_llama` (status, token counting, oversized-context refusal, answering from a
  document) run automatically when llama-server is reachable and are skipped otherwise.

Fixtures are generated by `tests/make_fixtures.py` on first run. Frontend: `npm run build`
type-checks, `npm run lint` lints.

## API overview

| Method       | Path                                                             | Purpose                                                      |
| ------------ | ---------------------------------------------------------------- | ------------------------------------------------------------ |
| GET          | `/api/health`                                                    | backend health                                               |
| GET          | `/api/llm/status`                                                | llama-server reachability, model, active context, budget     |
| GET          | `/api/privacy`                                                   | privacy status                                               |
| POST         | `/api/agent/run`                                                 | agent run (SSE: one event per step, then result)             |
| GET          | `/api/vision/status`                                             | is a vision projector loaded?                                |
| POST         | `/api/vision/{id}/extract`, `/describe`                          | find figures, describe them locally                          |
| GET/PUT/POST | `/api/vision/image/...`, `/image/{id}`, `/image/{id}/ask`        | serve, edit or question a figure                             |
| GET/PUT/POST | `/api/llm/launcher`, `/settings`, `/validate`, `/start`, `/stop` | start/stop llama-server with user-provided paths             |
| GET/POST     | `/api/documents`, `/upload`, `/text`, `/url`                     | list / import documents                                      |
| GET          | `/api/documents/{id}?preview_chars=N`                            | normalized content                                           |
| DELETE       | `/api/documents/{id}`, `/api/documents`                          | delete one / all                                             |
| POST         | `/api/context/check`                                             | token count vs. active context, and which strategy was used  |
| GET          | `/api/context/strategies`                                        | the available context strategies                             |
| POST         | `/api/context/compare`                                           | full vs retrieval token cost for the same question           |
| POST         | `/api/chat`                                                      | chat (SSE streaming by default, `stream:false` for JSON)     |
| GET          | `/api/chat/quick-actions`                                        | quick-action prompts                                         |
| POST         | `/api/generate/{docx\|xlsx\|pptx\|csv}`                          | structured generation → file                                 |
| POST         | `/api/exports/save-text`                                         | save an answer as `.docx` / `.pdf` / `.tex` / `.md` / `.txt` |
| GET          | `/api/documents/{id}/sections`                                   | sections with locators (citation viewer)                     |
| POST         | `/api/verify`                                                    | fact-check an answer against selected documents              |
| POST         | `/api/study/quiz`, `/grade`, `/report`                           | study mode                                                   |
| GET/POST     | `/api/data/{id}/info`, `/api/data/query`, `/api/data/export`     | ask your data                                                |
| POST         | `/api/privacy/scan`, `/api/privacy/redact`                       | privacy guard                                                |
| GET/DELETE   | `/api/exports`, `/api/exports/{id}`                              | list / download / delete generated files                     |
| POST         | `/api/chat/translate`                                            | translate an answer, citations protected and re-resolved     |
| GET          | `/api/eval/suite`                                                | benchmark questions, corpus summary, self-check problems     |
| GET/POST     | `/api/eval/retrieval`                                            | model-free retrieval check (last result / run now)           |
| POST         | `/api/eval/run`, `/api/eval/stop`                                | benchmark run (SSE: one event per question) / stop it        |
| GET/DELETE   | `/api/eval/results`, `/api/eval/results/{id}`                    | saved benchmark runs                                         |

Errors always have the shape `{"error": "...", "suggestions": [...], "context": {...}}` with plain
language messages (`llama-server is not running.`, `The selected documents require approximately
78,000 tokens but the active model context is 65,536 tokens.`, `This file type is not supported.`).

## Known limitations

- **Retrieval is lexical (BM25), not semantic.** A question phrased entirely in different words
  from the source ("how do I stop my model memorising the training data?" for a passage about
  overfitting) may retrieve nothing useful. The strategy reports how many passages matched, and
  falls back to full context when the question has no searchable terms or nothing scores, but it
  will not find a paraphrase the way an embedding model would. Adding embeddings later would not
  change the interface - only the ranking inside `RetrievalContextStrategy`. For the same reason
  **cross-lingual retrieval is weak**: an English question shares almost no words with a Finnish
  document. Use full context (or ask in the documents' language) when the languages differ; the
  [evaluation report](#evaluation-report) quantifies this.
- **Retrieval has a fixed overhead** (its instructions plus a document outline), so on small
  selections it costs more tokens than it saves. That is why `auto` is the default and why the
  compare endpoint recommends full context for small inputs.
- **Citations and fact-checks are only as good as the model.** Small models sometimes cite the
  wrong section; the app flags citations that do not match any section, and the fact-check is a
  second model opinion, not ground truth.
- **Model quality depends on the local model.** Small CPU-only models are slow (tens of seconds to
  minutes per request on a laptop) and may make factual or arithmetic mistakes. Reasoning models
  emit `<think>` blocks, which the UI shows collapsed.
- **Office formatting is basic.** Generated files use simple styles (headings, lists, tables,
  bold header rows, frozen headers, title/content slide layouts). Complex visual formatting of
  imported files is not preserved – the goal is semantic content extraction.
- **Figure understanding needs a vision model.** Without `--mmproj` the Figures tab reports that the
  loaded model cannot see images and the rest of the app works unchanged. Descriptions are the
  model's reading of the image: on a small local VLM they can misread crowded or low-resolution
  charts, which is why every description is reviewable and can be edited or excluded.
- **Native PowerPoint charts** (chart objects rather than pictures) cannot be rasterised locally and
  are skipped with a log entry; the same chart pasted as an image is read normally.
- **OCR for scanned PDFs** remains an optional hook (`LDW_PDF_OCR=true`, needs Tesseract); the
  vision pipeline covers figures, not full-page OCR of scans.
- **The agent router can mis-route** an ambiguous request. The chosen tool, its confidence and the
  restated task are always shown, and the individual tabs remain available for manual control.
- **Speed is dominated by the model, and on a CPU it is slow.** Measured on the same CPU-only
  laptop (Ryzen 5 5500U, 16 GB, no GPU offload), Q4_K_M models, thinking off:

  |                                   | Qwen2.5-3B | Qwen3.5-4B | Gemma-4-E4B |
  | --------------------------------- | ---------: | ---------: | ----------: |
  | Reading the prompt                |  ~85 tok/s |  ~22 tok/s |   ~60 tok/s |
  | Writing the answer                |  ~15 tok/s |   ~7 tok/s |    ~3 tok/s |
  | First question on ~4,000 tokens   |      ~50 s |     ~3 min |    ~2.5 min |
  | Follow-up question (cached prompt) |       ~4 s |     ~7 s   |      ~2 min |

  The first question about a new selection is the slow one: the model must read every document.
  Follow-up questions are fast because llama.cpp reuses the cached prompt (Gemma's follow-ups stay
  slow because its answers are long, see the [evaluation report](#gemma-4-e4b)). The application
  measures this from llama-server's own timings, shows the expected wait in the Context card
  before you send, and reports the phase ("Reading your documents" → "Writing the answer") with an
  elapsed timer. With a GPU (`-ngl 99`) all of these numbers drop by an order of magnitude.

- **A full agent run is several model calls** (router, tool, optional verifier and refinement), so
  it multiplies the above. "Verify" is therefore off by default in the Agent tab.
  Numeric JSON-schema bounds were deliberately removed from the structured outputs because
  llama.cpp's range grammars decode several times slower.
- **Vision needs a projector file.** Qwen3.5-4B has one (`mmproj-Qwen3.5-4B-BF16.gguf`), so the
  recommended model covers the Figures tab too; loading the projector adds memory and start-up time,
  so leave it out when you do not need figures.
- **Excel formulas are not evaluated**; cached values stored in the file are used and a note is
  attached when formulas are present. Very large sheets are capped at 20,000 rows per sheet with a
  visible note.
- **URL import needs the network** and cannot read JavaScript-rendered pages.
- **LaTeX export** is a `.tex` source file, not a compiled PDF; compile it with `pdflatex`
  (`xelatex`/`lualatex` for non-Latin scripts such as Chinese or Arabic).
- **Single user, no authentication, no cloud deployment** – by design for the prototype.
- **Accuracy is measured in English and Finnish only.** Other languages parse and display
  correctly (tested), but their answer quality has not been benchmarked.

## Project layout

```
backend/
  app/
    main.py, config.py
    models/document.py          DocumentContent, DocumentSection
    schemas/api.py, artifacts.py  API models; DocxSpec/XlsxSpec/PptxSpec for structured output
    routers/                    system, documents, chat, generate, features, vision, agent, evaluation
    services/
      parsers/                  txt/md, html + url_fetcher, csv, docx, pdf, xlsx, pptx
      writers/                  docx, xlsx, pptx, markdown_export (answer -> docx/pdf/tex), simple (csv/md/txt)
      llm/                      client, prompts, context_strategy, context_builder, context_budget, launcher
      retrieval/                chunker (locator-preserving passages) + BM25 with EN/FI stemming
      privacy/                  policy
      features/                 citations, verify, study, data_query, privacy_guard, structured, translate
      evaluation/               benchmark suite loader, scoring, runner, Markdown report
      document_store.py, export_store.py, generation.py
    utils/                      files (sanitizing, ids), logging
  tests/                        pytest suite + fixture generator
  requirements.txt
frontend/
  src/components/               DocumentPanel, ChatPanel (+SourceViewer), AgentPanel, FiguresPanel,
                                StudyPanel, DataPanel, PrivacyGuardPanel, EvaluationPanel, LauncherPanel,
                                StatusPanels (Privacy, Model, Exports)
  src/pages/Workspace.tsx       three-column layout
  src/services/api.ts           API client + SSE streaming
  src/types/api.ts
data/                           uploads/, converted/, exports/, images/, llm_settings.json (git-ignored)
benchmark/                      corpus/{en,fi}, questions.json, results/, corpus_text.py + make_corpus.py, run.py (CLI)
demo_data/                      demo teaching materials + generator
scripts/                        start_backend, start_frontend, example_llama_server_command
```
