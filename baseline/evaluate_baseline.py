"""
Scores baseline/outputs/baseline_results.json (produced by run_baseline.py)
against the gold-standard labels embedded in that same file.

Mirrors the metric choices/conventions in evaluation/question2.py (same 5-class
label scheme B/LB/VUS/LP/P, same sklearn macro-averaged metrics, same
classification_report/confusion_matrix), but adapted for baseline_results.json's
structure: each variant has multiple *passes*, not one prediction.

What this computes
-------------------
1. Per-pass metrics: for each pass index (1, 2, 3, ...), treat that pass's
   classification as the prediction for every variant and compute accuracy,
   macro/weighted precision/recall/F1, a confusion matrix, and a full
   per-class classification_report -- exactly as if it were a single
   evaluation run.
2. Averaged-across-passes metrics: mean +/- std of each of the above metrics
   across all passes. This answers "how did the baseline do, accounting for
   run-to-run variance" rather than trusting any single pass.
3. Majority-vote metrics: metrics computed using the majority classification
   across passes per variant (already computed by run_baseline.py), as a
   second, arguably more representative, single number.
4. A couple of extras beyond the core four metrics, since ACMG/AMP classes are
   ordinally ordered (B < LB < VUS < LP < P):
     - "off-by-one" accuracy: fraction of predictions within one severity tier
       of the gold label (a common leniency measure in variant classification
       benchmarks, since B vs LB is a much smaller miss than B vs P).
     - Cohen's kappa: agreement with gold beyond what chance alone would give,
       useful because raw accuracy alone doesn't account for class imbalance
       (most evaluation sets are heavy on P/LP/VUS).
   Both are computed per-pass, averaged, and for the majority vote.

Usage
-----
    venv/bin/python -m baseline.evaluate_baseline \\
        --results baseline/outputs/baseline_results.json \\
        --output-dir baseline/outputs
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    cohen_kappa_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

BASELINE_DIR = Path(__file__).resolve().parent
DEFAULT_RESULTS = BASELINE_DIR / "outputs" / "baseline_results.json"
DEFAULT_OUTPUT_DIR = BASELINE_DIR / "outputs"

LABELS = ["B", "LB", "VUS", "LP", "P"]
LABEL_RANK = {label: i for i, label in enumerate(LABELS)}  # for off-by-one / ordinal distance

# Same normalization table as evaluation/question2.py, so labels line up with
# the rest of the project's evaluation scripts. Extend this if classify() or
# the gold CSV ever produces a label string not covered here.
CLASSIFICATION_MAPPING = {
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
    "benign/likely benign": "LB",
    "b/lb": "LB",
    "pathogenic/likely pathogenic": "LP",
    "p/lp": "LP",
    "error": "ERROR",
}


def normalize_label(raw_label) -> str:
    if raw_label is None:
        return "ERROR"
    label = str(raw_label).strip().lower()
    return CLASSIFICATION_MAPPING.get(label, "ERROR")


# ──────────────────────────────────────────────────────────────────────────────
# Loading baseline_results.json into a tidy long-format DataFrame
# ──────────────────────────────────────────────────────────────────────────────

def load_long_df(results_path: Path) -> pd.DataFrame:
    """
    Returns one row per (variant, pass), with columns:
    variation_id, hgvs_cdna, gene, pass, gold_label, pred_label, is_error
    """
    with open(results_path, encoding="utf-8") as f:
        payload = json.load(f)

    rows = []
    for variant_result in payload["results"]:
        variation_id = variant_result.get("variation_id")
        hgvs_cdna = variant_result.get("hgvs_cdna")
        gene = variant_result.get("gene")

        gold_raw = (variant_result.get("gold_standard") or {}).get("gt_classification_short")
        gold_label = normalize_label(gold_raw)

        if variant_result.get("error"):
            # The whole variant failed before any pass ran (e.g. API key issue).
            rows.append(
                {
                    "variation_id": variation_id,
                    "hgvs_cdna": hgvs_cdna,
                    "gene": gene,
                    "pass": None,
                    "gold_label": gold_label,
                    "pred_label": "ERROR",
                    "is_error": True,
                }
            )
            continue

        for p in variant_result.get("passes", []):
            pass_idx = p.get("pass")
            if "error" in p or "classification_result" not in p:
                rows.append(
                    {
                        "variation_id": variation_id,
                        "hgvs_cdna": hgvs_cdna,
                        "gene": gene,
                        "pass": pass_idx,
                        "gold_label": gold_label,
                        "pred_label": "ERROR",
                        "is_error": True,
                    }
                )
                continue

            pred_raw = p["classification_result"].get("classification")
            rows.append(
                {
                    "variation_id": variation_id,
                    "hgvs_cdna": hgvs_cdna,
                    "gene": gene,
                    "pass": pass_idx,
                    "gold_label": gold_label,
                    "pred_label": normalize_label(pred_raw),
                    "is_error": False,
                }
            )

        # Majority-vote row, tagged with pass="majority" so it can be sliced
        # out separately.
        majority_raw = variant_result.get("majority_classification")
        rows.append(
            {
                "variation_id": variation_id,
                "hgvs_cdna": hgvs_cdna,
                "gene": gene,
                "pass": "majority",
                "gold_label": gold_label,
                "pred_label": normalize_label(majority_raw) if majority_raw else "ERROR",
                "is_error": majority_raw is None,
            }
        )

    return pd.DataFrame(rows), payload.get("meta", {})


# ──────────────────────────────────────────────────────────────────────────────
# Metric computation
# ──────────────────────────────────────────────────────────────────────────────

def off_by_one_accuracy(y_true: list[str], y_pred: list[str]) -> float:
    """Fraction of predictions within one severity tier of gold (e.g. LP predicted as P, or as VUS)."""
    hits = 0
    for t, p in zip(y_true, y_pred):
        if t not in LABEL_RANK or p not in LABEL_RANK:
            continue
        if abs(LABEL_RANK[t] - LABEL_RANK[p]) <= 1:
            hits += 1
    return hits / len(y_true) if y_true else float("nan")


def mean_ordinal_distance(y_true: list[str], y_pred: list[str]) -> float:
    """Average absolute distance between predicted and gold severity tiers (0 = perfect)."""
    dists = [
        abs(LABEL_RANK[t] - LABEL_RANK[p])
        for t, p in zip(y_true, y_pred)
        if t in LABEL_RANK and p in LABEL_RANK
    ]
    return float(np.mean(dists)) if dists else float("nan")


def compute_metrics(y_true: list[str], y_pred: list[str]) -> dict:
    """
    Computes the full metric bundle for one set of (gold, predicted) label pairs.
    ERROR-labeled predictions are excluded first (same convention as question2.py),
    with the count reported separately.
    """
    df = pd.DataFrame({"gold": y_true, "pred": y_pred})
    num_errors = int((df["pred"] == "ERROR").sum())
    df = df[df["pred"] != "ERROR"]

    if df.empty:
        return {
            "n": 0,
            "num_errors": num_errors,
            "accuracy": float("nan"),
            "macro_precision": float("nan"),
            "macro_recall": float("nan"),
            "macro_f1": float("nan"),
            "weighted_precision": float("nan"),
            "weighted_recall": float("nan"),
            "weighted_f1": float("nan"),
            "cohen_kappa": float("nan"),
            "off_by_one_accuracy": float("nan"),
            "mean_ordinal_distance": float("nan"),
            "confusion_matrix": None,
            "classification_report": None,
        }

    yt, yp = df["gold"].tolist(), df["pred"].tolist()

    return {
        "n": len(yt),
        "num_errors": num_errors,
        "accuracy": accuracy_score(yt, yp),
        "macro_precision": precision_score(yt, yp, labels=LABELS, average="macro", zero_division=0),
        "macro_recall": recall_score(yt, yp, labels=LABELS, average="macro", zero_division=0),
        "macro_f1": f1_score(yt, yp, labels=LABELS, average="macro", zero_division=0),
        "weighted_precision": precision_score(yt, yp, labels=LABELS, average="weighted", zero_division=0),
        "weighted_recall": recall_score(yt, yp, labels=LABELS, average="weighted", zero_division=0),
        "weighted_f1": f1_score(yt, yp, labels=LABELS, average="weighted", zero_division=0),
        "cohen_kappa": cohen_kappa_score(yt, yp, labels=LABELS),
        "off_by_one_accuracy": off_by_one_accuracy(yt, yp),
        "mean_ordinal_distance": mean_ordinal_distance(yt, yp),
        "confusion_matrix": confusion_matrix(yt, yp, labels=LABELS).tolist(),
        "classification_report": classification_report(yt, yp, labels=LABELS, zero_division=0, output_dict=True),
    }


def print_metrics(label: str, m: dict) -> None:
    print(f"\n{'=' * 70}\n{label}\n{'=' * 70}")
    if m["n"] == 0:
        print("No valid (non-error) predictions to score.")
        return
    print(f"n = {m['n']}  (excluded {m['num_errors']} error/unparseable predictions)")
    print(f"accuracy                 : {m['accuracy']:.4f}")
    print(f"macro precision          : {m['macro_precision']:.4f}")
    print(f"macro recall             : {m['macro_recall']:.4f}")
    print(f"macro F1                 : {m['macro_f1']:.4f}")
    print(f"weighted precision       : {m['weighted_precision']:.4f}")
    print(f"weighted recall          : {m['weighted_recall']:.4f}")
    print(f"weighted F1              : {m['weighted_f1']:.4f}")
    print(f"Cohen's kappa            : {m['cohen_kappa']:.4f}")
    print(f"off-by-one accuracy      : {m['off_by_one_accuracy']:.4f}")
    print(f"mean ordinal distance    : {m['mean_ordinal_distance']:.4f}")
    print("\nConfusion matrix (rows=actual, cols=predicted, order B/LB/VUS/LP/P):")
    cm_df = pd.DataFrame(
        m["confusion_matrix"],
        index=[f"Actual {label}" for label in LABELS],
        columns=[f"Pred {label}" for label in LABELS],
    )
    print(cm_df.to_string())


def average_metrics(per_pass: list[dict]) -> dict:
    """Mean +/- std across passes for each scalar metric (confusion matrices are summed instead)."""
    scalar_keys = [
        "accuracy",
        "macro_precision",
        "macro_recall",
        "macro_f1",
        "weighted_precision",
        "weighted_recall",
        "weighted_f1",
        "cohen_kappa",
        "off_by_one_accuracy",
        "mean_ordinal_distance",
    ]
    out = {}
    for key in scalar_keys:
        values = [m[key] for m in per_pass if not np.isnan(m[key])]
        out[f"{key}_mean"] = float(np.mean(values)) if values else float("nan")
        out[f"{key}_std"] = float(np.std(values)) if values else float("nan")

    summed_cm = np.zeros((len(LABELS), len(LABELS)), dtype=int)
    for m in per_pass:
        if m["confusion_matrix"] is not None:
            summed_cm += np.array(m["confusion_matrix"])
    out["summed_confusion_matrix"] = summed_cm.tolist()
    out["total_n"] = sum(m["n"] for m in per_pass)
    out["total_errors"] = sum(m["num_errors"] for m in per_pass)
    return out


def print_averaged(m: dict, num_passes: int) -> None:
    print(f"\n{'=' * 70}\nAVERAGED ACROSS {num_passes} PASSES (mean ± std)\n{'=' * 70}")
    print(f"total predictions scored : {m['total_n']}  (excluded {m['total_errors']} error/unparseable)")
    for key in [
        "accuracy",
        "macro_precision",
        "macro_recall",
        "macro_f1",
        "weighted_precision",
        "weighted_recall",
        "weighted_f1",
        "cohen_kappa",
        "off_by_one_accuracy",
        "mean_ordinal_distance",
    ]:
        print(f"{key:<25}: {m[key + '_mean']:.4f} ± {m[key + '_std']:.4f}")
    print("\nSummed confusion matrix across all passes (rows=actual, cols=predicted):")
    cm_df = pd.DataFrame(
        m["summed_confusion_matrix"],
        index=[f"Actual {label}" for label in LABELS],
        columns=[f"Pred {label}" for label in LABELS],
    )
    print(cm_df.to_string())


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS, help="Path to baseline_results.json")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Where to write the scored JSON summary")
    args = parser.parse_args()

    long_df, meta = load_long_df(args.results)

    pass_ids = sorted(
        {p for p in long_df["pass"].unique() if p is not None and p != "majority"}
    )

    per_pass_metrics = {}
    for pass_id in pass_ids:
        sub = long_df[long_df["pass"] == pass_id]
        m = compute_metrics(sub["gold_label"].tolist(), sub["pred_label"].tolist())
        per_pass_metrics[str(pass_id)] = m
        print_metrics(f"PASS {pass_id}", m)

    averaged = average_metrics(list(per_pass_metrics.values()))
    print_averaged(averaged, len(pass_ids))

    majority_sub = long_df[long_df["pass"] == "majority"]
    majority_metrics = compute_metrics(majority_sub["gold_label"].tolist(), majority_sub["pred_label"].tolist())
    print_metrics("MAJORITY VOTE ACROSS PASSES", majority_metrics)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output_dir / f"baseline_scored_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "source_results_file": str(args.results),
                "source_meta": meta,
                "per_pass_metrics": per_pass_metrics,
                "averaged_across_passes": averaged,
                "majority_vote_metrics": majority_metrics,
            },
            f,
            indent=2,
        )
    print(f"\nWrote scored summary to {out_path}")


if __name__ == "__main__":
    main()
