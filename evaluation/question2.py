# QUESTION2:
# Can the proposed system accurately classify genetic variants according to the ACMG/AMP guidelines?
# Accuracy
# Precision
# Recall
# F1-score

from pipeline import _safe_variant_name
import pandas as pd
import argparse
import sys
import os
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
from typing import Callable
from scipy.stats import bootstrap

LABELS = ["B", "LB", "VUS", "LP", "P"]


CLASSIFICATION_MAPPING = {
    # Guard against lowercase letters in hht-batches.csv
    "b": "B",
    "lb": "LB",
    "vus": "VUS",
    "lp": "LP",
    "p": "P",

    "benign": "B",
    "likely benign": "LB",
    "uncertain significance": "VUS",
    "variant of uncertain significance": "VUS",
    "variant of uncertain significance (vus)": "VUS",
    "likely pathogenic": "LP",
    "pathogenic": "P",

    # ClinVar "conflicting evidence" combo labels — collapsed to the
    # less-severe/likely-* side per common ClinVar convention. Revisit if
    # a stricter treatment (e.g. treat as a distinct/excluded class) is
    # preferred for this evaluation.
    "benign/likely benign": "LB",
    "b/lb": "LB",
    "pathogenic/likely pathogenic": "LP",
    "p/lp": "LP",

    "error": "ERROR"
}

def normalize_classification_label(raw_label: str) -> str:
    """Normalize a raw classification label into the standard evaluation label format.

    Args:
        raw_label: The raw classification string produced by the model or dataset.

    Returns:
        A normalized label from LABELS or ERROR.

    Raises:
        ValueError: If the input label is missing or not recognized.
    """
    if raw_label is None:
        raise ValueError("Classification Result Unavailable")

    label = str(raw_label).strip().lower()
    if label in CLASSIFICATION_MAPPING:
        return CLASSIFICATION_MAPPING[label]
    
    raise ValueError(f"Unknown classification: {raw_label}")



# ========================================================
# HELPERS TO LOADING GOLD ANSWERS AND PIPELINE PREDICTIONS
# ========================================================

def load_gold_answer_df(gold_csv_path: str) -> pd.DataFrame:
    """Load and preprocess the ground-truth evaluation dataset.

    Args:
        gold_csv_path: Path to the CSV file containing gold variant classifications.

    Returns:
        A pandas DataFrame with normalized variant names and renamed evaluation columns.

    Raises:
        FileNotFoundError: If the gold answer CSV file does not exist.
    """
    try: 
        gold_df = pd.read_csv(gold_csv_path)
    except FileNotFoundError as e:
        raise FileNotFoundError(
            f"Could not found golen answer csv file at {gold_csv_path}"
        )

    gold_df = gold_df.rename(columns={
        "hgvs_cdna": "variant",
        "condition": "disease",
        "gt_classification": "gold_classification",
        "gt_classification_short": "gold_classification_short"
    })

    gold_df["variant"] = gold_df["variant"].apply(_safe_variant_name)

    return gold_df

def load_predictions(batch_summary_path: str) -> pd.DataFrame:
    """Load model predictions from a batch summary JSON file.

    Args:
        batch_summary_path: Path to the JSON file containing model batch outputs.

    Returns:
        A pandas DataFrame containing variants and predicted classifications.

    Raises:
        FileNotFoundError: If the batch summary JSON file does not exist.
    """
    try:
        with open(batch_summary_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except FileNotFoundError as e:
        raise FileNotFoundError(
            f"Could not found batch summary at {batch_summary_path}"
        )
    
    results = payload["results"]

    rows = []
    for result in results:
        if result.get("status") and result.get("status") == "error":
            row = {
                "variant": result["variant"],
                "pred_classification": "ERROR"
            }
            rows.append(row)
            continue

        row = {
            "variant": result["variant"],
            "pred_classification": result["classification"],
        }
        rows.append(row)

    prediction_df = pd.DataFrame(rows)
    prediction_df["variant"] = prediction_df["variant"].apply(_safe_variant_name)

    return prediction_df

def merge_df(pred_df: pd.DataFrame, gold_df: pd.DataFrame) -> tuple:
    """Merge model predictions with gold labels and remove failed predictions.

    Args:
        pred_df: DataFrame containing model predictions.
        gold_df: DataFrame containing ground-truth classifications.

    Returns:
        A tuple containing the merged evaluation DataFrame and the number of failed predictions.
    """
    eval_df = pred_df.merge(
        gold_df,
        on=["variant"],
        how="left",
    )

    # Guard against predicted variants that have no matching gold row (NaN
    # gold_classification after the left-merge). Drop these before label
    # normalization, since normalize_classification_label would otherwise
    # raise ValueError on NaN and crash the whole evaluation run.
    unmatched_mask = eval_df["gold_classification"].isna()
    num_unmatched = int(unmatched_mask.sum())
    if num_unmatched:
        print(
            f"WARNING: {num_unmatched} predicted variant(s) had no matching "
            f"gold row and will be excluded from evaluation: "
            f"{eval_df.loc[unmatched_mask, 'variant'].tolist()}"
        )
    eval_df = eval_df.loc[~unmatched_mask].copy()

    eval_df["pred_classification"] = eval_df["pred_classification"].apply(normalize_classification_label)
    eval_df["gold_classification"] = eval_df["gold_classification"].apply(normalize_classification_label)
    num_errors = (eval_df['pred_classification'] == "ERROR").sum()

    eval_df = eval_df.drop(eval_df[eval_df['pred_classification'] == "ERROR"].index)
    num_errors += num_unmatched
    return eval_df, num_errors

# ========================================================
# HELPERS THAT PRINT & SAVE THE RESULT TO A JSON FILE
# ========================================================

def print_results(accuracy: float,
        precision: float,
        recall: float,
        f1_score: float,
        confusion_matrix: np.ndarray,
        num_errors: int
) -> None:
    """Print evaluation metrics and the confusion matrix in a readable format.

    Args:
        accuracy: Overall classification accuracy.
        precision: Precision score.
        recall: Recall score.
        f1_score: F1 score.
        confusion_matrix: Confusion matrix generated from predictions.
        num_errors: Number of variants that failed during prediction.
    """
    print(f"{'-'*60}")
    print(f"""accuracy: {accuracy}
precision: {precision}
recall: {recall}
F1: {f1_score}
number of failed variants: {num_errors}
""")
    
    print("Confusion Matrix:")
    print("-" * 60)
    cm_df = pd.DataFrame(
        confusion_matrix,
        index=[f"Actual {label}" for label in LABELS],
        columns=[f"Pred {label}" for label in LABELS],
    )
    print(cm_df.to_string())
    print("-" * 60)
    

def save_results(
        accuracy: float,
        precision: float,
        recall: float,
        f1_score: float,
        classification_report: str,
        num_errors: int,
        output_dir: str,
) -> None:
    """Save evaluation metrics and classification details as a JSON file.

    Args:
        accuracy: Overall classification accuracy.
        precision: Precision score.
        recall: Recall score.
        f1_score: F1 score.
        classification_report: Detailed per-class classification metrics.
        num_errors: Number of failed variant predictions.
        output_dir: Directory where the JSON output file is saved.
    """
    time = datetime.now()
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    filename = Path(output_dir) / f"{time.strftime('%Y%m%d_%H%M%S')}.json"
    
    output = {
        "time": str(time),
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "F1": f1_score,
        "failed_variant_count": int(num_errors),
        "classification_report": classification_report
    }

    try:
        with open(filename, "w") as f:
            json.dump(output, f, indent = 2)
            print(f"RESULT SAVED TO {filename}")
    except Exception as e:
        print("WARNING: Failed to save the result.")

# ========================================================
# A FUNCTION THAT COMBINES EVERYTHING
# ========================================================
def run_question2_evaluation(
        gold_answer_csv_path: str,
        bath_summary_json_path: str,
        output_dir: str
) -> None:
    """Run the complete Question 2 evaluation pipeline.

    This function loads the gold dataset and model predictions, merges the results,
    computes classification metrics, prints the evaluation summary, and saves the outputs.

    Args:
        gold_answer_csv_path: Path to the gold answer CSV file.
        bath_summary_json_path: Path to the model batch summary JSON file.
        output_dir: Directory where evaluation results are saved.
    """
    # ---------------- Loading the data ---------------- #
    classification_df = load_gold_answer_df(gold_csv_path=gold_answer_csv_path)
    prediction_df = load_predictions(batch_summary_path=bath_summary_json_path)
    combined_df, num_errors = merge_df(prediction_df, classification_df)

    y_true = combined_df["gold_classification"]
    y_pred = combined_df["pred_classification"]

    try: 
        # ---------------- Compute Statistics ---------------- #
        accuracy = accuracy_score(y_true=y_true,y_pred=y_pred)
        macro_recall = recall_score(y_true, y_pred,labels=LABELS,average="macro",zero_division=0)
        macro_precision = precision_score(y_true,y_pred,labels=LABELS,average="macro",zero_division=0)
        macro_f1 = f1_score(y_true,y_pred,labels=LABELS,average="macro",zero_division=0)
        cm = confusion_matrix(y_true,y_pred,labels=LABELS,)
        classification = classification_report(y_true,y_pred,labels=LABELS,zero_division=0,output_dict=True)

        # ---------------- Printing & Saving Outputs ---------------- #
        print_results(
            accuracy=accuracy,
            precision=macro_precision,
            recall=macro_recall,
            f1_score=macro_f1,
            confusion_matrix=cm,
            num_errors=num_errors,
        )

        save_results(
            accuracy=accuracy,
            precision=macro_precision,
            recall=macro_recall,
            f1_score=macro_f1,
            classification_report=classification,
            num_errors=num_errors,
            output_dir=output_dir,
        )

    except ValueError:
        print(f"{'-'*60}")
        print(f"""THE INPUT FILE CONTAINS NO VARIANT OR ALL THE VARIANTS HAVE FAILED
NOTHING SAVED TO OUTPUT
{num_errors} / {len(prediction_df)} VARIANTS FAILED """)
        print(f"{'-'*60}")

def main():
    """Parse command-line arguments and run the Question 2 evaluation pipeline."""
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

    run_question2_evaluation(
        args.gold_answer_csv_filename,
        args.model_output_json_filename,
        args.output_dir
    )

if __name__ == "__main__":
    main()