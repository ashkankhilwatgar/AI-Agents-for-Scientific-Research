import json

import pandas as pd
import pytest

from evaluation import question2


@pytest.mark.parametrize(
    "raw_label",
    [
        "vus",
        "VUS",
        "uncertain significance",
        "variant of uncertain significance",
        "Variant of Uncertain Significance",
        "variant of uncertain significance (VUS)",
        "  variant of uncertain significance  ",
    ],
)
def test_normalize_classification_label_accepts_vus_variants(raw_label):
    assert question2.normalize_classification_label(raw_label) == "VUS"


def test_merge_df_scores_long_gold_label_and_vus_prediction_as_a_match():
    variant = "NM_000020_3_c_557G_T"
    predictions = pd.DataFrame(
        [{"variant": variant, "pred_classification": "vus"}]
    )
    gold_answers = pd.DataFrame(
        [
            {
                "variant": variant,
                "gold_classification": "variant of uncertain significance",
            }
        ]
    )

    evaluation_df, num_errors = question2.merge_df(predictions, gold_answers)

    assert num_errors == 0
    assert evaluation_df["gold_classification"].tolist() == ["VUS"]
    assert evaluation_df["pred_classification"].tolist() == ["VUS"]
    assert question2.accuracy_score(
        evaluation_df["gold_classification"],
        evaluation_df["pred_classification"],
    ) == pytest.approx(1.0)

    confusion = question2.confusion_matrix(
        evaluation_df["gold_classification"],
        evaluation_df["pred_classification"],
        labels=question2.LABELS,
    )
    vus_index = question2.LABELS.index("VUS")
    assert confusion.sum() == 1
    assert confusion[vus_index, vus_index] == 1


def test_run_question2_evaluation_treats_equivalent_vus_labels_as_correct(
    tmp_path, monkeypatch
):
    variant = "NM_000020.3:c.557G>T"
    gold_path = tmp_path / "gold.csv"
    summary_path = tmp_path / "batch_summary.json"

    pd.DataFrame(
        [
            {
                "hgvs_cdna": variant,
                "condition": "HHT",
                "gt_classification": "variant of uncertain significance",
                "gt_classification_short": "VUS",
            }
        ]
    ).to_csv(gold_path, index=False)
    summary_path.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "variant": variant,
                        "status": "success",
                        "classification": "vus",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    printed_results = {}
    saved_results = {}
    monkeypatch.setattr(
        question2,
        "print_results",
        lambda **kwargs: printed_results.update(kwargs),
    )
    monkeypatch.setattr(
        question2,
        "save_results",
        lambda **kwargs: saved_results.update(kwargs),
    )

    question2.run_question2_evaluation(
        str(gold_path),
        str(summary_path),
        str(tmp_path / "evaluation-output"),
    )

    assert printed_results["accuracy"] == pytest.approx(1.0)
    assert printed_results["num_errors"] == 0
    vus_index = question2.LABELS.index("VUS")
    assert printed_results["confusion_matrix"][vus_index, vus_index] == 1

    # The other four fixed classes have no support in this one-row fixture, so
    # sklearn assigns each of them zero before taking the five-class macro mean.
    # This low macro score does not mean that the VUS prediction was incorrect.
    assert printed_results["precision"] == pytest.approx(0.2)
    assert printed_results["recall"] == pytest.approx(0.2)
    assert printed_results["f1_score"] == pytest.approx(0.2)

    assert saved_results["accuracy"] == pytest.approx(1.0)
    assert saved_results["classification_report"]["VUS"]["support"] == 1.0


@pytest.mark.parametrize("raw_label", [None, "", "not a classification"])
def test_normalize_classification_label_rejects_unknown_labels(raw_label):
    with pytest.raises(ValueError):
        question2.normalize_classification_label(raw_label)
