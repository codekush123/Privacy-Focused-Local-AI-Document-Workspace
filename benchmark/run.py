"""Command-line entry point for the accuracy benchmark.

Run from the repository root with the backend environment, e.g.

    backend/.venv/Scripts/python benchmark/run.py check
    backend/.venv/Scripts/python benchmark/run.py retrieval
    backend/.venv/Scripts/python benchmark/run.py run --quick
    backend/.venv/Scripts/python benchmark/run.py run --strategies full --languages fi
    backend/.venv/Scripts/python benchmark/run.py run --resume 20261003-143936_Qwen3.5-4B-Q4-K-M.gguf
    backend/.venv/Scripts/python benchmark/run.py report

``run`` uses whatever model llama-server currently has loaded; start each model
in turn (Model launcher or a terminal) and run the benchmark once per model.
Results are written to benchmark/results/ after every question, so an
interrupted run keeps what it has done.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.services.evaluation import report as report_mod  # noqa: E402
from app.services.evaluation.runner import RunConfig, results_dir, retrieval_check, run_cases  # noqa: E402
from app.services.evaluation.suite import load_suite, self_check  # noqa: E402


def cmd_check(_args) -> int:
    suite = load_suite()
    print(json.dumps(suite.summary(), ensure_ascii=False, indent=1))
    problems = self_check(suite)
    for p in problems:
        print("PROBLEM:", p)
    print("self-check:", "OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


def cmd_retrieval(_args) -> int:
    result = retrieval_check()
    path = results_dir() / "retrieval_check.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(report_mod.retrieval_table(result))
    print(f"\nSaved to {path}")
    return 0


async def _run(cfg: RunConfig, resume: str | None = None, only: list[str] | None = None) -> int:
    async for ev in run_cases(cfg, resume=resume, only_strategies=only):
        if ev["type"] == "start":
            print(f"Run {ev['id']}: model {ev['model']}, {ev['total']} cases, {ev['already_done']} already done")
        elif ev["type"] == "case":
            c = ev["case"]
            mark = "ERR" if "error" in c else ("ok " if c["correct"] else f"{c['score']:.2f}")
            print(f"[{ev['n']:>3}/{ev['total']}] {mark} {c['strategy']:9} {c['question_language']}->{c['corpus_language']} "
                  f"{c['id']}  {c['seconds']:5.1f}s  {c.get('error', '')}")
        else:
            print("\n" + report_mod.summary_line(ev["summary"]["all"]))
    return 0


def cmd_run(args) -> int:
    cfg = RunConfig(
        languages=args.languages,
        strategies=args.strategies,
        cross_lingual=not args.no_cross,
        categories=args.categories,
        question_ids=args.ids,
        limit=2 if args.quick else args.limit,
        max_output_tokens=args.max_tokens,
        stemming=not args.no_stemming,
        label=args.label or "",
    )
    only = args.strategies if args.resume and args.strategies_given else None
    return asyncio.run(_run(cfg, args.resume, only))


def cmd_report(_args) -> int:
    print(report_mod.markdown_report())
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="validate the suite (no model needed)")
    sub.add_parser("retrieval", help="retrieval recall with and without stemming (no model needed)")
    r = sub.add_parser("run", help="ask the loaded model every question and score the answers")
    r.add_argument("--languages", nargs="+", default=["en", "fi"], choices=["en", "fi"])
    r.add_argument("--strategies", nargs="+", default=["full", "retrieval"], choices=["full", "retrieval"])
    r.add_argument("--categories", nargs="+", choices=["detail", "list", "unanswerable"])
    r.add_argument("--ids", nargs="+", help="only these question ids")
    r.add_argument("--limit", type=int, help="at most N questions per category")
    r.add_argument("--quick", action="store_true", help="2 questions per category")
    r.add_argument("--no-cross", action="store_true", help="skip cross-lingual cases")
    r.add_argument("--no-stemming", action="store_true")
    r.add_argument("--max-tokens", type=int, default=512)
    r.add_argument("--label")
    r.add_argument("--resume", metavar="RUN_ID", help="continue an interrupted run (same model must be loaded)")
    sub.add_parser("report", help="print Markdown tables of all saved results")
    args = p.parse_args()
    args.strategies_given = "--strategies" in sys.argv
    return {"check": cmd_check, "retrieval": cmd_retrieval, "run": cmd_run, "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
