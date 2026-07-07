# QUESTION3:
# What is the contribution of each agent in the multi-agent framework?
# Ablation Study

# Ablation conditions:
#   full      - Plan → Debug(Task+retry) → Judge → Check  [full pipeline]
#   no_debug  - Plan → Task(no retry)    → Judge → Check  [skip Debug agent]
#   no_judge  - Plan → Debug(Task+retry) → Check          [skip Judge agent]
#   task_only - Plan → Task(no retry)    → Check          [skip Debug + Judge]

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.task_agent import run_task
from agents.check_agent import run_check
from pipeline import (
    _safe_variant_name,
    run_pipeline,
    PerCriterionState,
)
from data.planrag import query

LABELS = ["B", "LB", "VUS", "LP", "P"]

CLASSIFICATION_MAPPING = {
    "b": "B", "lb": "LB", "vus": "VUS", "lp": "LP", "p": "P",
    "benign": "B",
    "likely benign": "LB",
    "variant of uncertain significance (vus)": "VUS",
    "likely pathogenic": "LP",
    "pathogenic": "P",
    "error": "ERROR",
}

ABLATION_MODES = ["full", "no_debug", "no_judge", "task_only"]


# ── Ablation version of process_criterion ─────────────────────────────────────

def process_criterion_ablation(state: PerCriterionState, mode: str):
    """
    Runs a single criterion evaluation under a given ablation mode.

    Modes:
      full      - normal pipeline (debug → judge → check)
      no_debug  - task directly (no retry) → judge → check
      no_judge  - debug (task + retry) → check
      task_only - task directly (no retry) → check
    """
    from agents.debug_agent import run_debug
    from agents.judge_agent import run_judge

    task = state["task"]
    criterion = task["criterion"]
    disease = state["disease"]
    previous_results = state["previous_results"]
    tool_results = state["tool_results"]
    gene_symbol = state["gene_symbol"]

    # dependency / blocker check
    rag_entry = query(criterion, disease=disease)
    requires_applied = (rag_entry or {}).get("requires_applied", [])
    blocked_by = (rag_entry or {}).get("blocked_by", [])
    skipped_reason = None

    for dep in requires_applied:
        dep_key = dep.upper().replace("-", "_").replace(" ", "_")
        dep_result = previous_results.get(dep_key)
        if dep_result is None:
            skipped_reason = f"{dep} has not been evaluated"
            break
        if not dep_result.get("applies"):
            skipped_reason = f"{dep} did not apply — {criterion} requires it"
            break

    if not skipped_reason:
        for blocker in blocked_by:
            blocker_key = blocker.upper().replace("-", "_").replace(" ", "_")
            blocker_result = previous_results.get(blocker_key)
            if blocker_result and blocker_result.get("applies") is True:
                skipped_reason = f"{blocker} applied — {criterion} excluded"
                break

    if skipped_reason:
        skipped_entry = {"criterion": criterion, "status": "skipped", "reason": skipped_reason}
        return {"criterion_results": {criterion.upper().replace("-", "_"): skipped_entry}}

    tool_cache_update = {}

    if mode in ("full", "no_judge"):
        intermediate, tool_cache_update = run_debug(task, gene_symbol=gene_symbol, tool_results=tool_results)
    else:
        intermediate, tool_cache_update = run_task(task, tool_results=tool_results, gene_symbol=gene_symbol)

    if intermediate.get("status") == "error":
        return {
            "criterion_results": {criterion.upper().replace("-", "_"): intermediate},
            "tool_results": tool_cache_update,
        }

    if mode in ("full", "no_debug"):
        final_intermediate, tool_cache_update2 = run_judge(task, tool_results, intermediate)
        tool_cache_update.update(tool_cache_update2)
        if final_intermediate.get("status") == "error":
            return {
                "criterion_results": {criterion.upper().replace("-", "_"): final_intermediate},
                "tool_results": tool_cache_update,
            }
        intermediate = final_intermediate

    final_output = run_check(intermediate)
    return {
        "criterion_results": {criterion.upper().replace("-", "_"): final_output},
        "tool_results": tool_cache_update,
    }


# ── Run pipeline with a given ablation mode ───────────────────────────────────

def run_pipeline_ablation(variant: str, disease: str, mode: str):
    import pipeline as pipeline_module

    def patched_process_criterion(state):
        return process_criterion_ablation(state, mode=mode)

    with patch.object(pipeline_module, "process_criterion", patched_process_criterion):
        results_list, scoring_result = run_pipeline(variant, disease)

    return scoring_result


# ── Load data ─────────────────────────────────────────────────────────────────

def load_gold_df(gold_csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(gold_csv_path)
    df = df.rename(columns={
        "hgvs_cdna": "variant",
        "condition": "disease",
        "gt_classification": "gold_classification",
        "gt_classification_short": "gold_classification_short",
    })
    return df


def normalize(raw_label: str) -> str:
    if raw_label is None:
        return "ERROR"
    label = str(raw_label).strip().lower()
    return CLASSIFICATION_MAPPING.get(label, "ERROR")


# ── Metrics ───────────────────────────────────────────────────────────────────

def compute_metrics(y_true, y_pred):
    valid = [(t, p) for t, p in zip(y_true, y_pred) if p != "ERROR"]
    num_errors = len(y_true) - len(valid)
    if not valid:
        return None, num_errors
    yt = [v[0] for v in valid]
    yp = [v[1] for v in valid]
    metrics = {
        "accuracy": accuracy_score(yt, yp),
        "macro_precision": precision_score(yt, yp, labels=LABELS, average="macro", zero_division=0),
        "macro_recall": recall_score(yt, yp, labels=LABELS, average="macro", zero_division=0),
        "macro_f1": f1_score(yt, yp, labels=LABELS, average="macro", zero_division=0),
        "confusion_matrix": confusion_matrix(yt, yp, labels=LABELS).tolist(),
        "classification_report": classification_report(yt, yp, labels=LABELS, zero_division=0, output_dict=True),
        "num_errors": num_errors,
        "num_evaluated": len(valid),
    }
    return metrics, num_errors


# ── Main evaluation loop ──────────────────────────────────────────────────────

def run_question3_evaluation(gold_csv_path: str, variant_ids: list, output_dir: str):
    gold_df = load_gold_df(gold_csv_path)

    if variant_ids:
        gold_df = gold_df[gold_df["variation_id"].isin(variant_ids)].reset_index(drop=True)

    os.makedirs(output_dir, exist_ok=True)

    all_results = {}

    for mode in ABLATION_MODES:
        print(f"\n{'='*60}")
        print(f"ABLATION MODE: {mode.upper()}")
        print(f"{'='*60}")
        preds = []

        for _, row in gold_df.iterrows():
            variant = row["variant"]
            disease = row.get("disease", "HHT")
            gold = normalize(row["gold_classification_short"])

            print(f"\n  [{mode}] {variant}...")
            try:
                scoring = run_pipeline_ablation(variant, disease, mode)
                pred = normalize(scoring.get("classification", "ERROR"))
            except Exception as e:
                print(f"  ERROR: {e}")
                pred = "ERROR"

            preds.append({"variant": variant, "gold": gold, "pred": pred})
            print(f"  gold={gold}  pred={pred}")

        all_results[mode] = preds

    # save raw results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = Path(output_dir) / f"ablation_raw_{timestamp}.json"
    with open(raw_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nRaw results saved to {raw_path}")

    # print comparison table
    print(f"\n{'='*60}")
    print("ABLATION STUDY RESULTS")
    print(f"{'='*60}")
    print(f"{'Mode':<12} {'Accuracy':>10} {'Precision':>10} {'Recall':>10} {'F1':>10} {'Errors':>8}")
    print("-" * 62)

    summary = {}
    for mode in ABLATION_MODES:
        preds = all_results[mode]
        y_true = [p["gold"] for p in preds]
        y_pred = [p["pred"] for p in preds]
        metrics, num_errors = compute_metrics(y_true, y_pred)
        summary[mode] = metrics

        if metrics:
            print(
                f"{mode:<12} "
                f"{metrics['accuracy']:>10.3f} "
                f"{metrics['macro_precision']:>10.3f} "
                f"{metrics['macro_recall']:>10.3f} "
                f"{metrics['macro_f1']:>10.3f} "
                f"{num_errors:>8}"
            )
        else:
            print(f"{mode:<12} {'ALL FAILED':>52}")

    summary_path = Path(output_dir) / f"ablation_summary_{timestamp}.json"
    with open(summary_path, "w") as f:
        json.dump({"timestamp": timestamp, "modes": summary}, f, indent=2)
    print(f"\nSummary saved to {summary_path}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Question 3 - Ablation Study")
    parser.add_argument("--gold_answer_csv_filename", type=str, required=True)
    parser.add_argument("--variation_ids", type=str, default=None,
                        help="Comma-separated variation IDs to test (default: all)")
    parser.add_argument("--output_dir", type=str, default="evaluation/outputs")
    args = parser.parse_args()

    variant_ids = None
    if args.variation_ids:
        variant_ids = [int(v.strip()) for v in args.variation_ids.split(",")]

    run_question3_evaluation(
        gold_csv_path=args.gold_answer_csv_filename,
        variant_ids=variant_ids,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()

