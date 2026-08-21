# QUESTION1:
# Can the proposed system accurately evaluate individual ACMG/AMP (or VCEP-specific) criteria?
# Accuracy
# Precision
# Recall
# F1-score
#
# Unlike question2 (final variant classification), this script evaluates the system at the
# PER-CRITERION level: for every (variant, criterion) pair the pipeline touched, did the
# system correctly decide whether that criterion APPLIES or DOES NOT APPLY to the variant?
#
# Gold labels come from two columns in the evaluation CSV, both semicolon-separated lists of
# criterion names (optionally with a strength suffix, e.g. "PM2_Supporting"):
#   gt_criteria_applied   -> criteria the human curator says DO apply (positive / applies=True)
#   gt_criteria_not_met   -> criteria the human curator explicitly says DO NOT apply (applies=False)
# Any criterion the pipeline evaluated that is mentioned in NEITHER column has no known gold
# label (the curator simply didn't comment on it) and is excluded from scoring.
#
# Predictions come from the per-variant JSON files written by pipeline.run_batch /
# pipeline.save_results (NOT batch_summary.json, which only has the final classification).
# Each such file has a top-level "results" list of criterion dicts:
#   {"criterion": "PM2_SUPPORTING", "applies": true/false, "status": "complete"/"skipped"/"error", ...}
# A whole-variant failure is written as "<variant>.error.json" with no "results" key at all.

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import _safe_variant_name
import pandas as pd
import argparse
import json
import numpy as np
from sklearn.metrics import (
    f1_score,
    recall_score,
    accuracy_score,
    confusion_matrix,
    precision_score,
    classification_report,
)
from datetime import datetime
from pathlib import Path

# ========================================================
# CONSTANTS
# ========================================================

# Binary labels used for per-criterion "applies?" evaluation.
APPLIES_LABELS = [False, True]


# ========================================================
# HELPERS FOR NORMALIZING CRITERION NAMES / GOLD COLUMNS
# ========================================================

def normalize_criterion_name(raw_criterion: str) -> str:
    """Normalize a raw criterion string (from either gold CSV or pipeline output)
    into a canonical uppercase, underscore-separated form.

    Args:
        raw_criterion: A criterion label such as "PM2_Supporting" or "pvs1".

    Returns:
        The canonical form, e.g. "PM2_SUPPORTING" or "PVS1".
    """
    return str(raw_criterion).strip().upper().replace("-", "_").replace(" ", "_")


def parse_criteria_list(raw_value) -> set:
    """Parse a semicolon-separated criteria column from the gold CSV into a set of
    normalized criterion names.

    Args:
        raw_value: The raw cell value (string, NaN, or None).

    Returns:
        A set of normalized criterion names. Empty set if the cell is blank/NaN.
    """
    if raw_value is None or (isinstance(raw_value, float) and np.isnan(raw_value)):
        return set()

    raw_value = str(raw_value).strip()
    if not raw_value:
        return set()

    return {
        remove_strength(normalize_criterion_name(token))
        for token in raw_value.split(";")
        if token.strip()
    }

def remove_strength(criterion: str) -> str:
    """Remove the strength suffix of a criterion.

    Args:
        criterion: A criterion label such as "BS3_MODERATE"

    Returns:
        The criterion name without the strength suffix, such as "BS3"
    """
    return criterion.split("_")[0].strip()

# ========================================================
# HELPERS TO LOAD GOLD ANSWERS AND PIPELINE PREDICTIONS
# ========================================================

def load_gold_answer_df(gold_csv_path: str) -> pd.DataFrame:
    """Load and preprocess the ground-truth evaluation dataset.

    Args:
        gold_csv_path: Path to the CSV file containing gold variant classifications
            and per-criterion evidence columns.

    Returns:
        A pandas DataFrame indexed by normalized variant name with the gold
        applied/not-met criteria sets attached.

    Raises:
        FileNotFoundError: If the gold answer CSV file does not exist.
    """
    try:
        gold_df = pd.read_csv(gold_csv_path)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Could not find gold answer csv file at {gold_csv_path}"
        )

    gold_df = gold_df.rename(columns={"hgvs_cdna": "variant"})

    for col in ("gt_criteria_applied", "gt_criteria_not_met"):
        if col not in gold_df.columns:
            raise ValueError(
                f"Gold CSV is missing required column '{col}'. "
                f"Columns found: {list(gold_df.columns)}"
            )

    gold_df["variant_key"] = gold_df["variant"].apply(_safe_variant_name)
    gold_df["gold_applied"] = gold_df["gt_criteria_applied"].apply(parse_criteria_list)
    gold_df["gold_not_met"] = gold_df["gt_criteria_not_met"].apply(parse_criteria_list)

    return gold_df.set_index("variant_key")
 
def load_criterion_predictions(batch_summary_path: str) -> pd.DataFrame:
    """Load per-criterion predictions from a batch output directory, given the path
    to that directory's batch_summary.json (as written by pipeline.run_batch).

    The per-criterion detail lives in the individual per-variant JSON files that sit
    alongside batch_summary.json (batch_summary.json itself only has the final
    classification per variant), so this reads every "*.json" file in the same
    directory.

    Args:
        batch_summary_path: Path to the batch_summary.json file produced by a
            pipeline.run_batch run.

    Returns:
        A pandas DataFrame with one row per (variant, criterion) pair evaluated
        by the pipeline, including the predicted "applies" boolean (or None for
        skipped/error rows).

    Raises:
        FileNotFoundError: If the batch summary file (or its directory) does not exist.
    """
    summary_path = Path(batch_summary_path)
    if not summary_path.exists():
        raise FileNotFoundError(f"Could not find batch summary at {batch_summary_path}")

    batch_path = summary_path.parent
    if not batch_path.is_dir():
        raise FileNotFoundError(f"Could not find batch output directory at {batch_path}")

    rows = []
    num_variant_errors = 0

    for json_file in sorted(batch_path.glob("*.json")):
        if json_file.name == "batch_summary.json":
            continue

        with open(json_file, "r", encoding="utf-8") as f:
            payload = json.load(f)

        variant = payload.get("variant")
        if variant is None:
            continue
        variant_key = _safe_variant_name(variant)

        # Whole-variant failure (either "*.error.json" or an "ok" file that
        # somehow has no results) -- no criteria to score for this variant.
        if payload.get("status") == "error" or "results" not in payload:
            num_variant_errors += 1
            continue

        for result in payload["results"]:
            criterion = normalize_criterion_name(result.get("criterion", ""))
            criterion = remove_strength(criterion)
            status = result.get("status", "unknown")

            if status == "complete":
                pred_applies = bool(result.get("applies"))
            elif status == "skipped":
                # A criterion skipped because a dependency wasn't satisfied is,
                # in effect, a system decision that the criterion does not apply.
                pred_applies = False
            else:
                # status == "error" (or anything unrecognized) -> system failed
                # to evaluate this criterion; excluded from scoring, counted separately.
                pred_applies = None

            rows.append({
                "variant_key": variant_key,
                "variant": variant,
                "criterion": criterion,
                "status": status,
                "pred_applies": pred_applies,
            })

    pred_df = pd.DataFrame(rows)

    return pred_df, num_variant_errors


def build_evaluation_df(pred_df: pd.DataFrame, gold_df: pd.DataFrame) -> tuple:
    """Attach gold applies/not-applies labels to each predicted (variant, criterion)
    row and drop rows with no gold label or a system error.

    Args:
        pred_df: DataFrame of per-criterion predictions (see load_criterion_predictions).
        gold_df: DataFrame of gold answers, indexed by normalized variant name.

    Returns:
        A tuple of (scored DataFrame with gold_applies/pred_applies columns,
        num_criterion_errors, num_no_gold_label, num_unmatched_variants).
    """
    gold_applied_lookup = gold_df["gold_applied"].to_dict()

    gold_applies = []
    unmatched_variant = []
    for _, row in pred_df.iterrows():
        vkey = row["variant_key"]
        if vkey not in gold_applied_lookup:
            gold_applies.append(None)
            unmatched_variant.append(True)
            continue

        unmatched_variant.append(False)
        criterion = row["criterion"]
        if criterion in gold_applied_lookup[vkey]:
            gold_applies.append(True)
        else:
            gold_applies.append(False)

    pred_df = pred_df.copy()
    pred_df["gold_applies"] = gold_applies
    pred_df["unmatched_variant"] = unmatched_variant

    num_unmatched_variants = pred_df["unmatched_variant"].sum()
    num_criterion_errors = (pred_df["pred_applies"].isna() & ~pred_df["unmatched_variant"]).sum()
    criterion_with_errors = pred_df[pred_df["pred_applies"].isna() & ~pred_df["unmatched_variant"]].to_dict()
    num_no_gold_label = (
        pred_df["pred_applies"].notna()
        & ~pred_df["unmatched_variant"]
        & pred_df["gold_applies"].isna()
    ).sum()

    scored_df = pred_df[
        pred_df["pred_applies"].notna() & pred_df["gold_applies"].notna()
    ].copy()

    return scored_df, int(num_criterion_errors), int(num_no_gold_label), int(num_unmatched_variants), criterion_with_errors


# ========================================================
# HELPERS THAT PRINT & SAVE THE RESULT TO A JSON FILE
# ========================================================

def print_results(
        accuracy: float,
        precision: float,
        recall: float,
        f1: float,
        confusion_matrix_: np.ndarray,
        num_criterion_errors: int,
        num_no_gold_label: int,
        num_unmatched_variants: int,
        num_variant_errors: int,
        num_scored: int,
) -> None:
    """Print per-criterion evaluation metrics and the confusion matrix in a readable format."""
    print(f"{'-'*60}")
    print(f"""accuracy: {accuracy}
precision: {precision}
recall: {recall}
F1: {f1}
number of (variant, criterion) pairs scored: {num_scored}
number of criteria that errored during evaluation: {num_criterion_errors}
number of criteria with no gold label (curator silent): {num_no_gold_label}
number of predicted criteria with unmatched/unknown variant: {num_unmatched_variants}
number of whole-variant failures excluded: {num_variant_errors}
""")

    print("Confusion Matrix (rows=actual applies, cols=predicted applies):")
    print("-" * 60)
    cm_df = pd.DataFrame(
        confusion_matrix_,
        index=[f"Actual {label}" for label in APPLIES_LABELS],
        columns=[f"Pred {label}" for label in APPLIES_LABELS],
    )
    print(cm_df.to_string())
    print("-" * 60)


def print_per_criterion_breakdown(scored_df: pd.DataFrame) -> None:
    """Print per-criterion accuracy/precision/recall/F1 so individual weak criteria
    can be identified.

    Args:
        scored_df: DataFrame with gold_applies/pred_applies columns already attached.
    """
    print("\nPer-criterion breakdown:")
    print("-" * 60)
    print(f"{'Criterion':<20} {'N':>5} {'Applied':>8} {'Accuracy':>10} {'Precision':>10} {'Recall':>10} {'F1':>10}")
    for criterion, group in scored_df.groupby("criterion"):
        y_true = group["gold_applies"].astype(bool)
        y_pred = group["pred_applies"].astype(bool)
        acc = accuracy_score(y_true, y_pred)
        prec = precision_score(y_true, y_pred, zero_division=0)
        rec = recall_score(y_true, y_pred, zero_division=0)
        f1 = f1_score(y_true, y_pred, zero_division=0)
        num_applied = int(y_true.sum())
        print(f"{criterion:<20} {len(group):>5} {num_applied:>8} {acc:>10.3f} {prec:>10.3f} {rec:>10.3f} {f1:>10.3f}")
    print("-" * 60)


def save_results(
        accuracy: float,
        precision: float,
        recall: float,
        f1: float,
        classification_report_: dict,
        per_criterion: dict,
        num_criterion_errors: int,
        num_no_gold_label: int,
        num_unmatched_variants: int,
        num_variant_errors: int,
        num_scored: int,
        output_dir: str,
) -> None:
    """Save per-criterion evaluation metrics as a JSON file."""
    time = datetime.now()
    os.makedirs(output_dir, exist_ok=True)
    filename = Path(output_dir) / f"{time.strftime('%Y%m%d_%H%M%S')}_question1.json"

    output = {
        "time": str(time),
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "F1": f1,
        "num_scored": int(num_scored),
        "num_criterion_errors": int(num_criterion_errors),
        "num_no_gold_label": int(num_no_gold_label),
        "num_unmatched_variants": int(num_unmatched_variants),
        "num_variant_errors": int(num_variant_errors),
        "classification_report": classification_report_,
        "per_criterion": per_criterion,
    }

    try:
        with open(filename, "w") as f:
            json.dump(output, f, indent=2)
            print(f"RESULT SAVED TO {filename}")
    except Exception:
        print("WARNING: Failed to save the result.")


# ========================================================
# A FUNCTION THAT COMBINES EVERYTHING
# ========================================================

def run_question1_evaluation(
        gold_answer_csv_path: str,
        bath_summary_json_path: str,
        output_dir: str,
) -> None:
    """Run the complete Question 1 evaluation pipeline: per-criterion applies/does-not-apply
    classification, scored against the gold CSV's gt_criteria_applied / gt_criteria_not_met
    columns.

    Args:
        gold_answer_csv_path: Path to the gold answer CSV file.
        bath_summary_json_path: Path to the model batch_summary.json file (the
            per-criterion detail is read from the other JSON files in the same directory).
        output_dir: Directory where evaluation results are saved.
    """
    # ---------------- Loading the data ---------------- #
    gold_df = load_gold_answer_df(gold_csv_path=gold_answer_csv_path)
    pred_df, num_variant_errors = load_criterion_predictions(batch_summary_path=bath_summary_json_path)

    if pred_df.empty:
        print(f"{'-'*60}")
        print("NO CRITERION-LEVEL PREDICTIONS FOUND IN BATCH DIRECTORY")
        print(f"{num_variant_errors} whole-variant failure(s) found")
        print("NOTHING SAVED TO OUTPUT")
        print(f"{'-'*60}")
        return

    scored_df, num_criterion_errors, num_no_gold_label, num_unmatched_variants, criterion_with_error = build_evaluation_df(
        pred_df, gold_df
    )

    if scored_df.empty:
        print(f"{'-'*60}")
        print("NO (VARIANT, CRITERION) PAIR HAD BOTH A GOLD LABEL AND A VALID PREDICTION")
        print("NOTHING SAVED TO OUTPUT")
        print(f"{'-'*60}")
        return

    y_true = scored_df["gold_applies"].astype(bool)
    y_pred = scored_df["pred_applies"].astype(bool) 

    # ---------------- Compute Statistics ---------------- #
    accuracy = accuracy_score(y_true, y_pred)
    precision = precision_score(y_true, y_pred, zero_division=0)
    recall = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    cm = confusion_matrix(y_true, y_pred, labels=APPLIES_LABELS)
    report = classification_report(
        y_true, y_pred, labels=APPLIES_LABELS, zero_division=0, output_dict=True
    )

    per_criterion = {}
    for criterion, group in scored_df.groupby("criterion"):
        gt = group["gold_applies"].astype(bool)
        pt = group["pred_applies"].astype(bool)
        per_criterion[criterion] = {
            "n": int(len(group)),
            "applied": int(gt.sum()),
            "accuracy": accuracy_score(gt, pt),
            "precision": precision_score(gt, pt, zero_division=0),
            "recall": recall_score(gt, pt, zero_division=0),
            "F1": f1_score(gt, pt, zero_division=0),
        }

    # ---------------- Printing & Saving Outputs ---------------- #
    print_results(
        accuracy=accuracy,
        precision=precision,
        recall=recall,
        f1=f1,
        confusion_matrix_=cm,
        num_criterion_errors=num_criterion_errors,
        num_no_gold_label=num_no_gold_label,
        num_unmatched_variants=num_unmatched_variants,
        num_variant_errors=num_variant_errors,
        num_scored=len(scored_df),
    )
    print_per_criterion_breakdown(scored_df)

    save_results(
        accuracy=accuracy,
        precision=precision,
        recall=recall,
        f1=f1,
        classification_report_=report,
        per_criterion=per_criterion,
        num_criterion_errors=num_criterion_errors,
        num_no_gold_label=num_no_gold_label,
        num_unmatched_variants=num_unmatched_variants,
        num_variant_errors=num_variant_errors,
        num_scored=len(scored_df),
        output_dir=output_dir,
    )


def main():
    """Parse command-line arguments and run the Question 1 evaluation pipeline."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--gold_answer_csv_filename",
        type=str,
        help="Enter the file path of our evaluation dataset",
    )

    parser.add_argument(
        "--model_output_json_filename",
        type=str,
        help="""Enter the file path of batch_summary.json file
        produced after you run a batch of variants"""
    )

    parser.add_argument(
        "--output_dir",
        type=str,
        help="""Enter the file path of output directory
        (please enter evaluation/outputs)"""
    )

    args = parser.parse_args()

    run_question1_evaluation(
        args.gold_answer_csv_filename,
        args.model_output_json_filename,
        args.output_dir
    )


if __name__ == "__main__":
    main()
