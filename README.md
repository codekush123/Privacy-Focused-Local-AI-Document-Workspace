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

**Project documents:** [AGENTS.md](AGENTS.md) (rules and repository map for contributors and AI
coding agents) · [TESTING.md](TESTING.md) (how the project is verified) · [PLANS.md](PLANS.md)
(final-phase plan, status and decisions) · [FINAL-HOURS.md](FINAL-HOURS.md) (hours log, including
the share spent on testing).

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
| **Live answer check**        | nothing extra - the check runs without a second model call                                                                                                                      | every answer and translation is checked against the selected documents: numbers that appear in no source are highlighted in the answer, statements without a citation and citations that match no section are listed, and a badge shows the verdict - the same rules that score the benchmark |
| **Timeline**                  | lists the dated events of the selected documents (meetings, deadlines, decisions, incidents) as structured data with a citation each                                          | verifies that every date appears next to its event in the cited passage (same paragraph or table row, English and Finnish date forms) and finds the right passage when the citation is off; sorts the events, flags anything unverified, filters by document, opens the source passage, exports to Excel |
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
English and in Finnish. Two local models were run on the full benchmark - the old default
Qwen2.5-3B and the recommended Qwen3.5-4B - and Gemma-4-E4B on a matched sample, for the
reason explained in [Gemma-4-E4B](#gemma-4-e4b). Two cloud **frontier models**, Claude Opus 5
and GPT-6.1 Sol, answered the same questions as a reference point
([Frontier comparison](#frontier-comparison)). The questions come in two tiers: a
**standard** tier (42 per language) and a **hard** tier (22 per language) that was added when the
standard tier turned out to be too easy for the new model. The benchmark, its scoring and every
result file are part of the repository, so each number below can be reproduced with one command
(see [Reproducing the results](#reproducing-the-results)). How the project is tested overall is
described in [TESTING.md](TESTING.md); the plan and its decisions in [PLANS.md](PLANS.md).

### Summary

| Full context, standard tier (118 cases per model)  | Qwen2.5-3B (old, local) | **Qwen3.5-4B (new default, local)** | Claude Opus 5 (cloud) | GPT-6.1 Sol (cloud) |
| --------------------------------------------------- | ----------------------: | ----------------------------------: | --------------------: | ------------------: |
| Overall score                                       |                    65 % |                            **98 %** |                 100 % |               100 % |
| Small details found exactly                         |                    83 % |                            **99 %** |                 100 % |               100 % |
| Similar items: recall (found them all?)             |                    51 % |                           **100 %** |                 100 % |               100 % |
| Similar items: precision                            |                    85 % |                            **96 %** |                98 %² |               100 % |
| Unanswerable questions answered "not in documents" |                    25 % |                            **96 %** |                 100 % |               100 % |
| Answers with a number found in no document          |                     2 % |                             **0 %** |                   0 % |                 0 % |
| Citation points to the section holding the answer   |                    42 % |                            **97 %** |                 100 % |               100 % |
| English questions, English documents                |                    80 % |                           **100 %** |                 100 % |               100 % |
| Finnish questions, Finnish documents                |                   58 %³ |                           **100 %** |                 100 % |               100 % |
| **Hard tier** overall (68 cases)                    |                not run¹ |                            **89 %** |                 100 % |               100 % |
| Average time per question                           |    8.3 s (laptop CPU) |                  19.0 s (laptop CPU) |                 5.2 s |               6.5 s |
| **Time to complete the standard tier** (118 cases)⁴ |                  16 min |                              38 min |                10 min |              13 min |
| **Time to complete the hard tier** (68 cases)⁴      |                not run¹ |                              38 min |                 7 min |               7 min |
| Where the documents go                              |          stays on the laptop |                stays on the laptop |   sent to Anthropic |     sent to OpenAI |

¹ The Qwen2.5-3B model file had been removed from the test machine when the hard tier was added;
the standard tier is the like-for-like comparison.
² A scoring artefact, not a mistake: Claude added a section "for contrast - not delayed" naming
two projects, which the precision rule counts as listed.
³ Qwen2.5-3B answered the Finnish questions before the Finnish text was proofread (see
[Limitations](#limitations-of-this-evaluation)); all other models answered the proofread text.
⁴ Time to complete = the sum of the per-question answering times recorded in the result files. The
local models ran on the laptop CPU (no GPU); the frontier models' times include the network round
trip. The clock time of a run was longer where it was interrupted and resumed.

Main findings:

1. **Replacing Qwen2.5-3B was necessary.** It answered English questions reasonably well (80 %)
   but Finnish ones poorly (58 %). Above all, it **invented an answer to every unanswerable
   Finnish question** (0 % correct refusals): it named the CEO as the finance director, gave the
   wind-farm contract number for the battery project, and reported 2024 figures as 2023 figures.
2. **Qwen3.5-4B closes the language gap** on the standard questions (100 % English, 100 %
   Finnish), finds every item in the "find all similar items" questions, cites the right section
   97 % of the time and refuses correctly in 96 % of unanswerable cases. It is the new default.
3. **Gemma-4-E4B is accurate but impractical on this hardware.** On a matched sample it was as
   accurate as Qwen3.5-4B on facts, but with thinking switched off it writes its reasoning into
   the answer itself, at about 3 tokens per second: roughly two minutes per answer, and some
   answers ran out of length before reaching the conclusion.
4. **The price is speed.** On this CPU-only laptop Qwen3.5-4B reads a prompt about four times
   more slowly than Qwen2.5-3B. Asking several questions about the same documents stays fast,
   because llama-server reuses the cached prompt; the first question about a new selection is
   the slow one.
5. **Frontier models solve the whole benchmark.** Claude Opus 5 and GPT-6.1 Sol answered all
   186 cases correctly, standard and hard, in English, Finnish and across languages. The gap
   between the local 4B model and the frontier is therefore small on finding facts (98 % vs
   100 %) and visible on reasoning over them (89 % vs 100 % on the hard tier, 86 % in Finnish).
6. **Hard questions find the limits.** On questions that combine facts, need arithmetic,
   negation or picking the largest value from a table, Qwen3.5-4B drops to **89 %** (77 % on the
   hardest eight): it averages wrongly, names the newest instead of the oldest site, and misses
   items in "which sites had *no* injuries". Multi-step lookups and near-miss traps it handles
   perfectly. See [Hard questions](#hard-questions).
7. **The benchmark changed the application.** It exposed weak Finnish retrieval and a prompt
   flaw; both were fixed and re-measured (see [What the benchmark changed](#what-the-benchmark-changed)).

### Gemma-4-E4B

Qwen3.5-4B and Gemma-4-E4B are the two current small models considered for this project, so both
were tested.

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
| Overall score                               |      100 % |       100 % |
| Small details                               |      100 % |       100 % |
| Similar items: recall                       |      100 % |       100 % |
| Unanswerable refused correctly              |      100 % |       100 % |
| Citation points to the answer               |      100 % |        67 % |
| Seconds per question (incl. first, uncached) |         68 |         146 |
| Time to complete the 8 cases                |    9.1 min |    19.5 min |

The scores flatter Gemma: **none of its eight answers is a clean answer.** Every one is the
narration of its search, and three stop before any conclusion because the narration used up the
512-token answer limit - one ends with _"**Plan:** State the LTIF for 2025 using the citation from
Source 1."_ They count as correct because the expected value appears inside the narration; a user
would see the whole narration in the chat.

**Decision:** Qwen3.5-4B is the default. Gemma-4-E4B remains supported (the launcher accepts any
GGUF model) and is a reasonable choice on a machine with a GPU, where its writing speed matters
less.

### Hard questions

The first results put Qwen3.5-4B at 97 % - too close to the ceiling to tell good models apart, and a
benchmark in which every task is easy cannot rank models. A **hard tier** was therefore added:
22 questions per language (68 cases with the cross-lingual ones), written to need more than finding
one passage. It was built in two rounds: 14 questions first (Qwen3.5-4B scored 95 %), then 8 more
aimed at the weaknesses the first round revealed.

| Kind of hard question | Example | Cases | Qwen3.5-4B | Time per question | Time to complete |
| --- | --- | ---: | ---: | ---: | ---: |
| Multi-step lookup (2-3 facts) | _On which date did the injury happen at the site whose turbine contract is KR-2025-0417?_ | 14 | 100 % | 14 s | 3.3 min |
| Near-miss trap (not in the documents) | _Which company supplied the transformer for Pohjankangas?_ (Voltmark supplied Hietasaari's) | 6 | 100 % | 17 s | 1.7 min |
| Distractor in the same sentence | _What was the **original** commissioning date of the Hietasaari battery storage?_ | 2 | 100 % | 15 s | 0.5 min |
| Counting over a table | _How many lost-time injuries happened at the Vanhalinna plant?_ | 4 | 100 % | 15 s | 1.0 min |
| Arithmetic (sum, difference, average, share) | _On average, how many working days were lost per lost-time injury?_ (48 / 4 = 12) | 24 | 88 % | 44 s | 17.6 min |
| Negation | _Which of the company's sites had **no** lost-time injuries in 2025?_ (6 sites) | 8 | 81 % | 50 s | 6.6 min |
| Largest / smallest value with a trap | _Which site **in operation** has the largest capacity?_ (not Ristineva, 120 MW, under construction) | 10 | 70 % | 46 s | 7.7 min |
| **All hard questions** | | **68** | **89 %** | **34 s** | **38.4 min** |

The time column tells the same story as the score: the kinds of question the local model gets
wrong are also the ones it spends three times as long on (about 45 s against 15 s), writing long
answers that work through the table row by row.

By language the hard tier gives 95 % in English, 86 % in Finnish and 86-88 % across languages, so the
Finnish gap that the standard tier no longer showed for Qwen3.5-4B reappears on harder questions.

Typical hard-tier errors:

- **Arithmetic:** _"keskiarvo ... oli noin 12,5 työpäivää"_ - the right formula (48 / 4) with a wrong result;
  in another answer a wrong total (49) and an invented 32,900,000.
- **Smallest value:** asked in Finnish which operating site was commissioned first, it answered
  _Pohjankankaan tuulipuisto, 2019_ instead of Koskenniska, 1968.
- **Largest value:** it named the Vanhalinna fall (9 days) as the injury with the most lost days
  instead of the Ristineva accident (22 days) - it took the first row, not the maximum.
- **Negation:** listing sites with _no_ injuries, it missed sites and also listed ones that had
  injuries.

These errors share a pattern: a small model reading a table in its prompt does not reliably compute
over it. The application already avoids this where it matters - the _Ask your data_ feature has the
model write a query plan that the app executes in code - and the result supports that design.

### Frontier comparison

To put the local results in perspective, the same 186 cases (standard and hard, full context) were
sent to two current cloud frontier models through their official APIs:

| | Claude Opus 5 | GPT-6.1 Sol |
| --- | --- | --- |
| Vendor, API | Anthropic, Messages API (`anthropic` SDK) | OpenAI, Responses API (`openai` SDK) |
| Tier | Anthropic's main Opus model | OpenAI's "near-flagship" model, priced below GPT-6 Astra |
| Settings | vendor defaults (adaptive thinking), prompt caching | vendor defaults (built-in reasoning), automatic prompt caching |

Both received **exactly the prompt the application builds** for the local models - the same
system prompt, `<source>` blocks, locators and citation instructions - and were scored by the same
rules. Only the fictional benchmark corpus was sent; the application itself has no way to call a
cloud model (see [Privacy design](#privacy-design)).

| Overall score · time to complete, full context | Qwen3.5-4B (local, laptop CPU) | Claude Opus 5 | GPT-6.1 Sol |
| --- | ---: | ---: | ---: |
| Standard tier - English (42 cases) | 100 % · 12.2 min | 100 % · 3.1 min | 100 % · 2.6 min |
| Standard tier - Finnish (42 cases) | 100 % · 15.3 min | 100 % · 4.0 min | 100 % · 6.9 min |
| Standard tier - across languages (34 cases) | 88-100 % · 10.0 min | 100 % · 3.1 min | 100 % · 3.4 min |
| Hard tier - English (22 cases) | 95 % · 14.7 min | 100 % · 1.7 min | 100 % · 1.6 min |
| Hard tier - Finnish (22 cases) | 86 % · 11.1 min | 100 % · 2.5 min | 100 % · 2.9 min |
| Hard tier - across languages (24 cases) | 86-88 % · 12.7 min | 100 % · 2.6 min | 100 % · 2.9 min |
| **All 186 cases** | **95 % · 75.9 min** | **100 % · 17.1 min** | **100 % · 20.1 min** |
| Seconds per question | 24.5 | 5.5 | 6.5 |

Where the frontier models succeed and the local model fails is exactly the hard-tier weakness
described above: both compute the average (48 / 4 = **12** days), pick the oldest operating site
(Koskenniska, **1968**), list all six sites without injuries, and show their working - e.g.
_"Ristineva 120 MW + Tervaharju 78 MW = 198 MW; ... Erotus on 198 − 150 = 48 MW enemmän"_.

**What this means for the project.** For questions that need a fact found and cited - the
everyday use of a document workspace - the local Qwen3.5-4B is within a few percentage points of
the frontier (98 % vs 100 %), on a laptop without a GPU and without a document leaving the
machine. The frontier
advantage is in computing over tables and in Finnish reasoning; the application covers the first
by having code, not the model, do the arithmetic in _Ask your data_. The price of staying local
is speed (about 5x slower on this CPU) and the remaining reasoning gap; the price of the cloud is
sending the documents to a third party, which this application exists to avoid.

**The benchmark saturates at the frontier.** Both frontier models score 100 %, so this benchmark
ranks local models against the frontier but cannot rank frontier models against each other;
that would need longer documents and harder reasoning than a 13,000-character corpus allows.

**Tokens and cost.** Input tokens for the 186 answers in each result file, from the APIs' own
usage reports (the two vendors count tokens differently, so the numbers are not comparable with
each other):

| | Claude Opus 5 | GPT-6.1 Sol |
| --- | ---: | ---: |
| Input tokens, 186 questions | 1,254,484 | 788,672 |
| Input tokens per question | 6,744 | 4,240 |
| Visible answer, average | 683 characters | 188 characters |
| List price (input / output per 1M tokens) | $5 / $25 | $2 / $10 |
| Time to complete the 186 questions | 17.1 min | 20.1 min |

Without caching the input would cost about $6.30 (Claude) and $1.60 (GPT); both runs cached the
repeated document prompt, so the billed amount is lower. The Finnish half was asked twice (before
and after the Finnish proofreading), which adds about half again to the total actually used.
Output tokens include each model's hidden reasoning and were recorded only for the re-run half, so
the vendors' usage pages are the authoritative source for the exact bill.

### What was tested and why

The benchmark was **planned with a frontier AI model**: the
model proposed the question types, the fictional-corpus design and the text-matching scoring
rules, and the plan was then implemented and checked in this repository - the suite self-check
verifies every expected answer against the documents, and the scoring rules were corrected
wherever reading the actual answers showed them to be wrong.

Each goal of the benchmark maps to a question type:

| Goal                                             | Question type          | Count | Example (English / Finnish)                                                                                                         |
| ------------------------------------------------ | ---------------------- | ----: | ----------------------------------------------------------------------------------------------------------------------------------- |
| Retrieval of similar items - are they all found? | Similar items (lists)  |     8 | _Which projects are delayed or behind schedule?_ / _Mitkä hankkeet ovat viivästyneet tai aikataulusta jäljessä?_                     |
| Retrieval of very small details                  | Small details          |    26 | _What was the lost-time injury frequency (LTIF) in 2025?_ / _Mikä oli tapaturmataajuus (LTIF) vuonna 2025?_                          |
| Does it invent answers?                          | Not in the documents   |     8 | _Who is the company's chief financial officer?_ / _Kuka on yhtiön talousjohtaja?_                                                   |
| Tasks hard enough to separate models             | Hard tier              |    22 | _Which of the company's sites that are still in operation was commissioned first?_ / _Mikä yhtiön yhä käytössä olevista kohteista otettiin käyttöön ensimmäisenä?_ |
| English and Finnish                              | Every question in both |     - | 29 questions are also asked **across** languages (English question on Finnish documents and the reverse)                          |

Every question is asked in English on the English documents and in Finnish on the Finnish
documents, and the cross-lingual ones in both directions as well: **118 standard and 68 hard cases
per model and context strategy**.

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
| Similar items: precision       | for site and supplier lists, share of listed items that are correct; when the answer is a bulleted or numbered list only the list items count, so a remark such as "the others are already in operation" is not counted as listing them |
| Unanswerable: correct          | the answer says the documents do not contain it (about 20 English and Finnish phrasings are recognised), or corrects a false premise                                                                                                   |
| Number found in no document    | the answer contains a number that occurs in no document and not in the question (citations, list numbering and counts up to 12 are ignored); questions whose answer must be computed are left out, because sums and intermediate results are legitimately new numbers |
| Citation correct               | at least one citation resolves to a section that really contains the answer                                                                                                                                                          |
| Overall                        | mean over all cases: details and unanswerable count 1 or 0, a list counts its recall                                                                                                                                                 |

A **self-check** (`benchmark/run.py check`, also a unit test) verifies that every expected answer
really is present, at the stated location, in both language versions (for computed answers, that
the locations exist). Scoring rules were corrected four times after reading the answers - every
time because they penalised correct answers: remarks outside a list counted as listed items, lists
written as bold lines or tables were not recognised, computed intermediate numbers counted as
invented, and refusals written with contractions ("the sources don't contain ...") were missed.
`benchmark/run.py rescore` re-applied each fix to every saved answer of every model; no model was
re-run and no expected answer was changed.

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

| Overall score · time to complete (full context, standard tier) | Qwen2.5-3B | Qwen3.5-4B |
| ---------------------------------------------------- | ---------------: | ----------------: |
| English question → English documents (42 cases)     |   80 % · 3.1 min |  100 % · 12.2 min |
| Finnish question → Finnish documents (42 cases)     |   58 % · 8.3 min |  100 % · 15.3 min |
| English question → Finnish documents (17 cases)     |   60 % · 2.6 min |   100 % · 4.4 min |
| Finnish question → English documents (17 cases)     |   52 % · 2.3 min |    88 % · 5.6 min |

| Unanswerable questions refused correctly · time to complete | Qwen2.5-3B | Qwen3.5-4B |
| ---------------------------------------------------- | ---------------: | ----------------: |
| English (8 cases)                                    |    38 % · 0.5 min |   100 % · 2.1 min |
| Finnish (8 cases)                                    |     0 % · 1.4 min |   100 % · 1.7 min |

For Qwen3.5-4B the standard Finnish questions are now as easy as the English ones; Finnish stays
harder on the hard tier (86 % vs 95 %) and when a Finnish question is asked about English
documents (88 %), where the model has to translate while it searches. After the Finnish text was
proofread, Qwen3.5-4B also answered the two Finnish questions it had missed before - one of them
(D12) had been worded ungrammatically, a reminder that small models are sensitive to the wording
of a question.

### Retrieval: does the right passage reach the model?

Retrieval sends only the best-matching passages instead of whole documents. Measured **without a
model** (`benchmark/run.py retrieval`; the whole check, both tiers, completes in about 12 seconds
on the laptop): for every answerable question, is the
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

The table covers the standard questions, where one passage holds the answer. On the **hard**
questions the language-aware ranking is **no better** than plain BM25 (the answer's passage reached
the model in 85 % vs 95 % of English cases and 80 % vs 80 % of Finnish ones): their evidence is a
whole table or several sections, which better word matching does not help to find. The full table
for both tiers is in `benchmark/results/retrieval_check.json` and the Evaluation tab.

With a model (Qwen2.5-3B, the only model run with both strategies), retrieval scored **91 %**
overall on English (full context: 80 %) and **55 %** on Finnish (full context: 58 %). Fewer,
better-targeted passages helped the small model in English; in Finnish, the model's own language
weakness dominated. On this small corpus retrieval was also **slower**: the 42 English questions
took 9.0 min with retrieval against 3.1 min with full context (Finnish: 12.8 against 8.3 min),
because every question builds a different prompt, so llama-server cannot reuse its prompt cache.
Retrieval pays off in time only when the documents are much larger than the passages it sends.

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
| Qwen2.5-3B: 0 % correct refusals in Finnish, 58 % overall in Finnish                                                                                        | Default model changed to Qwen3.5-4B                                                                       | Finnish 58 % → **100 %**; Finnish refusals 0 % → **100 %**                                  |

The retrieval settings were chosen on this benchmark, so the retrieval gains are probably
somewhat optimistic for other documents; the model comparison does not depend on them (it uses
full context).

### Typical errors

The remaining errors of Qwen3.5-4B are few and specific (all answers are in the result file and
in the Evaluation tab):

- **Role confusion across languages:** asked in Finnish about the English documents, it named
  the CEO as the finance director, and said the company itself supplies the inverters that
  Helios Grid Systems supplies.
- **Before the Finnish proofreading** it also gave a wrong small number (_"kahdeksan voimalan
  perustuksesta"_ - eight instead of six foundations) and confused a capacity with a count
  (_"78 voimalaa"_ - 78 is MW); both were answered correctly on the proofread text.
- **Precision losses are partly a scoring artefact:** a list answer that says _"Kivijärvi is a
  solar park, not a wind farm"_ still counts Kivijärvi as listed.

### Limitations of this evaluation

- **The hard tier was written after seeing results.** It targets the weaknesses the first runs
  revealed, so it measures those weaknesses on purpose; it is not a neutral sample of questions.
- **Small corpus:** 4 documents and 64 questions per language. Differences of a few percentage
  points between models are within noise; the large gaps (Finnish 58 % → 100 %, refusals 25 % →
  96 %) are not.
- **One run per model** at temperature 0. Greedy decoding is close to deterministic, but no
  repeated runs were made.
- **Text matching has blind spots.** An answer that is right but phrased unusually can be scored
  wrong, and the "number in no document" metric cannot see a _real_ number used in the wrong place
  (2024 revenue reported as 2023); that case is caught by the unanswerable questions instead.
- **The Finnish text was written for the benchmark**; it is not a real Finnish company report. It
  was proofread for grammar and style on 9 October (three errors and a few awkward phrasings
  corrected, no facts changed) and the Finnish questions were then asked again of Qwen3.5-4B,
  Gemma-4-E4B and both frontier models. Qwen2.5-3B's Finnish answers are from the earlier wording,
  because its model file was no longer available.
- **Retrieval settings were tuned on the same benchmark** (see above).
- **Gemma-4-E4B was measured on 8 cases only**, so its numbers indicate behaviour, not a
  reliable score.
- **The frontier models reach 100 %**, so the benchmark cannot separate them from each other.
- **Precision and the number check are blunt.** A list that names other items explicitly as
  "not delayed" or "already in operation", or a correct total the model adds on its own, still
  counts against it. These cases are rare and shown in the result files.
- **Speed numbers are from one CPU-only laptop**; any GPU changes them completely. Frontier speeds
  include the network round trip from Finland.

### Reproducing the results

```powershell
# from the repository root, with the backend virtual environment
backend\.venv\Scripts\python benchmark\run.py check        # validate the suite (no model)
backend\.venv\Scripts\python benchmark\run.py retrieval    # retrieval table (no model, seconds)

# start llama-server with the model to test, then:
backend\.venv\Scripts\python benchmark\run.py run --strategies full          # 186 cases (standard + hard)
backend\.venv\Scripts\python benchmark\run.py run --strategies full --difficulty hard
backend\.venv\Scripts\python benchmark\run.py run --quick                    # 2 per category, a few minutes
backend\.venv\Scripts\python benchmark\run.py run --resume <run-id>          # continue an interrupted run
backend\.venv\Scripts\python benchmark\run.py rescore      # re-score saved answers after a scoring fix

# frontier reference (benchmark only; needs the optional packages and the vendor's key)
backend\.venv\Scripts\python -m pip install -r benchmark\requirements-frontier.txt
backend\.venv\Scripts\python benchmark\run.py run --strategies full --provider claude   # ANTHROPIC_API_KEY
backend\.venv\Scripts\python benchmark\run.py run --strategies full --provider openai   # OPENAI_API_KEY
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
   ├─ services/features        citations, verify, study, data_query, privacy_guard, translate, answer_check, timeline
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
   Below every answer the **answer check** shows whether all its numbers occur in the selected
   documents and whether its statements cite a source; numbers it could not find are highlighted
   in the answer text. Open the check to see the details.
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
9. **Timeline tab** – "Build timeline" lists the dated events of the selected documents in date
   order. Each event shows whether its date was found next to it in the cited passage; click the source to see
   the passage, filter by document, or export the timeline to Excel.
   Measured on the benchmark's annual report with Qwen3.5-4B: 10 of 11 English and 9 of 9 Finnish
   events verified; the one unverified event carried a wrong year (2026 for a closure planned for
   2028) and was flagged. Building takes about 5 minutes (English) and 7.5 minutes (Finnish) on the
   laptop CPU, at most 15 events per timeline.
10. **Evaluation tab** – the accuracy benchmark: run the model-free retrieval check, run the
   question set against the loaded model (quick or full, chosen languages and strategies) with live
   progress, compare runs side by side and read every answer that was scored wrong, with the reason.
11. **Privacy (left, bottom)** – LOCAL ONLY badge, endpoint, model, "Network needed: No (URL import only)".

## Privacy design

Default mode is **LOCAL ONLY**:

- The LLM endpoint must be a loopback address; a non-localhost `LDW_LLM_BASE_URL` blocks all AI
  requests (HTTP 403) and the UI shows a red warning instead of a green badge.
- The application has no cloud AI APIs, API keys, analytics or telemetry. The only code that can
  call a cloud model is the **benchmark's** optional frontier comparison
  (`benchmark/run.py run --provider claude|openai`): it runs from the command line only, sends only
  the fictional benchmark corpus, and cannot be started from the application's UI or API (a test
  checks this).
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

A browser smoke test (`scripts/ui_smoke_test.py`, Playwright) checks the main flows in a real
browser - upload, Finnish answer with a verified citation, citation opens the source passage,
translation, Evaluation tab - see [TESTING.md](TESTING.md).

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
| POST         | `/api/timeline`, `/api/timeline/export`                          | build a verified timeline / export it to Excel               |
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
- **Timeline and answer check verify, they do not prove.** The timeline accepts a date when it
  stands next to the event's own words in the source; an event described in completely different
  words can be flagged although its date is right, and a wrong event can pass if it reuses the
  wording of a nearby one. The answer check confirms that numbers occur in the sources, not that
  they are used for the right thing. Both say exactly what they checked.
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
      features/                 citations, verify, study, data_query, privacy_guard, structured, translate,
                                answer_check, timeline
      evaluation/               benchmark suite loader, scoring, runner, Markdown report
      document_store.py, export_store.py, generation.py
    utils/                      files (sanitizing, ids), logging
  tests/                        pytest suite + fixture generator
  requirements.txt
frontend/
  src/components/               DocumentPanel, ChatPanel (+SourceViewer), AgentPanel, FiguresPanel,
                                TimelinePanel, StudyPanel, DataPanel, PrivacyGuardPanel, EvaluationPanel, LauncherPanel,
                                StatusPanels (Privacy, Model, Exports)
  src/pages/Workspace.tsx       three-column layout
  src/services/api.ts           API client + SSE streaming
  src/types/api.ts
data/                           uploads/, converted/, exports/, images/, llm_settings.json (git-ignored)
benchmark/                      corpus/{en,fi}, questions.json, results/, corpus_text.py + make_corpus.py, run.py (CLI)
demo_data/                      demo teaching materials + generator
scripts/                        start_backend, start_frontend, example_llama_server_command
```
