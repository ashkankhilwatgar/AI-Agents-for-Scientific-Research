import argparse
import json
import os
from datetime import datetime
from agents.plan_agent import run_plan
from agents.debug_agent import run_debug
from agents.judge_agent import run_judge
from agents.check_agent import run_check

# ─────────────────────────────────────────────
# CRITERIA TO EVALUATE (expand as RAG grows)
# ─────────────────────────────────────────────
CRITERIA = ["PM2"]


def run_pipeline(variant: str, disease: str) -> list[dict]:
    """
    Main pipeline entry point.
    Runs all agents in sequence for each criterion.
    Returns a list of validated, formatted task outputs.
    """
    print("\n" + "="*60)
    print("PIPELINE: Starting variant classification")
    print(f"Variant:  {variant}")
    print(f"Disease:  {disease}")
    print("="*60)

    # ── PLAN AGENT ────────────────────────────
    tasks = run_plan(variant, disease, CRITERIA)

    if not tasks:
        print("PIPELINE: Plan agent returned no tasks. Exiting.")
        return []

    results = []

    for task in tasks:
        criterion = task.get("criterion")
        print(f"\n{'─'*60}")
        print(f"PIPELINE: Processing criterion {criterion}")
        print(f"{'─'*60}")

        # ── DEBUG AGENT (runs Task agent internally) ──
        print(f"\n[1/3] DEBUG AGENT — running Task agent and checking for technical errors")
        debug_output = run_debug(task)

        if debug_output.get("status") == "error":
            print(f"PIPELINE: Debug agent failed for {criterion} — {debug_output.get('error')}")
            results.append(debug_output)
            continue

        # ── JUDGE AGENT ───────────────────────
        print(f"\n[2/3] JUDGE AGENT — checking reasoning")
        judge_output = run_judge(task, debug_output)

        if judge_output.get("status") == "error":
            print(f"PIPELINE: Judge agent failed for {criterion} — {judge_output.get('error')}")
            results.append(judge_output)
            continue

        # ── CHECK AGENT ───────────────────────
        print(f"\n[3/3] CHECK AGENT — validating formatting")
        final_output = run_check(judge_output)

        results.append(final_output)
        print(f"\nPIPELINE: {criterion} complete")

    return results


def print_report(variant: str, disease: str, results: list[dict]) -> None:
    """
    Prints a human-readable classification report to the terminal.
    """
    print("\n" + "="*60)
    print("CLASSIFICATION REPORT")
    print("="*60)
    print(f"Variant : {variant}")
    print(f"Disease : {disease}")
    print(f"Date    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    if not results:
        print("No results to report.")
        return

    applied = []
    not_applied = []
    failed = []

    for result in results:
        criterion = result.get("criterion", "Unknown")
        status = result.get("status")

        if status == "error":
            failed.append(result)
            continue

        if result.get("applies"):
            applied.append(result)
        else:
            not_applied.append(result)

    # ── CRITERIA THAT APPLY ───────────────────
    print(f"\nCRITERIA APPLIED ({len(applied)}):")
    if not applied:
        print("  None")
    for r in applied:
        print(f"\n  ✓ {r['criterion']}")
        print(f"    Evidence : {r.get('evidence')}")
        print(f"    Reasoning: {r.get('reasoning')}")
        print(f"    Tool     : {r.get('tool_used')} → {r.get('tool_input')}")

    # ── CRITERIA THAT DO NOT APPLY ────────────
    print(f"\nCRITERIA NOT APPLIED ({len(not_applied)}):")
    if not not_applied:
        print("  None")
    for r in not_applied:
        print(f"\n  ✗ {r['criterion']}")
        print(f"    Evidence : {r.get('evidence')}")
        print(f"    Reasoning: {r.get('reasoning')}")

    # ── FAILED CRITERIA ───────────────────────
    if failed:
        print(f"\nFAILED CRITERIA ({len(failed)}):")
        for r in failed:
            print(f"\n  ! {r['criterion']}")
            print(f"    Error: {r.get('error')}")

    print("\n" + "="*60)


def save_results(variant: str, disease: str, results: list[dict]) -> str:
    """
    Saves full JSON results to a timestamped output file.
    Returns the file path.
    """
    os.makedirs("outputs", exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_variant = variant.replace(":", "_").replace(">", "_").replace(".", "_")
    filename = f"outputs/{safe_variant}_{disease}_{timestamp}.json"

    output = {
        "variant": variant,
        "disease": disease,
        "timestamp": timestamp,
        "results": results
    }

    with open(filename, "w") as f:
        json.dump(output, f, indent=2)

    return filename


def main():
    parser = argparse.ArgumentParser(
        description="LLM-based multi-agent pipeline for ACMG variant classification"
    )
    parser.add_argument(
        "--variant",
        type=str,
        required=True,
        help="Variant in HGVS or gnomAD format (e.g. NM_000020.3:c.557G>T or 12-51914005-G-T)"
    )
    parser.add_argument(
        "--disease",
        type=str,
        required=True,
        help="Disease name (e.g. HHT)"
    )

    args = parser.parse_args()

    results = run_pipeline(args.variant, args.disease)
    print_report(args.variant, args.disease, results)
    filepath = save_results(args.variant, args.disease, results)

    print(f"Full results saved to: {filepath}\n")


if __name__ == "__main__":
    main()