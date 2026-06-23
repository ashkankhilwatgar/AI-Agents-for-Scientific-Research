import argparse
import json
import os
from datetime import datetime
from operator import add
from typing import Annotated, Any, TypedDict, Optional

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from agents.plan_agent import run_plan
from agents.debug_agent import run_debug
from agents.judge_agent import run_judge
from agents.check_agent import run_check
from tools.utils import get_variant_type
from data.planrag import query


CRITERIA = [
    "PM2_SUPPORTING",
    "PP3",
    "BP4",
    "BA1",
    "BP7",
    "BS1",
    "PVS1",
    "PM4",
    "PM1",
    "PS1",
    "PM5",
    "PS4",
]


class PipelineGraphState(TypedDict):
    """
    Shared state for the the entire pipeline graph. 
    """

    tasks: list[dict[str, Any]]
    variant_type: Optional[str]
    results: Annotated[list[dict[str, Any]], add]


class CriterionWorkerState(TypedDict):
    """
    State for one parallel criterion worker.
    """

    task: dict[str, Any]
    variant_type: str | None
    task_index: int


def filter_criteria_by_variant_type(criteria: list[str], variant_type: str) -> list[str]:
    """
    Removes criteria that explicitly restrict which variant types they apply to
    when the variant type doesn't match.

    A criterion with no variant_types field in planrag passes through unchanged.
    A criterion with variant_types = [...] is only kept if variant_type is in that list.
    """
    filtered = []
    skipped = []

    for criterion in criteria:
        entry = query(criterion)
        if entry is None or entry.get("excluded") or entry.get("deferred"):
            filtered.append(criterion)  # let plan_agent handle excluded/deferred
            continue

        allowed_types = entry.get("variant_types")
        if allowed_types is None:
            # no restriction — criterion applies to all variant types
            filtered.append(criterion)
        elif variant_type in allowed_types:
            filtered.append(criterion)
        else:
            skipped.append((criterion, allowed_types))

    if skipped:
        print(
            f"PIPELINE: Skipped {len(skipped)} criterion/criteria — "
            f"not applicable to {variant_type} variants:"
        )
        for criterion, allowed in skipped:
            print(f"  - {criterion} (applies to: {allowed})")

    return filtered


def _dispatch_tasks(state: PipelineGraphState) -> list[Send]:
    """
    Fan out the planned tasks to parallel criterion workers.
    Each criterion worker runs the original sequential logic
    """
    sends = []

    for task_index, task in enumerate(state["tasks"]):
        sends.append(
            Send(
                "process_criterion",
                {
                    "task": task,
                    "variant_type": state.get("variant_type"),
                    "task_index": task_index,
                },
            )
        )

    return sends


def _process_one_criterion(state: CriterionWorkerState) -> dict[str, list[dict[str, Any]]]:
    """
    Runs the original per-criterion logic.
    """
    # Make a copy so this worker does not mutate the shared task object.
    task = dict(state["task"])
    task_index = state["task_index"]
    criterion = task.get("criterion", "Unknown")

    # Inject variant_type into task dict so downstream agents have it if needed.
    task["variant_type"] = state.get("variant_type")

    print(f"\n{'─' * 60}")
    print(f"PIPELINE: Processing criterion {criterion}")
    print(f"{'─' * 60}")

    # ── DEBUG AGENT (runs Task agent internally) ──
    print("\n[1/3] DEBUG AGENT — running Task agent and checking for technical errors")
    debug_output = run_debug(task)

    if debug_output.get("status") == "error":
        print(f"PIPELINE: Debug agent failed for {criterion} — {debug_output.get('error')}")
        result = _attach_result_metadata(debug_output, criterion, task_index)
        return {"results": [result]}

    # ── JUDGE AGENT ───────────────────────
    print("\n[2/3] JUDGE AGENT — checking reasoning")
    judge_output = run_judge(task, debug_output)

    if judge_output.get("status") == "error":
        print(f"PIPELINE: Judge agent failed for {criterion} — {judge_output.get('error')}")
        result = _attach_result_metadata(judge_output, criterion, task_index)
        return {"results": [result]}

    # ── CHECK AGENT ───────────────────────
    print("\n[3/3] CHECK AGENT — validating formatting")
    final_output = run_check(judge_output)
    result = _attach_result_metadata(final_output, criterion, task_index)

    print(f"\nPIPELINE: {criterion} complete")
    return {"results": [result]}


def _attach_result_metadata(
    result: dict[str, Any],
    criterion: str,
    task_index: int,
) -> dict[str, Any]:
    """
    Adds small internal metadata to restore the original task order after
    parallel execution.
    """
    normalized_result = dict(result)
    normalized_result.setdefault("criterion", criterion)
    normalized_result["__task_index"] = task_index
    return normalized_result


def _build_parallel_criterion_graph():
    """
    Builds the LangGraph graph that runs all criteria in parallel.

    Graph shape:

        START
          |
          | dynamic Send(...) fan-out
          v
        process_criterion   process_criterion   process_criterion ...
          |                  |                   |
          +------------------+-------------------+
                             |
                            END

    - Planning is still one shared step.
    - Each criterion task is independent after planning.
    - Therefore each criterion can run in parallel.
    - Results are merged using the reducer on PipelineGraphState.results.
    """
    graph_builder = StateGraph(PipelineGraphState)
    graph_builder.add_node("process_criterion", _process_one_criterion)
    graph_builder.add_conditional_edges(START, _dispatch_tasks)
    graph_builder.add_edge("process_criterion", END)
    return graph_builder.compile()


def _run_tasks_in_parallel(
    tasks: list[dict[str, Any]],
    variant_type: str | None,
    max_concurrency: int | None = None,
) -> list[dict[str, Any]]:
    """
    Runs planned criterion tasks in parallel using LangGraph.

    `max_concurrency` is optional. It is useful when calling external APIs
    that has a rate limit
    """
    graph = _build_parallel_criterion_graph()

    initial_state: PipelineGraphState = {
        "tasks": tasks,
        "variant_type": variant_type,
        "results": [],
    }

    config = {"max_concurrency": max_concurrency} if max_concurrency is not None else None
    graph_output = graph.invoke(initial_state, config=config)

    results = graph_output.get("results", [])

    # Restore deterministic output order after parallel execution.
    results.sort(key=lambda r: r.get("__task_index", 10**9))

    # Remove internal metadata before printing/saving final results.
    for result in results:
        result.pop("__task_index", None)

    return results


def run_pipeline(
    variant: str,
    disease: str,
    max_concurrency: int | None = None,
) -> list[dict[str, Any]]:
    """
    Main pipeline entry point.

    Returns a list of validated, formatted task outputs.
    """
    print("\n" + "=" * 60)
    print("PIPELINE: Starting variant classification")
    print(f"Variant:  {variant}")
    print(f"Disease:  {disease}")
    print("=" * 60)

    # ── VARIANT TYPE DETECTION ─────────────────
    print("\nPIPELINE: Detecting variant type via Ensembl VEP...")
    vep_result = get_variant_type(variant)

    if "error" in vep_result:
        print(f"PIPELINE: Warning — could not determine variant type: {vep_result['error']}")
        print("PIPELINE: Proceeding without variant type filtering")
        variant_type = None
    else:
        variant_type = vep_result["variant_type"]
        print(f"PIPELINE: Variant type detected: {variant_type} ({vep_result['raw_consequence']})")

    # ── CRITERIA FILTERING ─────────────────────
    active_criteria = CRITERIA
    if variant_type is not None:
        active_criteria = filter_criteria_by_variant_type(CRITERIA, variant_type)

    # ── PLAN AGENT ────────────────────────────
    tasks = run_plan(variant, disease, active_criteria)
    print(tasks)

    if not tasks:
        print("PIPELINE: Plan agent returned no tasks. Exiting.")
        return []

    print("\nPIPELINE: Running criterion workers in parallel with LangGraph")
    if max_concurrency is not None:
        print(f"PIPELINE: max_concurrency = {max_concurrency}")

    return _run_tasks_in_parallel(
        tasks=tasks,
        variant_type=variant_type,
        max_concurrency=max_concurrency,
    )


def print_report(variant: str, disease: str, results: list[dict[str, Any]]) -> None:
    """
    Prints a human-readable classification report to the terminal.
    """
    print("\n" + "=" * 60)
    print("CLASSIFICATION REPORT")
    print("=" * 60)
    print(f"Variant : {variant}")
    print(f"Disease : {disease}")
    print(f"Date    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

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

    print("\n" + "=" * 60)


def save_results(variant: str, disease: str, results: list[dict[str, Any]]) -> str:
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
        "results": results,
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
        help="Variant in HGVS or gnomAD format (e.g. NM_000020.3:c.557G>T or 12-51914005-G-T)",
    )
    parser.add_argument(
        "--disease",
        type=str,
        required=True,
        help="Disease name (e.g. HHT)",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=None,
        help=(
            "Optional maximum number of criterion workers to run at the same time. "
            "Useful for avoiding LLM/API rate limits."
        ),
    )

    args = parser.parse_args()

    results = run_pipeline(
        args.variant,
        args.disease,
        max_concurrency=args.max_concurrency,
    )
    print_report(args.variant, args.disease, results)
    filepath = save_results(args.variant, args.disease, results)

    print(f"Full results saved to: {filepath}\n")


if __name__ == "__main__":
    main()
