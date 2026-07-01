import argparse
import csv
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from agents.plan_agent import run_plan
from agents.debug_agent import run_debug
from agents.judge_agent import run_judge
from agents.check_agent import run_check
from tools.vep import annotate_variant
from tools.scoring import classify
from data.planrag import query, is_vcep_disease, ACMG_PLANRAG_DB
from typing import Any, TypeAlias
from pipeline_logging import log

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
        # else: criterion doesn't apply to this variant_type — silently
        # excluded. It just won't show up in the "variant | criterion |
        # applies=" console lines or the output JSON for this variant.

    return filtered

# ==================================
# Type aliases
# ==================================
ToolResults: TypeAlias = dict[str, dict[str, Any]]
Tasks: TypeAlias = dict[str, list[dict[str, str]]]
CriterionResults: TypeAlias = dict[str, dict[str, Any]]

# ==================================
# Criterion processing
# ==================================
# Criteria used to run in parallel per phase via a LangGraph StateGraph with
# Send-based fan-out. That's been removed — criteria within a variant now
# run strictly sequentially, phase by phase, in a plain loop. The only
# parallelism left is across variants (see run_pipeline_batch below).

def process_criterion(
        variant: str,
        task: dict[str, str],
        disease: str,
        previous_results: CriterionResults,
        tool_results: ToolResults,
        gene_symbol: str | None,
) -> tuple[dict[str, Any], ToolResults]:
    """
    Executes full evaluation pipeline for a single ACMG/VCEP criterion.

    Performs dependency checking, runs debug → judge → check agents sequentially,
    and returns the criterion's result entry plus any tool_results to merge in.
    Skips execution if prerequisites are not satisfied.

    Prints exactly one console line for this criterion when it finishes:
        <variant> | <criterion> | applies=<True/False/None>
    Full reasoning/evidence/tool detail is not printed — it's still in the
    returned result dict, which pipeline.py writes to the batch JSON output.
    """
    criterion = task["criterion"]

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
        skipped_entry = {
            "criterion": criterion,
            "status": "skipped",
            "reason": skipped_reason,
        }
        log(f"{variant} | {criterion} | applies=None (skipped)")
        return skipped_entry, {}

    # ── DEBUG AGENT (runs Task agent internally) ──
    debug_output, tool_cache_update = run_debug(task, gene_symbol=gene_symbol, tool_results=tool_results)

    if debug_output.get("status") == "error":
        log(f"{variant} | {criterion} | applies=None (error)")
        return debug_output, tool_cache_update

    # ── JUDGE AGENT ───────────────────────
    judge_output, tool_cache_update = run_judge(task, tool_results, debug_output, gene_symbol=gene_symbol)

    if judge_output.get("status") == "error":
        log(f"{variant} | {criterion} | applies=None (error)")
        return judge_output, tool_cache_update

    # ── CHECK AGENT ───────────────────────
    final_output = run_check(judge_output)

    log(f"{variant} | {criterion} | applies={final_output.get('applies')}")
    return final_output, tool_cache_update


def process_criterions_sequentially(
        variant: str,
        tasks: Tasks,
        variant_type: str | None,
        disease: str,
        gene_symbol: str | None
) -> dict[str, Any]:
    """
    Runs ACMG/VCEP criterion evaluation sequentially, phase by phase.

    Each phase's criteria are processed one at a time, in order; results and
    tool_results accumulate as we go, so a phase-N criterion can rely on
    phase-(N-1) results (requires_applied/blocked_by) the same way the old
    LangGraph fan-out/fan-in did — a phase never starts before the previous
    one has fully finished.

    Args:
        variant: Variant string, used only to label console output.
        tasks: Phased criterion tasks (phase1..phase4).
        variant_type: Variant consequence type (may be None).
        disease: Target disease context.
        gene_symbol: Resolved gene symbol (may be None).
    Returns:
        dict with "criterion_results" and "tool_results", matching the shape
        the old LangGraph state produced.
    """
    tool_results: ToolResults = {}
    criterion_results: CriterionResults = {}

    for phase_num in (1, 2, 3, 4):
        phase_key = f"phase{phase_num}"
        phase_tasks = tasks.get(phase_key, [])
        if not phase_tasks:
            continue

        for task in phase_tasks:
            criterion = task["criterion"]
            result, tool_cache_update = process_criterion(
                variant=variant,
                task=task,
                disease=disease,
                previous_results=criterion_results,
                tool_results=tool_results,
                gene_symbol=gene_symbol,
            )
            criterion_results[criterion.upper().replace("-", "_")] = result
            tool_results.update(tool_cache_update)

    return {"criterion_results": criterion_results, "tool_results": tool_results}

def run_pipeline(variant: str, disease: str) -> tuple[list[Any], dict]:
    """
    Main pipeline entry point.
    Runs all agents in sequence for each criterion.
    Returns a list of validated, formatted task outputs.
    """
    # ── VARIANT TYPE DETECTION ─────────────────
    vep_result = annotate_variant(variant)

    gene_symbol = None
    if "error" in vep_result:
        variant_type = None
    else:
        variant_type = vep_result["variant_type"]
        gene_symbol = vep_result.get("gene_symbol")

    # ── CRITERIA SELECTION & FILTERING ────────
    base_criteria = get_criteria_for_disease(disease)
    active_criteria = base_criteria
    if variant_type is not None:
        active_criteria = filter_criteria_by_variant_type(base_criteria, variant_type, disease=disease)

    # ── PLAN AGENT ────────────────────────────
    tasks = run_plan(variant, disease, active_criteria,gene_symbol=gene_symbol)

    if not any(tasks.values()):
        log(f"{variant} | no tasks generated by plan agent — skipping")
        return [], {}

    # ── RUN CRITERIA SEQUENTIALLY ────────────────────────────
    # process_criterion() prints one "variant | criterion | applies=..." line
    # per criterion as it finishes — that's the only per-criterion console
    # output. Full reasoning/evidence stays in the returned results, which
    # save_results() below (or run_pipeline_batch's caller) writes to JSON.
    results = process_criterions_sequentially(
        variant=variant,
        tasks=tasks,
        variant_type=variant_type,
        disease=disease,
        gene_symbol=gene_symbol
    )

    results_list = list(results["criterion_results"].values())
    results_dict = results["criterion_results"]

    # ── SCORING ───────────────────────────────────────────────────────────────
    scoring_result = classify(results_dict, disease=disease)
    log(f"{variant} | RESULT | classification={scoring_result['classification']} rule={scoring_result['rule_matched']}")

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


def save_results(
        variant: str,
        disease: str,
        results: list[dict],
        scoring_result: dict = None,
        output_dir: str = "outputs",
        error: str = None,
) -> str:
    """
    Saves full JSON results to a timestamped output file.
    output_dir defaults to "outputs" for single-variant runs; batch runs pass
    a per-batch subfolder (see run_pipeline_batch) so files don't all land
    flat in outputs/.
    error is set only when the variant's pipeline run raised an exception —
    still writes a file so every requested variant produces exactly one
    output record, success or failure.

    The timestamp includes microseconds and a short random suffix so two
    variants finishing in the same wall-clock second — e.g. a duplicate
    (variant, disease) pair in a batch CSV, or a rerun landing in the same
    output_dir — never collide on the same filename and silently overwrite
    each other.
    Returns the file path.
    """
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    unique_suffix = uuid.uuid4().hex[:8]
    safe_variant = variant.replace(":", "_").replace(">", "_").replace(".", "_")
    filename = f"{output_dir}/{safe_variant}_{disease}_{timestamp}_{unique_suffix}.json"

    output = {
        "variant": variant,
        "disease": disease,
        "timestamp": timestamp,
        "classification": scoring_result.get("classification") if scoring_result else None,
        "rule_matched":   scoring_result.get("rule_matched")   if scoring_result else None,
        "scoring":        scoring_result,
        "results": results,
        "error": error,
    }

    with open(filename, "w") as f:
        # default=str: if anything non-JSON-native (e.g. a set, dataclass
        # instance, or other object) ever ends up embedded in results/scoring
        # from an agent or tool, fall back to str() for that value instead of
        # raising and losing the whole record. Better a stringified field
        # than a batch run that silently dies mid-way with no output at all.
        json.dump(output, f, indent=2, default=str)

    return filename


def load_variants_from_csv(csv_path: str) -> list[tuple[str, str]]:
    """
    Reads (variant, disease) pairs from a batch-evaluation CSV like
    hht_variants_eval.csv. Expects an "hgvs_cdna" column for the variant and
    a "condition" column for the disease. Rows with no hgvs_cdna are skipped
    (e.g. large deletions/duplications not expressed as HGVS in this dataset).
    """
    pairs = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            variant = (row.get("hgvs_cdna") or "").strip()
            disease = (row.get("condition") or "").strip()
            if not variant:
                continue
            pairs.append((variant, disease))
    return pairs


def run_pipeline_batch(
        variant_disease_pairs: list[tuple[str, str]],
        max_concurrency: int = 3,
) -> str:
    """
    Runs run_pipeline() for each (variant, disease) pair concurrently, bounded
    by max_concurrency. Criterion evaluation within each variant's pipeline is
    sequential (see process_criterions_sequentially) — this is the only layer
    of parallelism, across variants.

    Every console line printed (see process_criterion() in this file) embeds
    the variant string directly, so concurrent variants' output stays
    distinguishable even without any thread-tagging — log() just holds a
    shared lock so two threads' lines can't get interleaved into a garbled one.

    One variant failing (exception anywhere in its pipeline) does not stop
    the rest of the batch — the error is caught, logged, and still written to
    a JSON output file so every variant produces exactly one result record.

    All output files for this run go into a single timestamped subfolder
    under outputs/, e.g. outputs/batch_20260701_143000/, instead of flat in
    outputs/.

    Returns the batch output directory path.
    """
    batch_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_dir = f"outputs/batch_{batch_timestamp}"
    os.makedirs(batch_dir, exist_ok=True)

    total = len(variant_disease_pairs)
    log("="*60)
    log(f"BATCH: Starting {total} variant(s), max_concurrency={max_concurrency}")
    log(f"BATCH: Output folder → {batch_dir}")
    log("="*60)

    def _run_one(variant: str, disease: str) -> tuple[str, str, list, dict, str]:
        try:
            results, scoring_result = run_pipeline(variant, disease)
            return variant, disease, results, scoring_result, None
        except Exception as e:
            return variant, disease, [], {}, str(e)

    completed = 0
    with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
        futures = [
            executor.submit(_run_one, variant, disease)
            for variant, disease in variant_disease_pairs
        ]

        for future in as_completed(futures):
            completed += 1
            variant, disease = "unknown", "unknown"
            try:
                variant, disease, results, scoring_result, error = future.result()

                filepath = save_results(
                    variant, disease, results, scoring_result,
                    output_dir=batch_dir, error=error,
                )

                if error:
                    log(f"BATCH [{completed}/{total}] ✗ {variant} ({disease}) — ERROR: {error}")
                else:
                    classification = scoring_result.get("classification", "Unknown") if scoring_result else "Unknown"
                    log(f"BATCH [{completed}/{total}] ✓ {variant} ({disease}) → {classification}  [{filepath}]")
            except Exception as e:
                # Anything unexpected here (e.g. future.result() itself
                # raising, or save_results() failing) must not kill the rest
                # of the batch — log it clearly and keep going so every other
                # variant still gets processed and BATCH COMPLETE still prints.
                log(f"BATCH [{completed}/{total}] ✗ {variant} ({disease}) — UNEXPECTED ERROR: {e}")

    log("="*60)
    log(f"BATCH COMPLETE: {completed}/{total} variant(s) processed")
    log(f"Results saved to: {batch_dir}/")
    log("="*60)

    return batch_dir


def main():
    parser = argparse.ArgumentParser(
        description="LLM-based multi-agent pipeline for ACMG variant classification"
    )
    parser.add_argument(
        "--variant",
        type=str,
        default=None,
        help="Variant in HGVS or gnomAD format (e.g. NM_000020.3:c.557G>T or 12-51914005-G-T). "
             "Required unless --variants-csv is given."
    )
    parser.add_argument(
        "--disease",
        type=str,
        default=None,
        help="Disease name (e.g. HHT). Required unless --variants-csv is given."
    )
    parser.add_argument(
        "--variants-csv",
        type=str,
        default=None,
        help="Path to a CSV with 'hgvs_cdna' and 'condition' columns (e.g. hht_variants_eval.csv) "
             "to run many variants in parallel instead of a single --variant/--disease pair."
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=3,
        help="Max number of variants to run at once in batch mode (--variants-csv). "
             "Ignored for single-variant runs. Default: 3."
    )

    args = parser.parse_args()

    if args.variants_csv:
        pairs = load_variants_from_csv(args.variants_csv)
        if not pairs:
            parser.error(f"No variants found in {args.variants_csv} (expected an 'hgvs_cdna' column)")
        run_pipeline_batch(pairs, max_concurrency=args.max_concurrency)
        return

    if not args.variant or not args.disease:
        parser.error("Either --variants-csv, or both --variant and --disease, must be provided.")

    results, scoring_result = run_pipeline(args.variant, args.disease)
    print_report(args.variant, args.disease, results, scoring_result)
    filepath = save_results(args.variant, args.disease, results, scoring_result)

    print(f"Full results saved to: {filepath}\n")


if __name__ == "__main__":
    main()