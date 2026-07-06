# QUESTION2: 
# Can the proposed system accurately classify genetic variants according to the ACMG/AMP guidelines?
# Accuracy
# Precision
# Recall
# F1-score


import pandas as pd
import argparse
import sys
import os
import json
from pipeline import _safe_variant_name
import numpy as np
from sklearn.metrics import f1_score, recall_score, accuracy_score, confusion_matrix
import datetime
from pathlib import Path
from typing import Callable

# ========================================================
# HELPERS TO LOADING GOLD ANSWERS AND PIPELINE PREDICTIONS
# ========================================================

def load_gold_answer_df(gold_csv_path: str) -> pd.DataFrame:
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
    try:
        with open(batch_summary_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except FileNotFoundError as e:
        raise FileNotFoundError(
            f"Could not found batch summary at {batch_summary_path}"
        )
    
    results = payload["results"]

    rows = {}
    for result in results:
        print(result)
        if result.get("status") and result.get("status") == "error":
            row = {
                "variant": result["variant"],
                "pred_classification": None,
                "status": "error",
            }
            rows.update(row)
            continue

        row = {
            "variant": result["variant"],
            "pred_classification": result["classification"],
            "status": "success",
        }
        rows.update(row)

    return pd.DataFrame(rows)

def merge_df(pred_df: pd.DataFrame, gold_df: pd.DataFrame) -> pd.DataFrame:
    eval_df = pred_df.merge(
        gold_df,
        on=["variant"],
        how="left",
    )

    eval_df["pred_classification"] = eval_df["pred_classification"].apply(
        lambda classification: 1 if classification else 0
    )
    eval_df["gold_classification"] = eval_df["gold_classification"].apply(
        lambda classification: 1 if classification else 0
    )

    return eval_df

# ========================================================
# HELPERS TO CALCULATE PRECISION, RECALL, ACCURACY, F1
# ========================================================
def bootstrap_metric(
        predictions: np.ndarray, 
        gold_answers: np.ndarray,
        metric_function: Callable,
        num_boots: int = 1000,
) -> tuple:
    rng = np.random.RandomState()
    vals = []
    idx = np.arange(len(predictions))
    for _ in range(num_boots):
        sample_idx = rng.choice(idx, len(idx), replace=False)
        metrics = metric_function(predictions[sample_idx], gold_answers[sample_idx])
        vals.append(metrics)
    return vals.mean(), vals.std(ddof=1)

def compute_precision(
        predictions: np.ndarray,
        classification: np.ndarray
) -> float:
    cm = confusion_matrix(classification, predictions, labels=[1, 0])
    tp = cm[0, 0]
    fp = cm[1, 0]
    return tp / (tp + fp)

def compute_specificity(
        predictions: np.ndarray,
        classification: np.ndarray
) -> float:
    cm = confusion_matrix(classification, predictions, labels=[1, 0])
    tn = cm[1,1]
    fn = cm[0,1]
    return tn / (tn + fn)

# ========================================================
# HELPERS THAT PRINT & SAVE THE RESULT TO A JSON FILE
# ========================================================

def print_results(accuracy: float,
        precision: float,
        recall: float,
        f1_score: float,
        confusion_matrix: np.ndarray,
) -> None:
    
    print(f"{"+"*60}")
    print(f"""accuracy: {accuracy}
precision: {precision}
recall: {recall}
F1: {f1_score}
""")
    
    print("\nConfusion Matrix:")
    print("-----------------")
    print("             Predicted")
    print("             Not Met  Met")
    print(f"Actual Not Met   {confusion_matrix[0][0]:<7} {confusion_matrix[0][1]}")
    print(f"      Met        {confusion_matrix[1][0]:<7} {confusion_matrix[1][1]}")
    

def save_results(
        accuracy: float,
        precision: float,
        recall: float,
        f1_score: float,
        output_dir: str,
) -> None:
    time = datetime.now()
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    filename = Path(output_dir) / f"{time.strftime("%Y%m%d_%H%M%S")}.json"
    
    output = {
        "time": time,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "F1": f1_score,
    }

    with open(filename, "w") as f:
        json.dump(output, f, indent = 2)

# ========================================================
# A FUNCTION THAT COMBINES EVERYTHING
# ========================================================
def run_question2_evaluation(
        gold_answer_csv_path: str,
        bath_summary_json_path: str,
        output_dir: str
) -> None:
    # ---------------- Loading the data ---------------- #
    classification_df = load_gold_answer_df(gold_csv_path=gold_answer_csv_path)
    prediction_df = load_predictions(batch_summary_path=bath_summary_json_path)
    combined_df = merge_df(classification_df, prediction_df)

    # ---------------- Compute Statistics ---------------- #
    accuracy, accuracy_std = bootstrap_metric(
        predictions=combined_df["pred_classification"].to_numpy(),
        gold_answers=combined_df["gold_classification"].to_numpy(),
        metric_function=accuracy_score,
        num_boots=1000
    )

    precision, precision_std = bootstrap_metric(
        predictions=combined_df["pred_classification"].to_numpy(),
        gold_answers=combined_df["gold_classification"].to_numpy(),
        metric_function=compute_precision,
    )

    recall, recall_std = bootstrap_metric(
        predictions=combined_df["pred_classification"].to_numpy(),
        gold_answers=combined_df["gold_classification"].to_numpy(),
        metric_function=recall_score
    )

    F1, F1_std = bootstrap_metric(
        predictions=combined_df["pred_classification"].to_numpy(),
        gold_answers=combined_df["gold_classification"].to_numpy(),
        metric_function=f1_score
    )

    cm = confusion_matrix(
        combined_df["gold_classification"].to_numpy(),
        combined_df["pred_classification"].to_numpy(),
        labels=[0,1]
    )

    # ---------------- Printing & Saving Outputs ---------------- #
    print_results(
        accuracy,
        precision,
        recall,
        F1,
        cm,
    )

    save_results(
        accuracy,
        precision,
        recall,
        F1,
        output_dir,
    )

def main():
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