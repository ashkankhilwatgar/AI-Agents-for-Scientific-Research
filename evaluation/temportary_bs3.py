
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

    scored_df, num_criterion_errors, num_no_gold_label, num_unmatched_variants = build_evaluation_df(
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

