"""
Executable Evaluation Suite Runner for Weather-Advisory Support Bot.

Usage:
    python evals/run_evals.py
    or
    ./.venv/bin/python evals/run_evals.py
"""
import asyncio
import os
import sys
import json
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evals.eval_suite import run_all_evaluations, format_markdown_report


async def main_async():
    print("=" * 80)
    print(" WEATHER-ADVISORY SUPPORT BOT — COMPREHENSIVE EVALUATION SUITE")
    print("=" * 80)
    print("Executing all 8 evaluation cases (including live Open-Meteo API query)...\n")

    summary = await run_all_evaluations()

    evals_dir = PROJECT_ROOT / "evals"
    report_md_path = evals_dir / "evaluation_report.md"
    report_json_path = evals_dir / "evaluation_report.json"

    # Save Markdown Report
    md_content = format_markdown_report(summary)
    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    # Save JSON Report
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(summary.model_dump(), f, indent=2, ensure_ascii=False)

    print("\n" + "-" * 80)
    print(f"{'CASE ID':<30} | {'STATUS':<8} | {'TYPE':<22} | {'TITLE'}")
    print("-" * 80)
    for r in summary.results:
        badge = "PASS" if r.status == "PASS" else "FAIL"
        print(f"{r.case_id:<30} | {badge:<8} | {r.evaluation_type:<22} | {r.title}")
    print("-" * 80)

    print(f"\nOverall Result: {summary.passed_cases}/{summary.total_cases} PASSED "
          f"({summary.passed_cases/summary.total_cases*100:.1f}%)")
    print(f"Detailed Markdown Report saved to: {report_md_path}")
    print(f"Machine-readable JSON Report saved to: {report_json_path}")
    print("=" * 80 + "\n")

    if summary.failed_cases > 0:
        sys.exit(1)
    sys.exit(0)


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
