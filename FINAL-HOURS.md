# Final phase — hours log

**Phase: 28 September – 18 October 2026**

Each member records the hours they actually worked. Put your hours in your own column next to
the activity, or add a row if your activity is not listed. Update the totals when you do, and
commit your own hours yourself so the log matches the repository history.

Activities marked **(T)** are testing, benchmarking and verification. The project's target is that
at least **25 %** of the effort goes to them; the share is calculated at the bottom of this file.

---

## Week 1 — 28 September – 4 October

| Activity                                                                 | Kush | Achal | Kabya | Sidong |
| ------------------------------------------------------------------------ | ---: | ----: | ----: | -----: |
| (T) Benchmark design: question types, fictional corpus, expected answers |      |       |       |        |
| (T) Benchmark corpus in English and Finnish (writing, generation)        |      |       |       |        |
| (T) Scoring rules, suite self-check, runner and CLI                      |      |       |       |        |
| (T) Local model runs (Qwen2.5-3B, Qwen3.5-4B, Gemma-4-E4B) and analysis  |      |       |       |        |
| Language-aware retrieval (Finnish stemming, prefixes, titles)            |      |       |       |        |
| Finnish answers and answer translation                                   |      |       |       |        |
| Evaluation tab (UI)                                                      |      |       |       |        |
| Model switch (Qwen3.5-4B / Gemma-4-E4B), launcher and docs               |      |       |       |        |
|                                                                          |      |       |       |        |
| **Week 1 total**                                                         |      |       |       |        |

## Week 2 — 5 – 11 October

| Activity                                                                 | Kush | Achal | Kabya | Sidong |
| ------------------------------------------------------------------------ | ---: | ----: | ----: | -----: |
| (T) Hard question tier (multi-step, arithmetic, negation, traps)         |      |       |       |        |
| (T) Frontier comparison (Claude Opus 5, GPT-6.1 Sol)                     |      |       |       |        |
| (T) Reviewing answers, scoring fixes, re-scoring                         |      |       |       |        |
| (T) Unit and API tests                                                   |      |       |       |        |
| (T) Native-speaker review of the Finnish benchmark text                  |      |       |       |        |
| README evaluation report                                                 |      |       |       |        |
| AGENTS.md, TESTING.md, PLANS.md                                          |      |       |       |        |
|                                                                          |      |       |       |        |
| **Week 2 total**                                                         |      |       |       |        |

## Week 3 — 12 – 18 October

| Activity                                                                 | Kush | Achal | Kabya | Sidong |
| ------------------------------------------------------------------------ | ---: | ----: | ----: | -----: |
| (T) Manual click-through of all tabs (TESTING.md, "Manual checks")       |      |       |       |        |
| Demo video                                                               |      |       |       |        |
| Final report and submission                                              |      |       |       |        |
|                                                                          |      |       |       |        |
| **Week 3 total**                                                         |      |       |       |        |

---

## Phase total

| Member | Week 1 | Week 2 | Week 3 | Total | of which (T) |
| ------ | -----: | -----: | -----: | ----: | -----------: |
| Kush   |        |        |        |       |              |
| Achal  |        |        |        |       |              |
| Kabya  |        |        |        |       |              |
| Sidong |        |        |        |       |              |
| **All** |       |        |        |       |              |

**Share of testing, benchmarking and verification:** (T) hours ÷ total hours = ____ % (target ≥ 25 %)

---

## How to add your hours

1. `git pull`
2. Edit this file: put your hours in your column, on the rows you worked on. Add a row if what
   you did is not listed; mark it (T) if it is testing, benchmarking or verification.
3. Update your week totals, the phase total and the (T) column.
4. `git add FINAL-HOURS.md && git commit -m "Add <name> final-phase hours" && git push`
