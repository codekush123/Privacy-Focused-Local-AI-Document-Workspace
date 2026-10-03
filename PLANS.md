# PLANS.md

Plan for the final phase of the project (deadline **18 October 2026**). Updated as work is done;
decisions are recorded with their reason so later work does not undo them by accident.

## Feedback this plan responds to

From the professor on the prototype:

1. Build our own benchmark for accuracy: retrieval of similar items (did it find them all?),
   retrieval of very small details (did it hallucinate?), at least English and Finnish.
2. Replace the outdated Qwen2.5-3B-Instruct with Qwen3.5-4B or Gemma-4-E4B.

From the general comment to all projects:

3. Verify and benchmark against frontier models; do not make all test tasks too easy; spend at
   least 25 % of resources on testing.
4. Do not use models released 2+ years ago.
5. Structure the repository for AI coding agents: AGENTS.md, TESTING.md, PLANS.md.

## Status

| # | Work item | Status |
| - | --- | --- |
| 1 | Bilingual benchmark corpus (fictional company, PDF/DOCX/PPTX/XLSX, EN + FI) | done |
| 2 | Question set: details, similar-item lists, unanswerable, cross-lingual | done (42 per language) |
| 3 | Deterministic scoring + suite self-check | done |
| 4 | Model-free retrieval check; language-aware retrieval (stemming, prefixes, titles) | done (Finnish recall@5 90 % -> 100 %) |
| 5 | Runner, CLI, Evaluation tab, resume after interruption | done |
| 6 | Full-context runs: Qwen2.5-3B (baseline), Qwen3.5-4B | done (65 % vs 97 %) |
| 7 | Gemma-4-E4B | done as a matched sample (too slow on this CPU for a full run) |
| 8 | Finnish answers and translation of answers with working citations | done |
| 9 | Hard question tier (multi-hop, arithmetic, max/min, negation, traps) | done (22 per language); Qwen3.5-4B 89 % |
| 10 | Frontier reference (Claude Opus 5 via the Anthropic API, benchmark only) | runner done; waiting for an API key |
| 11 | AGENTS.md, TESTING.md, PLANS.md | done |
| 12 | README evaluation report updated with hard tier and frontier results | hard tier done; frontier after 10 |
| 13 | Native-speaker review of the Finnish corpus and questions | **open - team** |
| 14 | Final-phase hours log (shows the share of testing work) | **open - team** |
| 15 | Final manual click-through (TESTING.md, "Manual checks") and demo video | **open - team** |

## Decisions and reasons

- **Fictional corpus.** A model cannot know a company that does not exist, so a correct answer
  must come from the documents and an invented one is unambiguously a hallucination.
- **Deterministic scoring, no LLM judge.** Reproducible, free, auditable; the cost is that some
  correct but oddly phrased answers are scored wrong - documented as a limitation.
- **Qwen3.5-4B is the default model.** 97 % vs 65 % (Qwen2.5-3B) on the standard tier; Finnish
  95 % vs 58 %; correct refusals 92 % vs 25 %. Slower prompt reading is accepted.
- **Gemma-4-E4B not the default.** With thinking disabled it writes its reasoning into the answer
  (~2 minutes per answer on CPU, some answers cut off before the conclusion).
- **Models compared with full context.** Retrieval prompts cannot use the prompt cache, which made
  full multi-strategy runs take many hours on CPU; retrieval is evaluated separately (model-free
  check plus the Qwen2.5-3B run with both strategies).
- **Frontier comparison is benchmark-only.** The app's LOCAL ONLY guarantee is unchanged; only the
  fictional corpus is sent, only when someone runs `run.py run --provider claude` with their key.
- **Hard tier added after the first results.** The standard tier was near the ceiling for
  Qwen3.5-4B, which would hide differences between good models. A second round targeted the
  weaknesses the first round exposed (table max/min, averages, negation).
- **Scoring fixes are re-applied, never answers changed.** Two rules penalised correct answers
  (list remarks outside the list, computed numbers); `run.py rescore` re-scored saved answers.
- **Qwen2.5-3B not run on the hard tier.** Its model file was removed from the test machine; the
  standard tier remains the like-for-like comparison with the old model.

## Next steps (in order)

1. Run the frontier reference once an API key is available (about 10 minutes, a few euros).
2. Add the frontier numbers to the README evaluation report.
3. Team: Finnish review -> if text changes, regenerate and re-run Qwen3.5-4B (about 1 hour).
4. Team: hours log, manual click-through, demo video.
