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
from data.classification_guidelines import query, is_vcep_disease, ACMG_CRITERIA_DB
from typing_extensions import TypedDict, Annotated
import operator
from typing import Any, TypeAlias
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# ==================================
# RICH LIBRARY INITIALIZATION
# ==================================

console = Console()

def _display(value: Any) -> str:
    """Return a terminal-friendly representation for optional values."""
    return "—" if value is None or value == "" else str(value)

def _status_message(
    label: str,
    message: Any = None,
    *,
    style: str = "cyan",
    symbol: str = "•",
) -> None:
    """Print a consistently styled one-line pipeline status message."""
    line = Text()
    line.append(f"{symbol} {label}", style=f"bold {style}")
    if message is not None:
        line.append(": ", style="dim")
        line.append(_display(message))
    console.print(line)

def _key_value_panel(
    title: str,
    rows: list[tuple[str, Any]],
    *,
    border_style: str = "cyan",
    subtitle: str | None = None,
    panel_box=box.DOUBLE,
) -> Panel:
    """Build a compact panel containing aligned key/value rows."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style=f"bold {border_style}", no_wrap=True)
    grid.add_column()
    for label, value in rows:
        grid.add_row(label, Text(_display(value)))
    return Panel.fit(
        grid,
        title=Text(title, style="bold"),
        subtitle=subtitle,
        border_style=border_style,
        box=panel_box,
        padding=(1, 2),
    )

# ==================================
# HHT CRITERIA UTILS
# ==================================

# HHT VCEP criteria — used when disease is HHT (or None for backward compatibility)
HHT_CRITERIA = ["PM2_SUPPORTING", "PP3", "BP4", "BA1", "BP7", "BS1", "PVS1", "PM4", "PM1", "PS1", "PM5", "PS4", "BS3", "PS3"]

# ACMG criteria — all automatable/partially-automatable entries in ACMG_CRITERIA_DB
# (deferred entries are filtered out by plan_agent, but excluded here too for clarity)
ACMG_CRITERIA = [k for k in ACMG_CRITERIA_DB if k != "SCORING"]

def get_criteria_for_disease(disease: str) -> list[str]:
    """Returns the correct criteria list based on whether disease has a VCEP spec."""
    if disease is None or is_vcep_disease(disease):
        return HHT_CRITERIA
    return ACMG_CRITERIA

def filter_criteria_by_variant_type(criteria: list[str], variant_type: str, disease: str = None) -> list[str]:
    """
    Removes criteria that explicitly restrict which variant types they apply to
    when the variant type doesn't match.

    A criterion with no ``variant_types`` field in the guideline registry passes through unchanged.
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
        skipped_table = Table(
            "Criterion",
            "Applicable variant types",
            box=box.SIMPLE,
            header_style="bold yellow",
            show_edge=False,
        )
        for criterion, allowed in skipped:
            skipped_table.add_row(Text(criterion), Text(", ".join(map(str, allowed))))
        console.print(Panel(
            skipped_table,
            title=f"[bold yellow]Skipped {len(skipped)} inapplicable criteria[/bold yellow]",
            subtitle=Text(reason),
            border_style="yellow",
            box=box.ROUNDED,
        ))

    return filtered

# ==================================
# Type aliases for LangGraph states
# ==================================
ToolResults: TypeAlias = dict[str, dict[str, Any]]
Tasks: TypeAlias = dict[str, list[dict[str, str]]]
CriterionResults: TypeAlias = dict[str, dict[str, Any]]

# ==================================
# StateGraph reducers
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
# Helper Function for Printing Results After Each Phase
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


def _print_phase_summary(
    phase_number: int,
    criteria: list[str],
    results: list[dict[str, Any]],
) -> None:
    """Render a Rich summary table for a completed evaluation phase."""
    table = Table(
        box=box.MINIMAL_DOUBLE_HEAD,
        header_style="bold cyan",
        expand=True,
        show_edge=False,
        show_lines=True,
        padding=(0, 1),
    )
    table.add_column("Criterion", style="bold", no_wrap=True)
    table.add_column("Result", no_wrap=True)
    table.add_column("Evidence", ratio=2)
    table.add_column("Reasoning", ratio=3)
    table.add_column(
        "Tool",
        style="cyan",
        min_width=20,
        max_width=24,
        overflow="fold",
    )

    for result in results:
        status = result.get("status")
        if status == "error":
            result_text = Text("Error", style="bold red")
            evidence = result.get("error", "Unknown error")
        elif status == "skipped":
            result_text = Text("Skipped", style="bold yellow")
            evidence = result.get("reason", "No reason provided")
        elif result.get("applies") is True:
            result_text = Text("Applied", style="bold green")
            evidence = result.get("evidence")
        elif result.get("applies") is False:
            result_text = Text("Not applied", style="bold bright_black")
            evidence = result.get("evidence")
        else:
            result_text = Text("Unknown", style="bold yellow")
            evidence = result.get("evidence")

        table.add_row(
            Text(_display(result.get("criterion", "Unknown"))),
            result_text,
            Text(_display(evidence)),
            Text(_display(result.get("reasoning"))),
            Text(_display(result.get("tool_used"))),
        )

    checked = ", ".join(_display(criterion) for criterion in criteria) or "None"
    console.print(Panel(
        table,
        title=Text(f"Phase {phase_number} complete", style="bold green"),
        subtitle=Text(f"Checked: {checked}", style="dim"),
        border_style="green",
        box=box.ROUNDED,
        padding=(0, 1),
    ))

# ==================================
# LangGraph Nodes
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
    
    _print_phase_summary(1, phase1_criterions, phase1_results)
        
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
    
    _print_phase_summary(2, phase2_criterions, phase2_results)

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
    
    _print_phase_summary(3, phase3_criterions, phase3_results)
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
    
    _print_phase_summary(4, phase4_criterions, phase4_results)
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
    guideline_entry = query(criterion, disease=disease)
    requires_applied = (guideline_entry or {}).get("requires_applied", [])
    blocked_by      = (guideline_entry or {}).get("blocked_by", [])
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
        console.print(Panel.fit(
            Text.assemble(
                (f"{criterion}\n", "bold yellow"),
                (skipped_reason, "white"),
            ),
            title=Text("Criterion skipped", style="bold yellow"),
            border_style="yellow",
            box=box.ROUNDED,
        ))
        skipped_entry = {
            "criterion": criterion,
            "status": "skipped",
            "reason": skipped_reason,
        }
        
        return {"criterion_results": {criterion.upper().replace("-", "_"): skipped_entry}}        

    # ── DEBUG AGENT (runs Task agent internally) ──
    # console.print("[1/3] DEBUG AGENT — running Task agent and checking for technical errors")
    debug_output, tool_cache_update = run_debug(task, gene_symbol = gene_symbol, tool_results = tool_results)

    if debug_output.get("status") == "error":
        return {
            "criterion_results": {criterion.upper().replace("-", "_"): debug_output},
            "tool_results": tool_cache_update
        }  

    # ── JUDGE AGENT ───────────────────────
    judge_output, tool_cache_update = run_judge(task, tool_results, debug_output, gene_symbol=gene_symbol)

    if judge_output.get("status") == "error":
        return {
            "criterion_results": {criterion.upper().replace("-", "_"): judge_output},
            "tool_results": tool_cache_update
            }  

    # ── CHECK AGENT ───────────────────────
    final_output = run_check(judge_output)

    return {
        "criterion_results": {criterion.upper().replace("-", "_"): final_output},
        "tool_results": tool_cache_update
        } 

# ==================================
# LangGraph Routers
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
# Invoking the state graph
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
    # ── INITIALIZE THE PIPELINE ─────────────────
    console.print()
    console.print(_key_value_panel(
        "Variant Classification Pipeline",
        [
            ("Variant", variant),
            ("Disease", disease),
        ],
        subtitle="Starting classification",
        border_style="cyan",
        panel_box=box.DOUBLE,
    ))

    # ── VARIANT TYPE DETECTION ─────────────────
    console.print()
    _status_message("Detecting variant type", "Ensembl VEP", style="cyan", symbol="◆")
    vep_result = annotate_variant(variant)

    gene_symbol = None
    if "error" in vep_result:
        _status_message(
            "Could not determine variant type",
            vep_result["error"],
            style="yellow",
            symbol="⚠",
        )
        variant_type = None
        # Fallback: get gene_symbol from NCBI when VEP fails
        if variant.startswith("NM_") and ":" in variant:
            transcript = variant.split(":")[0]
            gene_symbol = get_gene_symbol_from_transcript(transcript)
            if gene_symbol:
                _status_message("Gene detected via NCBI fallback", gene_symbol, style="green", symbol="✓")
    else:
        variant_type = vep_result["variant_type"]
        gene_symbol = vep_result.get("gene_symbol")
        if gene_symbol:
            _status_message("Gene detected via VEP", gene_symbol, style="green", symbol="✓")
        consequence = vep_result["variant_consequence"]
        _status_message(
            "Variant type detected",
            f"{variant_type} ({consequence})",
            style="green",
            symbol="✓",
        )

    # ── CRITERIA SELECTION & FILTERING ────────
    # Always run filtering — when variant_type is None (VEP failed), conservatively
    # exclude criteria with variant_type restrictions since we can't verify the type.
    base_criteria = get_criteria_for_disease(disease)
    active_criteria = filter_criteria_by_variant_type(base_criteria, variant_type, disease=disease)

    # ── PLAN AGENT ────────────────────────────
    tasks = run_plan(variant, disease, active_criteria,gene_symbol=gene_symbol)

    if not tasks:
        console.print(Panel.fit(
            "The plan agent returned no criterion tasks.",
            title=Text("Pipeline stopped", style="bold yellow"),
            border_style="yellow",
            box=box.ROUNDED,
        ))
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
    console.print()
    _status_message("Running classification scoring", scoring_label, style="magenta", symbol="◆")
    scoring_result = classify(results_dict, disease=disease)
    console.print(_key_value_panel(
        "Scoring complete",
        [
            ("Classification", scoring_result["classification"]),
            ("Rule matched", scoring_result["rule_matched"]),
        ],
        border_style="magenta",
        panel_box=box.ROUNDED,
    ))

    return results_list, scoring_result


def print_report(variant: str, disease: str, results: list[dict], scoring_result: dict | None = None) -> None:
    """
    Prints a human-readable classification report to the terminal.
    """
    console.print()
    console.print(_key_value_panel(
        "Classification Report",
        [
            ("Variant", variant),
            ("Disease", disease),
            ("Generated", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ],
        border_style="bright_blue",
        panel_box=box.DOUBLE,
    ))

    # ── FINAL CLASSIFICATION ──────────────────────────────────────────────────
    if scoring_result:
        classification = scoring_result.get("classification", "Unknown")
        rule = scoring_result.get("rule_matched", "—")
        buckets = scoring_result.get("buckets", {})
        bucket_detail = scoring_result.get("bucket_detail", {})

        classification_styles = {
            "Pathogenic": ("bold red", "red"),
            "Likely Pathogenic": ("bold yellow", "yellow"),
            "Likely Benign": ("bold cyan", "cyan"),
            "Benign": ("bold blue", "blue"),
        }
        classification_style, border_style = classification_styles.get(
            classification,
            ("bold white", "white"),
        )
        classification_grid = Table.grid(padding=(0, 2))
        classification_grid.add_column(style="bold", no_wrap=True)
        classification_grid.add_column()
        classification_grid.add_row(
            "Classification",
            Text(_display(classification), style=classification_style),
        )
        classification_grid.add_row("Rule matched", Text(_display(rule)))
        console.print(Panel.fit(
            classification_grid,
            title=Text("Final Classification", style=classification_style),
            border_style=border_style,
            box=box.HEAVY,
            padding=(1, 2),
        ))

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
            bucket_table = Table(
                "Evidence strength",
                "Count",
                "Criteria",
                box=box.SIMPLE_HEAVY,
                header_style="bold magenta",
                show_edge=False,
            )
            for k, v in nonempty.items():
                criteria_in_bucket = [c for c, b in bucket_detail.items()
                                      if b == {
                                          "vs": "very_strong", "s": "strong",
                                          "m": "moderate", "sup": "supporting",
                                          "ba": "benign_stand_alone", "bs": "benign_strong",
                                          "bsup": "benign_supporting",
                                      }.get(k)]
                bucket_table.add_row(
                    Text(bucket_labels.get(k, k)),
                    Text(str(v), style="bold"),
                    Text(", ".join(criteria_in_bucket) or "—"),
                )
            console.print(Panel(
                bucket_table,
                title=Text("Strength bucket counts", style="bold magenta"),
                border_style="magenta",
                box=box.ROUNDED,
            ))

        warning_lines = [
            str(note) for note in scoring_result.get("incompatibility_notes", [])
        ]
        warning_lines.extend(
            f"Unrecognised criterion skipped in scoring: {criterion}"
            for criterion in scoring_result.get("unrecognised_criteria", [])
        )
        if warning_lines:
            warnings = Text()
            for index, warning in enumerate(warning_lines):
                if index:
                    warnings.append("\n")
                warnings.append("⚠ ", style="bold yellow")
                warnings.append(warning)
            console.print(Panel(
                warnings,
                title=Text("Scoring notes", style="bold yellow"),
                border_style="yellow",
                box=box.ROUNDED,
            ))

    if not results:
        console.print(Panel.fit(
            "No criterion results are available.",
            title=Text("No results", style="bold yellow"),
            border_style="yellow",
            box=box.ROUNDED,
        ))
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
    applied_table = Table(
        box=box.MINIMAL_DOUBLE_HEAD,
        header_style="bold green",
        expand=True,
        show_edge=False,
        show_lines=True,
        padding=(0, 1),
    )
    applied_table.add_column("Criterion", style="bold green", no_wrap=True)
    applied_table.add_column("Evidence", ratio=2)
    applied_table.add_column("Reasoning", ratio=3)
    applied_table.add_column(
        "Tool / input",
        min_width=20,
        max_width=28,
        overflow="fold",
    )
    for result in applied:
        tool = Text(_display(result.get("tool_used")), style="bold cyan")
        tool.append("\n")
        tool.append(_display(result.get("tool_input")), style="dim")
        applied_table.add_row(
            Text(f"✓ {_display(result.get('criterion'))}", style="bold green"),
            Text(_display(result.get("evidence"))),
            Text(_display(result.get("reasoning"))),
            tool,
        )
    if not applied:
        applied_table.add_row(Text("None", style="dim"), "", "", "")
    console.print(Panel(
        applied_table,
        title=Text(f"Criteria Applied ({len(applied)})", style="bold green"),
        border_style="green",
        box=box.ROUNDED,
    ))

    # ── CRITERIA THAT DO NOT APPLY ────────────
    not_applied_table = Table(
        "Criterion",
        "Evidence",
        "Reasoning",
        box=box.MINIMAL_DOUBLE_HEAD,
        header_style="bold bright_black",
        expand=True,
        show_edge=False,
        show_lines=True,
        padding=(0, 1),
    )
    for result in not_applied:
        not_applied_table.add_row(
            Text(f"✗ {_display(result.get('criterion'))}", style="bold bright_black"),
            Text(_display(result.get("evidence"))),
            Text(_display(result.get("reasoning"))),
        )
    if not not_applied:
        not_applied_table.add_row(Text("None", style="dim"), "", "")
    console.print(Panel(
        not_applied_table,
        title=Text(f"Criteria Not Applied ({len(not_applied)})", style="bold bright_black"),
        border_style="bright_black",
        box=box.ROUNDED,
    ))

    # ── SKIPPED CRITERIA ──────────────────────
    if skipped:
        skipped_table = Table(
            "Criterion",
            "Reason",
            box=box.SIMPLE,
            header_style="bold yellow",
            expand=True,
            show_edge=False,
        )
        for result in skipped:
            skipped_table.add_row(
                Text(f"– {_display(result.get('criterion'))}", style="bold yellow"),
                Text(_display(result.get("reason"))),
            )
        console.print(Panel(
            skipped_table,
            title=Text(f"Skipped Criteria ({len(skipped)})", style="bold yellow"),
            border_style="yellow",
            box=box.ROUNDED,
        ))

    # ── FAILED CRITERIA ───────────────────────
    if failed:
        failed_table = Table(
            "Criterion",
            "Error",
            box=box.SIMPLE,
            header_style="bold red",
            expand=True,
            show_edge=False,
        )
        for result in failed:
            failed_table.add_row(
                Text(f"! {_display(result.get('criterion'))}", style="bold red"),
                Text(_display(result.get("error"))),
            )
        console.print(Panel(
            failed_table,
            title=Text(f"Failed Criteria ({len(failed)})", style="bold red"),
            border_style="red",
            box=box.ROUNDED,
        ))


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

    Single-variant mode uses a timestamped filename (preserves history).
    Batch mode (``timestamped=False``) uses a deterministic filename
    (``<safe_variant>_<disease>.json``) so re-running against the same folder
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
# Batch mode (CSV input, variants run SEQUENTIALLY)
# ==================================

def run_batch(
    csv_path: str,
    output_dir: str | None = None,
    disease_default: str | None = None,
    variant_col: str = "hgvs_cdna",
    disease_col: str = "condition",
) -> str:
    """
    Runs the full pipeline over every variant in a CSV, ONE VARIANT AT A TIME.

    Variants are processed sequentially; criterion-level parallelism still
    happens inside each variant via the existing LangGraph fan-out. One JSON
    file is written per variant into a per-run batch folder, plus a
    batch_summary.json.

    - Per-variant errors are isolated: a failure becomes an error file/summary
      row and the batch continues with the next variant.
    - Resumable: pass an existing output_dir to skip variants already written.

    Returns the batch output folder path.
    """
    import csv

    # One folder per batch run (unless an existing one is passed in, enabling resume).
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
    console.print()
    console.print(_key_value_panel(
        "Batch Classification",
        [
            ("Variants", total),
            ("Input CSV", csv_path),
            ("Output folder", output_dir),
            ("Execution", "Variants sequential; criteria parallel"),
        ],
        subtitle="Starting batch",
        border_style="cyan",
        panel_box=box.DOUBLE,
    ))

    summary = []
    for i, (variant, disease) in enumerate(rows, start=1):
        safe = _safe_variant_name(variant)
        target = os.path.join(output_dir, f"{safe}_{disease}.json")

        if os.path.exists(target):
            _status_message(
                f"[{i}/{total}] Skipped existing result",
                variant,
                style="yellow",
                symbol="↷",
            )
            summary.append({"variant": variant, "disease": disease,
                            "status": "skipped_existing", "file": target})
        else:
            try:
                results, scoring_result = run_pipeline(variant, disease)
                path = save_results(variant, disease, results, scoring_result,
                                    output_dir=output_dir, timestamped=False)
                res = {
                    "variant": variant,
                    "disease": disease,
                    "status": "ok",
                    "classification": (scoring_result or {}).get("classification"),
                    "rule_matched": (scoring_result or {}).get("rule_matched"),
                    "file": path,
                }
                _status_message(
                    f"[{i}/{total}] Completed",
                    f"{variant} → {res['classification']}",
                    style="green",
                    symbol="✓",
                )
            except (Exception, SystemExit) as e:  # isolate: one variant must not kill the batch
                # Catch SystemExit too: a stray sys.exit() inside a tool (it runs
                # in a LangGraph worker thread) would otherwise bypass `except
                # Exception` and silently terminate the whole batch. KeyboardInterrupt
                # (BaseException, not caught here) still stops the run as expected.
                res = {
                    "variant": variant,
                    "disease": disease,
                    "status": "error",
                    "error": f"{type(e).__name__}: {e}",
                }
                errfile = os.path.join(output_dir, f"{safe}_{disease}.error.json")
                with open(errfile, "w") as fh:
                    json.dump(res, fh, indent=2)
                res["file"] = errfile
                _status_message(
                    f"[{i}/{total}] Failed",
                    f"{variant} → {res['error']}",
                    style="red",
                    symbol="✗",
                )
            summary.append(res)

        # Write summary incrementally so an interruption doesn't lose progress.
        with open(os.path.join(output_dir, "batch_summary.json"), "w") as fh:
            json.dump({
                "csv": csv_path,
                "total": total,
                "completed": i,
                "results": summary,
            }, fh, indent=2)

    ok = sum(1 for r in summary if r["status"] == "ok")
    errs = sum(1 for r in summary if r["status"] == "error")
    skipped = sum(1 for r in summary if r["status"] == "skipped_existing")
    console.print()
    console.print(_key_value_panel(
        "Batch Complete",
        [
            ("Successful", ok),
            ("Errors", errs),
            ("Skipped", skipped),
            ("Output folder", output_dir),
        ],
        border_style="green" if errs == 0 else "yellow",
        panel_box=box.DOUBLE,
    ))
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
        help="Path to a CSV of variants to run as a batch (variants run sequentially). "
             "Use this OR --variant."
    )
    parser.add_argument(
        "--disease",
        type=str,
        default=None,
        help="Disease name (e.g. HHT). Required for --variant; for --csv it is the fallback "
             "when a row has no disease column."
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

    console.print(Panel.fit(
        Text(_display(filepath)),
        title=Text("Results saved", style="bold green"),
        border_style="green",
        box=box.ROUNDED,
    ))


if __name__ == "__main__":
    main()
