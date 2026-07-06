import argparse
import json
import os
from datetime import datetime
from agents.plan_agent import run_plan
from agents.debug_agent import run_debug
from agents.judge_agent import run_judge
from agents.check_agent import run_check
from tools.vep import annotate_variant
from tools.utils import get_gene_symbol_from_transcript
from tools.vep import annotate_variant
from tools.scoring import classify
from data.planrag import query, is_vcep_disease, ACMG_PLANRAG_DB
from typing_extensions import TypedDict, Annotated
import operator
from typing import Any, TypeAlias
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

# HHT VCEP criteria — used when disease is HHT (or None for backward compatibility)
HHT_CRITERIA = ["PM2_SUPPORTING", "PP3", "BP4", "BA1", "BP7", "BS1", "PVS1", "PM4", "PM1", "PS1", "PM5", "PS4", "BS3", "PS3"]

# ACMG criteria — all automatable/partially-automatable entries in ACMG_PLANRAG_DB
# (deferred entries are filtered out by plan_agent, but excluded here too for clarity)
ACMG_CRITERIA = [k for k in ACMG_PLANRAG_DB if k != "SCORING"]

def get_criteria_for_disease(disease: str) -> list[str]:
    """Returns the correct criteria list based on whether disease has a VCEP spec."""
    if disease is None or is_vcep_disease(disease):
        return HHT_CRITERIA
    return ACMG_CRITERIA

def filter_criteria_by_variant_type(criteria: list[str], variant_type: str, disease: str = None) -> list[str]:
    """
    Removes criteria that explicitly restrict which variant types they apply to
    when the variant type doesn't match.

    A criterion with no variant_types field in planrag passes through unchanged.
    A criterion with variant_types = [...] is only kept if variant_type is in that list.
    """
    filtered = []
    skipped = []

    for criterion in criteria:
        entry = query(criterion, disease=disease)
        if entry is None or entry.get("excluded") or entry.get("deferred"):
            filtered.append(criterion)  # let plan_agent handle excluded/deferred
            continue

        allowed_types = entry.get("variant_types")
        if allowed_types is None:
            # no restriction — criterion applies to all variant types
            filtered.append(criterion)
        elif variant_type is not None and variant_type in allowed_types:
            filtered.append(criterion)
        else:
            # variant_type is None (VEP failed) or doesn't match — exclude
            skipped.append((criterion, allowed_types))

    if skipped:
        reason = f"{variant_type} variants" if variant_type else "unknown variant type (VEP failed)"
        print(f"PIPELINE: Skipped {len(skipped)} criterion/criteria — not applicable to {reason}:")
        for criterion, allowed in skipped:
            print(f"  - {criterion} (applies to: {allowed})")

    return filtered

# ==================================
# Type alias for langgraph states
# ==================================
ToolResults: TypeAlias = dict[str, dict[str, Any]]
Tasks: TypeAlias = dict[str, list[dict[str, str]]]
CriterionResults: TypeAlias = dict[str, dict[str, Any]]

# ==================================
# Stategraph reducer
# ==================================
def merge_tool_results(
        left: ToolResults,
        right: ToolResults
) -> ToolResults:
    """
    Merges tool result dictionaries in LangGraph state updates.
    Later values override earlier ones on key conflicts.
    """
    return {**left, **right}

def merge_criterion_results(
        left: CriterionResults,
        right: CriterionResults
) -> CriterionResults:
    """
    Merges criterion result dictionaries in LangGraph state updates.
    Later results overwrite existing entries with the same key.
    """
    return {**left, **right}

# ==================================
# Langgraph States
# ==================================
class OverallState(TypedDict):
    tasks: Tasks
    tool_results: Annotated[ToolResults, merge_tool_results]
    criterion_results: Annotated[CriterionResults, merge_criterion_results]
    variant_type: str | None 
    disease: str
    gene_symbol: str | None

class PerCriterionState(TypedDict):
    task: dict[str, str]
    variant_type: str | None
    disease: str
    previous_results: CriterionResults
    tool_results: ToolResults
    gene_symbol: str | None

# ==================================
# Helper Function for Printing  
# Results After Each Phase
# ==================================

def format_result(result: dict[str, Any]) -> str:
    """
    Format a single criterion result
    """
    if result.get("status") and result.get("status") == "error":
        return f"""CRITERION: {result.get("criterion", "unknown criterion")}
ERROR: {result.get("error", "unknown error")}"""
        
    return f"""CRITERION: {result["criterion"]}
APPLIED: {result.get("applies", "unknown")}
EVIDENCE: {result.get("evidence", "unknown")}
REASONING: {result.get("reasoning", "unknown")}
TOOL USED: {result.get("tool_used", "unknown")}"""

# ==================================
# Langgraph Nodes
# ==================================

def fan_in_after_phase_1(state: OverallState):
    """
    Fan-in node that aggregates and logs Phase 1 results.
    This function acts as a synchronization barrier after parallel execution.
    It collects results, formats a structured summary, and print outputs
    for debugging/traceability purposes.

    Returns:
        Empty dict (LangGraph convention for no state mutation here)
    """
    phase1_tasks = state.get("tasks", {}).get("phase1", {})
    phase1_criterions = [task.get("criterion") for task in phase1_tasks]
    
    phase1_results = [state.get("criterion_results", {}).get(criterion, {}) for criterion in phase1_criterions]
    
    print(f"\n{'-'*60}")
    print("PHASE 1 COMPLETE")
    print(f"CHECKED: {', '.join(phase1_criterions)}")

    # --------------- LOGGING ----------------
    for result in phase1_results:
        print("*" * 60)
        result_formatted = format_result(result)
        print(result_formatted)
    print(f"{'-'*60}")
        
    return {}

def fan_in_after_phase_2(state: OverallState):
    """
    Fan-in node that synchronizes phase completion in the LangGraph pipeline.

    Acts as a barrier node after parallel criterion execution, allowing the graph
    to merge results before proceeding to the next phase.

    Returns:
        Empty dict to trigger state continuation without modification.
    """
    phase2_tasks = state.get("tasks", {}).get("phase2", {})
    phase2_criterions = [task.get("criterion") for task in phase2_tasks]
    
    phase2_results = [state.get("criterion_results", {}).get(criterion, {}) for criterion in phase2_criterions]
    
    print(f"\n{'-'*60}")
    print("PHASE 2 COMPLETE")
    print(f"CHECKED: {', '.join(phase2_criterions)}")

    # --------------- LOGGING ----------------
    for result in phase2_results:
        print("*" * 60)
        result_formatted = format_result(result)
        print(result_formatted)
    print(f"{'-'*60}")

    return {}

def fan_in_after_phase_3(state: OverallState):
    """
    Fan-in node that synchronizes phase completion in the LangGraph pipeline.

    Acts as a barrier node after parallel criterion execution, allowing the graph
    to merge results before proceeding to the next phase.

    Returns:
        Empty dict to trigger state continuation without modification.
    """
    phase3_tasks = state.get("tasks", {}).get("phase3", {})
    phase3_criterions = [task.get("criterion") for task in phase3_tasks]
    
    phase3_results = [state.get("criterion_results", {}).get(criterion, {}) for criterion in phase3_criterions]
    
    print(f"\n{'-'*60}")
    print("PHASE 3 COMPLETE")
    print(f"CHECKED: {', '.join(phase3_criterions)}")

    # --------------- LOGGING ----------------
    for result in phase3_results:
        print("*" * 60)
        result_formatted = format_result(result)
        print(result_formatted)
    print(f"{'-'*60}")
    return {}

def fan_in_after_phase_4(state: OverallState):
    """
    Fan-in node that synchronizes phase completion in the LangGraph pipeline.

    Acts as a barrier node after parallel criterion execution, allowing the graph
    to merge results before proceeding to the next phase.

    Returns:
        Empty dict to trigger state continuation without modification.
    """
    phase4_tasks = state.get("tasks", {}).get("phase4", {})
    phase4_criterions = [task.get("criterion") for task in phase4_tasks]
    
    phase4_results = [state.get("criterion_results", {}).get(criterion, {}) for criterion in phase4_criterions]
    
    print(f"\n{'-'*60}")
    print("PHASE 4 COMPLETE")
    print(f"CHECKED: {', '.join(phase4_criterions)}")

    # --------------- LOGGING ----------------
    for result in phase4_results:
        print("*" * 60)
        result_formatted = format_result(result)
        print(result_formatted)
    print(f"{'-'*60}")
    return {}

def process_criterion(state: PerCriterionState):
    """
    Executes full evaluation pipeline for a single ACMG/VCEP criterion.

    Performs dependency checking, runs debug → judge → check agents sequentially,
    and returns updated criterion and tool results. Skips execution if prerequisites
    are not satisfied.
    """

    task = state["task"]
    criterion = task["criterion"]
    disease = state["disease"]
    previous_results = state["previous_results"]
    tool_results = state["tool_results"]
    gene_symbol = state["gene_symbol"]

    # ── PRECONDITION CHECK ────────────────────
    rag_entry = query(criterion, disease=disease)
    requires_applied = (rag_entry or {}).get("requires_applied", [])
    blocked_by      = (rag_entry or {}).get("blocked_by", [])
    skipped_reason = None

    for dep in requires_applied:
        dep_key = dep.upper().replace("-", "_").replace(" ", "_")
        dep_result = previous_results.get(dep_key)
        if dep_result is None:
            skipped_reason = f"{dep} has not been evaluated (dependency ordering error)"
            break
        if not dep_result.get("applies"):
            skipped_reason = f"{dep} did not apply — {criterion} requires it"
            break

    if not skipped_reason:
        for blocker in blocked_by:
            blocker_key = blocker.upper().replace("-", "_").replace(" ", "_")
            blocker_result = previous_results.get(blocker_key)
            if blocker_result and blocker_result.get("applies") is True:
                skipped_reason = f"{blocker} applied — {criterion} is excluded when {blocker} applies"
                break

    if skipped_reason:
        print(f"\nPIPELINE: Skipping {criterion} — {skipped_reason}")
        skipped_entry = {
            "criterion": criterion,
            "status": "skipped",
            "reason": skipped_reason,
        }
        
        return {"criterion_results": {criterion.upper().replace("-", "_"): skipped_entry}}        

    # print(f"\n{'─'*60}")
    # print(f"PIPELINE: Processing criterion {criterion}")
    # print(f"{'─'*60}")

    # ── DEBUG AGENT (runs Task agent internally) ──
    # print(f"\n[1/3] DEBUG AGENT — running Task agent and checking for technical errors")
    debug_output, tool_cache_update = run_debug(task, gene_symbol = gene_symbol, tool_results = tool_results)

    if debug_output.get("status") == "error":
        # print(f"PIPELINE: Debug agent failed for {criterion} — {debug_output.get('error')}")

        return {
            "criterion_results": {criterion.upper().replace("-", "_"): debug_output},
            "tool_results": tool_cache_update
        }  

    # ── JUDGE AGENT ───────────────────────
    # print(f"\n[2/3] JUDGE AGENT — checking reasoning")
    judge_output, tool_cache_update = run_judge(task, tool_results, debug_output)

    if judge_output.get("status") == "error":
        # print(f"PIPELINE: Judge agent failed for {criterion} — {judge_output.get('error')}")

        return {
            "criterion_results": {criterion.upper().replace("-", "_"): judge_output},
            "tool_results": tool_cache_update
            }  

    # ── CHECK AGENT ───────────────────────
    # print(f"\n[3/3] CHECK AGENT — validating formatting")
    final_output = run_check(judge_output)

    # print(f"\nPIPELINE: {criterion} complete")
    return {
        "criterion_results": {criterion.upper().replace("-", "_"): final_output},
        "tool_results": tool_cache_update
        } 

# ==================================
# Langgraph Routers
# ==================================

def fan_out_before_phase_1(state: OverallState):
    """
    Dispatch phase 1 tasks to parallel criterion nodes.
    """
    return [Send("process_phase_1_criterion", {
        "task": task, 
        "variant_type": state["variant_type"],
        "disease": state["disease"],
        "previous_results": state["criterion_results"],
        "tool_results": state["tool_results"],
        "gene_symbol": state["gene_symbol"]
    }) for task in state["tasks"]["phase1"]]

def fan_out_before_phase_2(state: OverallState):
    """
    Dispatch phase 2 tasks to parallel criterion nodes.
    """
    return [Send("process_phase_2_criterion", {
        "task": task, 
        "variant_type": state["variant_type"],
        "disease": state["disease"],
        "previous_results": state["criterion_results"],
        "tool_results": state["tool_results"],
        "gene_symbol": state["gene_symbol"]
    }) for task in state["tasks"]["phase2"]]

def fan_out_before_phase_3(state: OverallState):
    """
    Dispatch phase 3 tasks to parallel criterion nodes.
    """
    return [Send("process_phase_3_criterion", {
        "task": task, 
        "variant_type": state["variant_type"],
        "disease": state["disease"],
        "previous_results": state["criterion_results"],
        "tool_results": state["tool_results"],
        "gene_symbol": state["gene_symbol"]
    }) for task in state["tasks"]["phase3"]]

def fan_out_before_phase_4(state: OverallState):
    """
    Dispatch phase 4 tasks to parallel criterion nodes.
    """
    return [Send("process_phase_4_criterion", {
        "task": task, 
        "variant_type": state["variant_type"],
        "disease": state["disease"],
        "previous_results": state["criterion_results"],
        "tool_results": state["tool_results"],
        "gene_symbol": state["gene_symbol"]
    }) for task in state["tasks"]["phase4"]]
        
# ==================================
# Invoking state graph
# ==================================
def build_graph():
    """
    Build and compile LangGraph once.
    """
    graph_builder = StateGraph(OverallState)

    # NODES
    graph_builder.add_node("process_phase_1_criterion", process_criterion)
    graph_builder.add_node("fan_in_after_phase_1", fan_in_after_phase_1)
    graph_builder.add_node("process_phase_2_criterion", process_criterion)
    graph_builder.add_node("fan_in_after_phase_2", fan_in_after_phase_2)
    graph_builder.add_node("process_phase_3_criterion", process_criterion)
    graph_builder.add_node("fan_in_after_phase_3", fan_in_after_phase_3)
    graph_builder.add_node("process_phase_4_criterion", process_criterion)
    graph_builder.add_node("fan_in_after_phase_4", fan_in_after_phase_4)

    # EDGES
    graph_builder.add_conditional_edges(START, fan_out_before_phase_1)
    graph_builder.add_edge("process_phase_1_criterion", "fan_in_after_phase_1")
    graph_builder.add_conditional_edges("fan_in_after_phase_1", fan_out_before_phase_2)
    graph_builder.add_edge("process_phase_2_criterion", "fan_in_after_phase_2")
    graph_builder.add_conditional_edges("fan_in_after_phase_2", fan_out_before_phase_3)
    graph_builder.add_edge("process_phase_3_criterion", "fan_in_after_phase_3")
    graph_builder.add_conditional_edges("fan_in_after_phase_3", fan_out_before_phase_4)
    graph_builder.add_edge("process_phase_4_criterion", "fan_in_after_phase_4")
    graph_builder.add_edge("fan_in_after_phase_4", END)

    # COMPILE
    graph = graph_builder.compile()
    return graph

def process_criterions_in_parallel(
        tasks: Tasks,
        variant_type: str | None,
        disease: str,
        gene_symbol: str | None
) -> dict[str, Any]:
    """
    Runs ACMG/VCEP criterion evaluation in parallel using a LangGraph pipeline.
    Builds and executes a multi-phase graph that processes each criterion
    through parallel agent steps and aggregates tool + evaluation results.

    Args:
        tasks: Phased criterion tasks.
        variant_type: Variant consequence type (may be None).
        disease: Target disease context.
    Returns:
        Final LangGraph state with criterion and tool results.
    """

    # BUILD GRAPH
    graph = build_graph()

    # INVOKE
    initial_state: OverallState = {
        "tasks": tasks,
        "tool_results": {},
        "criterion_results": {},
        "variant_type": variant_type,
        "disease": disease,
        "gene_symbol": gene_symbol
    }

    state = graph.invoke(initial_state)
    return state

def run_pipeline(variant: str, disease: str) -> tuple[list[Any], dict]:
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

    # ── VARIANT TYPE DETECTION ─────────────────
    print("\nPIPELINE: Detecting variant type via Ensembl VEP...")
    vep_result = annotate_variant(variant)

    gene_symbol = None
    if "error" in vep_result:
        print(f"PIPELINE: Warning — could not determine variant type: {vep_result['error']}")
        variant_type = None
        # Fallback: get gene_symbol from NCBI when VEP fails
        if variant.startswith("NM_") and ":" in variant:
            transcript = variant.split(":")[0]
            gene_symbol = get_gene_symbol_from_transcript(transcript)
            if gene_symbol:
                print(f"PIPELINE: Gene detected from NCBI fallback: {gene_symbol}")
    else:
        variant_type = vep_result["variant_type"]
        gene_symbol = vep_result.get("gene_symbol")
        if gene_symbol:
            print(f"PIPELINE: Gene detected from VEP: {gene_symbol}")
        print(f"PIPELINE: Variant type detected: {variant_type} ({vep_result['variant_consequence']})")

    # ── CRITERIA SELECTION & FILTERING ────────
    # Always run filtering — when variant_type is None (VEP failed), conservatively
    # exclude criteria with variant_type restrictions since we can't verify the type.
    base_criteria = get_criteria_for_disease(disease)
    active_criteria = filter_criteria_by_variant_type(base_criteria, variant_type, disease=disease)

    # ── PLAN AGENT ────────────────────────────
    tasks = run_plan(variant, disease, active_criteria,gene_symbol=gene_symbol)

    if not tasks:
        print("PIPELINE: Plan agent returned no tasks. Exiting.")
        return [], {}

    # ── RUN PARALLEL AGENTS ────────────────────────────
    results = process_criterions_in_parallel(
        tasks=tasks,
        variant_type=variant_type,
        disease=disease,
        gene_symbol=gene_symbol
    )
    
    results_list = list(results["criterion_results"].values())
    results_dict = results["criterion_results"]

    # ── SCORING ───────────────────────────────────────────────────────────────
    scoring_label = "HHT VCEP" if (disease is None or is_vcep_disease(disease)) else "ACMG/AMP 2015"
    print("\n" + "─"*60)
    print(f"PIPELINE: Running {scoring_label} classification scoring...")
    scoring_result = classify(results_dict, disease=disease)
    print(f"PIPELINE: Classification → {scoring_result['classification']}")
    print(f"          Rule matched   → {scoring_result['rule_matched']}")

    return results_list, scoring_result


def print_report(variant: str, disease: str, results: list[dict], scoring_result: dict = None) -> None:
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

    # ── FINAL CLASSIFICATION ──────────────────────────────────────────────────
    if scoring_result:
        classification = scoring_result.get("classification", "Unknown")
        rule = scoring_result.get("rule_matched", "—")
        buckets = scoring_result.get("buckets", {})
        bucket_detail = scoring_result.get("bucket_detail", {})

        # Colour-code the classification label
        _COLOURS = {
            "Pathogenic":          "\033[91m",   # red
            "Likely Pathogenic":   "\033[93m",   # yellow
            "Likely Benign":       "\033[96m",   # cyan
            "Benign":              "\033[94m",   # blue
        }
        _RESET = "\033[0m"
        colour = _COLOURS.get(classification, "\033[97m")  # white for VUS

        print(f"\n{'─'*60}")
        print(f"  FINAL CLASSIFICATION: {colour}{classification}{_RESET}")
        print(f"  Rule matched        : {rule}")

        # Bucket summary (only print non-zero buckets)
        bucket_labels = {
            "vs":   "Very Strong (P)",
            "s":    "Strong (P)",
            "m":    "Moderate (P)",
            "sup":  "Supporting (P)",
            "ba":   "Stand-alone (B)",
            "bs":   "Strong (B)",
            "bsup": "Supporting (B)",
        }
        nonempty = {k: v for k, v in buckets.items() if v > 0}
        if nonempty:
            print(f"\n  Strength bucket counts:")
            for k, v in nonempty.items():
                criteria_in_bucket = [c for c, b in bucket_detail.items()
                                      if b == {
                                          "vs": "very_strong", "s": "strong",
                                          "m": "moderate", "sup": "supporting",
                                          "ba": "benign_stand_alone", "bs": "benign_strong",
                                          "bsup": "benign_supporting",
                                      }.get(k)]
                print(f"    {bucket_labels.get(k, k):20s}: {v}  [{', '.join(criteria_in_bucket)}]")

        # Incompatibility notes
        for note in scoring_result.get("incompatibility_notes", []):
            print(f"\n  ⚠  {note}")

        # Unrecognised criteria (should be empty in normal operation)
        for u in scoring_result.get("unrecognised_criteria", []):
            print(f"\n  ⚠  Unrecognised criterion skipped in scoring: {u}")

        print(f"{'─'*60}")

    if not results:
        print("No results to report.")
        return

    applied = []
    not_applied = []
    failed = []
    skipped = []

    for result in results:
        criterion = result.get("criterion", "Unknown")
        status = result.get("status")

        if status == "skipped":
            skipped.append(result)
            continue

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

    # ── SKIPPED CRITERIA ──────────────────────
    if skipped:
        print(f"\nSKIPPED CRITERIA ({len(skipped)}):")
        for r in skipped:
            print(f"\n  – {r['criterion']}")
            print(f"    Reason: {r.get('reason')}")

    # ── FAILED CRITERIA ───────────────────────
    if failed:
        print(f"\nFAILED CRITERIA ({len(failed)}):")
        for r in failed:
            print(f"\n  ! {r['criterion']}")
            print(f"    Error: {r.get('error')}")

    print("\n" + "="*60)


def _safe_variant_name(variant: str) -> str:
    """Filesystem-safe version of a variant string."""
    return variant.replace(":", "_").replace(">", "_").replace(".", "_").replace("/", "_")


def save_results(
    variant: str,
    disease: str,
    results: list[dict],
    scoring_result: dict | None = None,
    output_dir: str = "outputs",
    timestamped: bool = True,
) -> str:
    """
    Saves full JSON results to an output file inside ``output_dir``.

    In single-variant mode the filename is timestamped (preserves history).
    In batch mode (``timestamped=False``) the filename is deterministic
    (``<safe_variant>_<disease>.json``) so a re-run against the same folder
    can detect and skip variants that already completed.

    Returns the file path.
    """
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_variant = _safe_variant_name(variant)
    if timestamped:
        filename = os.path.join(output_dir, f"{safe_variant}_{disease}_{timestamp}.json")
    else:
        filename = os.path.join(output_dir, f"{safe_variant}_{disease}.json")

    output = {
        "variant": variant,
        "disease": disease,
        "timestamp": timestamp,
        "classification": scoring_result.get("classification") if scoring_result else None,
        "rule_matched":   scoring_result.get("rule_matched")   if scoring_result else None,
        "scoring":        scoring_result,
        "results": results,
    }

    with open(filename, "w") as f:
        json.dump(output, f, indent=2)

    return filename


# ==================================
# Batch mode (CSV input, parallel variants)
# ==================================

def run_batch(
    csv_path: str,
    max_concurrency: int = 5,
    output_dir: str | None = None,
    disease_default: str | None = None,
    variant_col: str = "hgvs_cdna",
    disease_col: str = "condition",
) -> str:
    """
    Runs the full pipeline over every variant in a CSV, in parallel.

    Each variant runs the existing (unchanged) per-criterion pipeline; multiple
    variants run concurrently through a bounded thread pool so total concurrency
    stays within the shared per-model rate limiters. One JSON file is written per
    variant into a per-run batch folder, plus a batch_summary.json.

    - Per-variant errors are isolated: a failure becomes an error file/summary row
      and the batch continues.
    - Resumable: if output_dir already contains a variant's file, it is skipped.

    Returns the batch output folder path.
    """
    import csv
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # One folder per batch run (unless an existing one is given, enabling resume).
    if output_dir is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.join("outputs", f"batch_{stamp}")
    os.makedirs(output_dir, exist_ok=True)

    # ── Read variants from CSV ────────────────────────────────────────────────
    rows = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        if variant_col not in fieldnames:
            raise ValueError(
                f"CSV is missing the variant column '{variant_col}'. "
                f"Columns found: {fieldnames}"
            )
        for row in reader:
            variant = (row.get(variant_col) or "").strip()
            if not variant:
                continue
            disease = (row.get(disease_col) or "").strip() if disease_col in fieldnames else ""
            disease = disease or disease_default
            if not disease:
                raise ValueError(
                    f"No disease for variant {variant}: CSV has no '{disease_col}' value "
                    f"and no --disease default was provided."
                )
            rows.append((variant, disease))

    total = len(rows)
    print(f"\nBATCH: {total} variant(s) from {csv_path}")
    print(f"BATCH: output folder -> {output_dir}")
    print(f"BATCH: max concurrency = {max_concurrency}\n")

    def _process(variant: str, disease: str) -> dict:
        safe = _safe_variant_name(variant)
        target = os.path.join(output_dir, f"{safe}_{disease}.json")
        if os.path.exists(target):
            print(f"BATCH: skip (already done) {variant}")
            return {"variant": variant, "disease": disease, "status": "skipped_existing", "file": target}
        try:
            results, scoring_result = run_pipeline(variant, disease)
            path = save_results(variant, disease, results, scoring_result,
                                 output_dir=output_dir, timestamped=False)
            return {
                "variant": variant,
                "disease": disease,
                "status": "ok",
                "classification": (scoring_result or {}).get("classification"),
                "rule_matched": (scoring_result or {}).get("rule_matched"),
                "file": path,
            }
        except Exception as e:  # isolate: one variant must not kill the batch
            err = {
                "variant": variant,
                "disease": disease,
                "status": "error",
                "error": f"{type(e).__name__}: {e}",
            }
            errfile = os.path.join(output_dir, f"{safe}_{disease}.error.json")
            with open(errfile, "w") as fh:
                json.dump(err, fh, indent=2)
            print(f"BATCH: ERROR on {variant} -- {err['error']}")
            return {**err, "file": errfile}

    summary = []
    done = 0
    with ThreadPoolExecutor(max_workers=max_concurrency) as pool:
        futures = {pool.submit(_process, v, d): v for v, d in rows}
        for fut in as_completed(futures):
            res = fut.result()
            summary.append(res)
            done += 1
            print(f"BATCH: [{done}/{total}] {res['variant']} -> {res['status']}"
                  + (f" ({res.get('classification')})" if res.get("classification") else ""))
            # Write summary incrementally so a crash doesn't lose progress.
            with open(os.path.join(output_dir, "batch_summary.json"), "w") as fh:
                json.dump({
                    "csv": csv_path,
                    "total": total,
                    "completed": done,
                    "max_concurrency": max_concurrency,
                    "results": summary,
                }, fh, indent=2)

    ok = sum(1 for r in summary if r["status"] == "ok")
    errs = sum(1 for r in summary if r["status"] == "error")
    skipped = sum(1 for r in summary if r["status"] == "skipped_existing")
    print(f"\nBATCH COMPLETE: {ok} ok, {errs} error, {skipped} skipped -> {output_dir}\n")
    return output_dir


def main():
    parser = argparse.ArgumentParser(
        description="LLM-based multi-agent pipeline for ACMG variant classification"
    )
    parser.add_argument(
        "--variant",
        type=str,
        default=None,
        help="Single variant in HGVS or gnomAD format (e.g. NM_000020.3:c.557G>T). "
             "Use this OR --csv."
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="Path to a CSV of variants to run as a batch (in parallel). Use this OR --variant."
    )
    parser.add_argument(
        "--disease",
        type=str,
        default=None,
        help="Disease name (e.g. HHT). Required for --variant; for --csv it is the fallback "
             "when a row has no disease column."
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=5,
        help="Batch mode only: number of variants to run concurrently (default 5)."
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Batch mode only: reuse an existing batch folder to resume (skips completed "
             "variants). Defaults to a new outputs/batch_<timestamp> folder."
    )
    parser.add_argument(
        "--variant-col",
        type=str,
        default="hgvs_cdna",
        help="Batch mode only: CSV column holding the variant (default: hgvs_cdna)."
    )
    parser.add_argument(
        "--disease-col",
        type=str,
        default="condition",
        help="Batch mode only: CSV column holding the disease (default: condition)."
    )

    args = parser.parse_args()

    # Exactly one of --variant / --csv must be given.
    if bool(args.variant) == bool(args.csv):
        parser.error("Provide exactly one of --variant (single) or --csv (batch).")

    if args.csv:
        run_batch(
            csv_path=args.csv,
            max_concurrency=args.max_concurrency,
            output_dir=args.output_dir,
            disease_default=args.disease,
            variant_col=args.variant_col,
            disease_col=args.disease_col,
        )
        return

    # ── Single-variant mode (unchanged behaviour) ─────────────────────────────
    if not args.disease:
        parser.error("--disease is required when using --variant.")

    results, scoring_result = run_pipeline(args.variant, args.disease)
    print_report(args.variant, args.disease, results, scoring_result)
    filepath = save_results(args.variant, args.disease, results, scoring_result)

    print(f"Full results saved to: {filepath}\n")


if __name__ == "__main__":
    main()