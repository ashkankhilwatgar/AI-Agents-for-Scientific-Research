import sys
import os
from pathlib import Path
import csv
import json
import re

HHT_CRITERIA = ["PM2", "PP3", "BP4", "BA1", "BP7", "BS1", "PVS1", "PM4", "PM1", "PS1", "PM5", "PS4", "BS3", "PS3"]
def find_project_root(start: Path) -> Path:
    for dir in (start, *start.parents):
        if (dir/"evaluation/question1.py").is_file():
            return dir
    raise RuntimeError("Could not locate the project root")

root_directory = find_project_root(Path.cwd().resolve())
sys.path.insert(0, str(root_directory))

from evaluation.question2 import load_gold_answer_df, load_predictions, merge_df
from evaluation.question1 import normalize_criterion_name
from pipeline import HHT_CRITERIA

def load_prediction_criterions(
        variant: str,
        batch_summary_path: str
) -> list[str]:
    if not isinstance(variant, str) or not variant.strip():
        raise ValueError("Incorrect varaint name")

    batch_summary = Path(batch_summary_path)
    if not batch_summary.exists():
        raise FileNotFoundError(f"Could not find batch summary at {batch_summary_path}")

    try:
        with open(str(batch_summary), "r", encoding="utf-8") as f:
            payload = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"batch summary is not valid json") from e

    results = payload.get("results")

    if results is None or not isinstance(results, list):
        raise ValueError("Batch summary has not results list")

    matches = [
        result 
        for result in results
        if isinstance(result, dict)
        and result.get("variant") == variant
    ]

    if not matches:
        raise ValueError(f"Cannot found prediction results for variant {variant}")

    if len(matches) > 1:
        raise ValueError(f"Found overlapping predictions for variant {variant}")

    prediction_path = matches[0].get("file")

    if not isinstance(prediction_path, str) or not prediction_path.strip():
        raise FileNotFoundError(f"Prediction json for variant {variant} is missing")

    prediction_path = root_directory / prediction_path

    prediction_file = Path(prediction_path)
    if not prediction_file.exists():
        raise FileNotFoundError(f"Could not found predictions file at {prediction_path}")

    try:
        with open(str(prediction_file), "r", encoding="utf-8") as f:
            payload = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Prediction Output is not valid json"
        ) from e

    results = payload.get("results")

    if results is None or not isinstance(results, list):
        raise ValueError(f"Prediction output has no valid results list")

    applied_criteria = []

    for i, result in enumerate(results):
        if not isinstance(result, dict):
            print(
                f"Warning: one criterion prediction for variant {variant} is not a valid dict"
            )
            continue

        if result.get("status") != "complete":
            continue

        if result.get("applies"):
            criterion  = result.get("criterion", "")

            if not isinstance(criterion, str) or not criterion.strip():
                raise ValueError(f"Applied result {i} has no valid criterion in {prediction_path}")

            # strength = result.get("applied_strength", "")
            # if not isinstance(strength, str) or not strength.strip():
            #     raise ValueError(f"Applied result {i} has an invalid strength in {prediction_path}")

            # normalized_strength = normalize_criterion_name(strength)
            # if not criterion.endswith(f"_{normalized_strength}"):
            #     criterion = f"{criterion}_{normalized_strength}"

            applied_criteria.append(criterion.split("_")[0])

    return applied_criteria   

def restore_hgvs(value: str) -> str:
    """
    Convert a filename-safe variant string into HGVS notation.

    Examples:
        NM_000020_3_c_557G_T
            -> NM_000020.3:c.557G>T

        NM_001114753_3_c_1701del
            -> NM_001114753.3:c.1701del
    """
    pattern = (
        r"^(?P<accession>[A-Za-z]+_\d+)_"
        r"(?P<version>\d+)_"
        r"(?P<coordinate_type>[cgnmrp])_"
        r"(?P<variant>.+)$"
    )

    match = re.fullmatch(pattern, value)

    if match is None:
        raise ValueError(f"Unsupported encoded HGVS format: {value}")

    accession = match.group("accession")
    version = match.group("version")
    coordinate_type = match.group("coordinate_type")
    variant = match.group("variant")

    # Restore substitutions such as 557G_T -> 557G>T.
    substitution_pattern = r"^(.+[A-Za-z*])_([A-Za-z*]+)$"
    substitution_match = re.fullmatch(substitution_pattern, variant)

    if substitution_match is not None:
        reference_part, alternate = substitution_match.groups()
        variant = f"{reference_part}>{alternate}"

    return f"{accession}.{version}:{coordinate_type}.{variant}"


def load_gold_predictions(gold_answer_path: str, variant: str) -> list:
    gold_answer_csv = Path(gold_answer_path)
    if not gold_answer_csv.exists():
        raise FileNotFoundError(
            f"Could not found gold answer csv at {gold_answer_path}"
        )

    gold_criterions = []

    with open(str(gold_answer_csv), "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        if "hgvs_cdna" not in reader.fieldnames or "gt_criteria_applied" not in reader.fieldnames:
            raise FileNotFoundError("The provided csv file does not have variant name and applied criterias")

        matches = []
        for row in reader:
            variant_name = row.get("hgvs_cdna", "")
            if not isinstance(variant_name, str) or not variant_name.strip():
                continue

            if variant_name == variant:
                applied_criteria = [criterion.upper().split("_")[0] for criterion in row["gt_criteria_applied"].split(";")]
                matches.append(applied_criteria)

        if not matches:
            raise ValueError(
                f"No matching variant in gold csv for variant {variant}"
            )

        print(f"{"=" * 100}")
        print("MATCHES", matches)
        print(f"{"=" * 100}")

        if len(matches) > 1:
            raise ValueError(
                f"Duplicate matches for variant {variant} in golden csv"
            )

        gold_criterions.append(matches)

    return gold_criterions[0][0]


# def load_actual_predictions(variant: str, gold_csv: str) -> str:
#     if not isinstance(variant, str) or not variant.strip():
#         raise ValueError("Invalid Variant Name")

if __name__ == "__main__":
    gold_csv = root_directory / "datasets/applied_only_evaluation_dataset.csv"
    predictions_json =root_directory / "outputs/batch_20260729_194939/batch_summary.json"

    gold_answer = load_gold_answer_df(str(gold_csv))
    predictions = load_predictions(str(predictions_json))
    final_df = merge_df(predictions, gold_answer)[0]

    final_df = final_df[final_df["pred_classification"] != final_df["gold_classification"]]

    final_df["variant"] = final_df["variant"].apply(restore_hgvs)

    final_df["criteria_predictions"] = final_df.apply(
        lambda row: load_prediction_criterions(
            row["variant"],
            str(predictions_json),
        ),
        axis = 1,
    )

    final_df["gold_criteria"] = final_df.apply(
        lambda row: load_gold_predictions(
            str(gold_csv),
            row["variant"]
        ),
        axis = 1
    )

    final_df = final_df[["variant", "criteria_predictions", "gold_criteria"]]

    final_df["extra_criteria"] = final_df.apply(
        lambda row: [criteria for criteria in row["gold_criteria"] if criteria not in row["criteria_predictions"]],
        axis = 1
    )

    final_df["automatable_criteria"] = final_df.apply(
        lambda row: [criteria for criteria in row["extra_criteria"] if criteria in HHT_CRITERIA],
        axis = 1
    )

    final_df["non_automatable_criteria"] = final_df.apply(
        lambda row: [criteria for criteria in row["extra_criteria"] if criteria not in HHT_CRITERIA],
        axis = 1
    )

    final_df["additional_predictions"] = final_df.apply(
        lambda row: [criteria for criteria in row["criteria_predictions"] if criteria not in row["gold_criteria"]],
        axis = 1
    )

    # df1: final-classification errors with no criteria predicted beyond the gold list.
    no_additional_predictions_df = final_df[
        final_df["additional_predictions"].map(lambda criteria: not criteria)
    ].copy()

    # df2: df1 rows with no missing automatable criteria.
    no_automatable_missing_criteria_df = no_additional_predictions_df[
        no_additional_predictions_df["automatable_criteria"].map(lambda criteria: not criteria)
    ].copy()

    # df3: df1 rows with at least one missing non-automatable criterion.
    with_non_automatable_missing_criteria_df = no_additional_predictions_df[
        no_additional_predictions_df["non_automatable_criteria"].map(bool)
    ].copy()

    # df4: df1 rows that appear in neither df2 nor df3. These have missing
    # automatable criteria only.
    automatable_only_missing_criteria_df = no_additional_predictions_df.loc[
        ~no_additional_predictions_df.index.isin(no_automatable_missing_criteria_df.index)
        & ~no_additional_predictions_df.index.isin(with_non_automatable_missing_criteria_df.index)
    ].copy()