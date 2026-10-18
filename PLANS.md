# PLANS.md

Plan for the final phase of the project (deadline **18 October 2026**). Updated as work is done;
decisions are recorded with their reason so later work does not undo them by accident.

## Goals of the final phase

1. Measure accuracy with our own benchmark: retrieval of similar items (are they all found?),
   retrieval of very small details (is anything invented?), in English and in Finnish.
2. Move to current small models: Qwen3.5-4B or Gemma-4-E4B instead of Qwen2.5-3B-Instruct.
3. Compare against frontier models, with test tasks hard enough to separate models, and spend at
   least 25 % of the effort on testing and verification.
4. Use only current models.
5. Structure the repository for AI coding agents: AGENTS.md, TESTING.md, PLANS.md.

## Status

| # | Work item | Status |
| - | --- | --- |
| 1 | Bilingual benchmark corpus (fictional company, PDF/DOCX/PPTX/XLSX, EN + FI) | done |
| 2 | Question set: details, similar-item lists, unanswerable, cross-lingual | done (42 per language) |
| 3 | Deterministic scoring + suite self-check | done |
| 4 | Model-free retrieval check; language-aware retrieval (stemming, prefixes, titles) | done (Finnish recall@5 90 % -> 100 %) |
| 5 | Runner, CLI, Evaluation tab, resume after interruption | done |
| 6 | Full-context runs: Qwen2.5-3B (baseline), Qwen3.5-4B | done (65 % vs 98 % standard) |
| 7 | Gemma-4-E4B | done as a matched sample (too slow on this CPU for a full run) |
| 8 | Finnish answers and translation of answers with working citations | done |
| 9 | Hard question tier (multi-hop, arithmetic, max/min, negation, traps) | done (22 per language); Qwen3.5-4B 89 % |
| 10 | Frontier reference: Claude Opus 5 and GPT-6.1 Sol via their APIs, benchmark only | done (both 100 % on all 186 cases) |
| 11 | AGENTS.md, TESTING.md, PLANS.md | done |
| 12 | README evaluation report updated with hard tier and frontier results | done |
| 13 | Finnish corpus and questions proofread (grammar/style); Finnish cases re-run | done 9 Oct; a native speaker's read-through is still welcome |
| 14 | Hours and responsibilities of each member | done 18 Oct (FINAL-HOURS.md) |
| 15 | Browser click-through of the new features | done 9 Oct with `scripts/ui_smoke_test.py`: found and fixed 3 bugs and a 404 (TESTING.md, layer 7) |
| 16 | Live answer check on every answer (numbers, citations, refusals; no model call) | done 9 Oct |
| 17 | Timeline of dated events with every date verified in its source, Excel export | done 9 Oct |
| 18 | Final manual check by the team and demo video | **open - team** |
| 19 | Whole-project review: every defect reproduced first, then fixed with a test (list below and in TESTING.md) | done 14 Oct |
| 20 | Every completion streamed with llama-server's progress reports: real reading progress in the UI, no read timeout on long CPU prompts, cut-off answers reported | done 14 Oct |
| 21 | `auto` decided by the context budget instead of a 12,000-character threshold; measured against the old default | done 14 Oct (README, "Default context strategy") |
| 22 | Parameter tests: retrieval sweep (82 settings, no model), file-generation output budget, chat temperature | done 14 Oct (README, "Parameter tests") |
| 23 | UI: tabs keep their state, cited passage highlighted, drop files anywhere, keyboard control (Escape, Study keys), New chat / copy / Try again / Continue, Stop for the agent, tiers and `auto` in the Evaluation tab | done 14 Oct |
| 24 | Browser smoke test extended to the new interactions and re-run | extended 14 Oct; the run found and fixed the answer-language problem (TESTING.md), then stopped when the library was cleared in another window - **open: one clean re-run** |
| 25 | "Vastaa suomeksi" followed reliably: the language rule repeated after the sources | done 14 Oct (3 of 6 → 6 of 6 Finnish answers) |

## Decisions and reasons

- **Fictional corpus.** A model cannot know a company that does not exist, so a correct answer
  must come from the documents and an invented one is unambiguously a hallucination.
- **Deterministic scoring, no LLM judge.** Reproducible, free, auditable; the cost is that some
  correct but oddly phrased answers are scored wrong - documented as a limitation.
- **Qwen3.5-4B is the default model.** 98 % vs 65 % (Qwen2.5-3B) on the standard tier; Finnish
  100 % vs 58 %; correct refusals 96 % vs 25 %. Slower prompt reading is accepted.
- **Gemma-4-E4B not the default.** With thinking disabled it writes its reasoning into the answer
  (~2 minutes per answer on CPU, some answers cut off before the conclusion).
- **Models compared with full context.** Retrieval prompts cannot use the prompt cache, which made
  full multi-strategy runs take many hours on CPU; retrieval is evaluated separately (model-free
  check plus the Qwen2.5-3B run with both strategies).
- **Frontier comparison is benchmark-only.** The app's LOCAL ONLY guarantee is unchanged; only the
  fictional corpus is sent, only when someone runs `run.py run --provider claude|openai` with their
  key. The app's API cannot request a cloud provider (tested).
- **Frontier models: Claude Opus 5 and GPT-6.1 Sol.** Comparable tiers (strong, not the most
  expensive model of each vendor), vendor-default settings, same prompts as the local models.
  Both scored 100 %, so the benchmark measures the local-vs-frontier gap but cannot rank frontier
  models against each other.
- **Hard tier added after the first results.** The standard tier was near the ceiling for
  Qwen3.5-4B, which would hide differences between good models. A second round targeted the
  weaknesses the first round exposed (table max/min, averages, negation).
- **Scoring fixes are re-applied, never answers changed.** Two rules penalised correct answers
  (list remarks outside the list, computed numbers); `run.py rescore` re-scored saved answers.
- **Qwen2.5-3B not run on the hard tier.** Its model file was removed from the test machine; the
  standard tier remains the like-for-like comparison with the old model.
- **`auto` = full context while it fits the window (14 Oct).** The old rule (retrieval above
  12,000 characters) sent the benchmark's own corpus - 4,000 tokens, a quarter of the window -
  through retrieval: 30 % fewer tokens, but no prompt cache between questions and weak
  cross-lingual recall. The chat's default was therefore not the configuration the evaluation
  measured. The threshold stays available (`LDW_RETRIEVAL_AUTO_THRESHOLD_CHARACTERS`) for slow
  machines that ask one question per selection.
- **Every completion streamed, with `return_progress` (14 Oct).** The only way to see how far
  llama-server has read a prompt, and the only way a silent 10-minute prompt read on a CPU does
  not trip the read timeout. Servers without the flag ignore it.
- **Separate output budget for generated files: 3,072 tokens (14 Oct).** Measured: a Word summary
  of the 9-page annual report needs 2,393 tokens; with the chat's 1,024 it was cut off twice and
  failed after 7 minutes. A cut-off answer is retried once with up to twice the room - never with
  the same limit.
- **Retrieval defaults unchanged after the sweep (14 Oct).** 82 settings (passage size, top-k,
  neighbours, Finnish prefix length) measured without a model: the defaults are on the plateau,
  prefix length 6 is the best, and the small gains elsewhere would only fit the settings further
  to this benchmark.
- **Spreadsheet cells are never formulas (14 Oct).** Model output and document text can contain
  `=HYPERLINK(...)`; written as a formula it could send data away when the file is opened, which
  contradicts the LOCAL ONLY promise.

## Next steps (in order)

1. Re-run `scripts/ui_smoke_test.py` once with nobody else using the app (item 24).
2. If a native speaker changes the Finnish text, regenerate
   (`make_corpus.py`, `make_questions.py`) and re-run the Finnish cases (see TESTING.md).
3. Team: final manual check (TESTING.md, "Manual checks") and demo video; re-run
   `scripts/ui_smoke_test.py` before recording.
4. Optional: a longer corpus or harder reasoning tier if frontier models are to be ranked against
   each other.
