import argparse
import json
import os
from datetime import datetime
from agents.plan_agent import run_plan
from agents.debug_agent import run_debug
from agents.judge_agent import run_judge
from agents.check_agent import run_check
from tools.vep import annotate_variant
from tools.scoring import classify
from data.planrag import query, is_vcep_disease, ACMG_PLANRAG_DB
from typing_extensions import TypedDict, Annotated
import operator
from typing import Any, TypeAlias
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

# HHT VCEP criteria — used when disease is HHT (or None for backward compatibility)
HHT_CRITERIA = ["PM2_SUPPORTING", "PP3", "BP4", "BA1", "BP7", "BS1", "PVS1", "PM4", "PM1", "PS1", "PM5", "PS4"]

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
        elif variant_type in allowed_types:
            filtered.append(criterion)
        else:
            skipped.append((criterion, allowed_types))

    if skipped:
        print(f"PIPELINE: Skipped {len(skipped)} criterion/criteria — not applicable to {variant_type} variants:")
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

class PerCriterionState(TypedDict):
    task: dict[str, str]
    variant_type: str | None
    disease: str
    previous_results: CriterionResults
    tool_results: ToolResults

# ==================================
# Langgraph Nodes
# ==================================

def fan_in(state: OverallState):
    """
    Fan-in node that synchronizes phase completion in the LangGraph pipeline.

    Acts as a barrier node after parallel criterion execution, allowing the graph
    to merge results before proceeding to the next phase.

    Returns:
        Empty dict to trigger state continuation without modification.
    """
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

    print(f"\n{'─'*60}")
    print(f"PIPELINE: Processing criterion {criterion}")
    print(f"{'─'*60}")

    # ── DEBUG AGENT (runs Task agent internally) ──
    print(f"\n[1/3] DEBUG AGENT — running Task agent and checking for technical errors")
    debug_output, tool_cache_update = run_debug(task, tool_results = tool_results)

    if debug_output.get("status") == "error":
        print(f"PIPELINE: Debug agent failed for {criterion} — {debug_output.get('error')}")

        return {
            "criterion_results": {criterion.upper().replace("-", "_"): debug_output},
            "tool_results": tool_cache_update
        }  

    # ── JUDGE AGENT ───────────────────────
    print(f"\n[2/3] JUDGE AGENT — checking reasoning")
    judge_output = run_judge(task, debug_output)

    if judge_output.get("status") == "error":
        print(f"PIPELINE: Judge agent failed for {criterion} — {judge_output.get('error')}")

        return {
            "criterion_results": {criterion.upper().replace("-", "_"): judge_output},
            "tool_results": tool_cache_update
            }  

    # ── CHECK AGENT ───────────────────────
    print(f"\n[3/3] CHECK AGENT — validating formatting")
    final_output = run_check(judge_output)

    print(f"\nPIPELINE: {criterion} complete")
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
        "tool_results": state["tool_results"]
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
        "tool_results": state["tool_results"]
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
        "tool_results": state["tool_results"]
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
        "tool_results": state["tool_results"]
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
    graph_builder.add_node("fan_in_after_phase_1", fan_in)
    graph_builder.add_node("process_phase_2_criterion", process_criterion)
    graph_builder.add_node("fan_in_after_phase_2", fan_in)
    graph_builder.add_node("process_phase_3_criterion", process_criterion)
    graph_builder.add_node("fan_in_after_phase_3", fan_in)
    graph_builder.add_node("process_phase_4_criterion", process_criterion)

    # EDGES
    graph_builder.add_conditional_edges(START, fan_out_before_phase_1)
    graph_builder.add_edge("process_phase_1_criterion", "fan_in_after_phase_1")
    graph_builder.add_conditional_edges("fan_in_after_phase_1", fan_out_before_phase_2)
    graph_builder.add_edge("process_phase_2_criterion", "fan_in_after_phase_2")
    graph_builder.add_conditional_edges("fan_in_after_phase_2", fan_out_before_phase_3)
    graph_builder.add_edge("process_phase_3_criterion", "fan_in_after_phase_3")
    graph_builder.add_conditional_edges("fan_in_after_phase_3", fan_out_before_phase_4)
    graph_builder.add_edge("process_phase_4_criterion", END)

    # COMPILE
    graph = graph_builder.compile()
    return graph

def process_criterions_in_parallel(
        tasks: Tasks,
        variant_type: str | None,
        disease: str,
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

    if "error" in vep_result:
        print(f"PIPELINE: Warning — could not determine variant type: {vep_result['error']}")
        print("PIPELINE: Proceeding without variant type filtering")
        variant_type = None
    else:
        variant_type = vep_result["variant_type"]
        print(f"PIPELINE: Variant type detected: {variant_type} ({vep_result['variant_consequence']})")

    # ── CRITERIA SELECTION & FILTERING ────────
    base_criteria = get_criteria_for_disease(disease)
    active_criteria = base_criteria
    if variant_type is not None:
        active_criteria = filter_criteria_by_variant_type(base_criteria, variant_type, disease=disease)

    # ── PLAN AGENT ────────────────────────────
    tasks = run_plan(variant, disease, active_criteria)
    # print(tasks)

    if not tasks:
        print("PIPELINE: Plan agent returned no tasks. Exiting.")
        return [], {}

    # ── RUN PARALLEL AGENTS ────────────────────────────
    results = process_criterions_in_parallel(
        tasks=tasks,
        variant_type=variant_type,
        disease=disease
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


def save_results(variant: str, disease: str, results: list[dict], scoring_result: dict = None) -> str:
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
        "classification": scoring_result.get("classification") if scoring_result else None,
        "rule_matched":   scoring_result.get("rule_matched")   if scoring_result else None,
        "scoring":        scoring_result,
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
        help="Variant in HGVS or gnomAD format (e.g. NM_000020.3:c.557G>T or 12-51914005-G-T)"
    )
    parser.add_argument(
        "--disease",
        type=str,
        required=True,
        help="Disease name (e.g. HHT)"
    )

    args = parser.parse_args()

    results, scoring_result = run_pipeline(args.variant, args.disease)
    print_report(args.variant, args.disease, results, scoring_result)
    filepath = save_results(args.variant, args.disease, results, scoring_result)

    print(f"Full results saved to: {filepath}\n")


if __name__ == "__main__":
    main()