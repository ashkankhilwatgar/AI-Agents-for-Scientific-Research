import json

import pandas as pd

from evaluation import question1, question3


def _gold_df(variants):
    return pd.DataFrame(
        [
            {
                "variant": variant,
                "disease": "HHT",
                "gold_classification_short": "LP",
            }
            for variant in variants
        ]
    )


def test_run_single_mode_writes_pipeline_compatible_batch_outputs(tmp_path, monkeypatch):
    successful_variant = "NM_000020.3:c.1A>G"
    failed_variant = "NM_000020.3:c.2A>G"
    criterion_results = [
        {
            "criterion": "PM2_SUPPORTING",
            "status": "complete",
            "applies": True,
        }
    ]
    scoring = {
        "classification": "Likely Pathogenic",
        "rule_matched": "test rule",
    }

    def fake_run(variant, disease, mode):
        assert disease == "HHT"
        assert mode == "no_judge"
        if variant == failed_variant:
            raise RuntimeError("test failure")
        return criterion_results, scoring

    monkeypatch.setattr(question3, "run_pipeline_ablation", fake_run)
    mode_dir = tmp_path / "ablation_no_judge_TEST"

    predictions = question3.run_single_mode(
        _gold_df([successful_variant, failed_variant]),
        "no_judge",
        mode_output_dir=mode_dir,
        gold_csv_path="gold.csv",
    )

    assert predictions == [
        {"variant": successful_variant, "gold": "LP", "pred": "LP"},
        {"variant": failed_variant, "gold": "LP", "pred": "ERROR"},
    ]

    variant_path = mode_dir / "NM_000020_3_c_1A_G_HHT.json"
    variant_payload = json.loads(variant_path.read_text(encoding="utf-8"))
    assert variant_payload["variant"] == successful_variant
    assert variant_payload["classification"] == "Likely Pathogenic"
    assert variant_payload["scoring"] == scoring
    assert variant_payload["results"] == criterion_results

    error_path = mode_dir / "NM_000020_3_c_2A_G_HHT.error.json"
    error_payload = json.loads(error_path.read_text(encoding="utf-8"))
    assert error_payload["status"] == "error"
    assert error_payload["error"] == "RuntimeError: test failure"

    batch_summary = json.loads(
        (mode_dir / "batch_summary.json").read_text(encoding="utf-8")
    )
    assert batch_summary["csv"] == "gold.csv"
    assert batch_summary["total"] == 2
    assert batch_summary["completed"] == 2
    assert [result["status"] for result in batch_summary["results"]] == [
        "ok",
        "error",
    ]

    # Question 1 can consume the generated directory without special handling.
    criterion_df, num_variant_errors = question1.load_criterion_predictions(
        str(mode_dir / "batch_summary.json")
    )
    assert num_variant_errors == 1
    assert criterion_df[["criterion", "pred_applies"]].to_dict("records") == [
        {"criterion": "PM2", "pred_applies": True}
    ]


def test_full_ablation_run_creates_one_batch_folder_per_mode(tmp_path, monkeypatch):
    variant = "NM_000020.3:c.3A>G"
    gold_df = _gold_df([variant])
    monkeypatch.setattr(question3, "load_gold_df", lambda _: gold_df)
    monkeypatch.setattr(
        question3,
        "run_pipeline_ablation",
        lambda variant, disease, mode: (
            [{"criterion": "PS1", "status": "complete", "applies": mode == "full"}],
            {"classification": "Likely Pathogenic", "rule_matched": mode},
        ),
    )

    artifacts = question3.run_question3_evaluation(
        gold_csv_path="gold.csv",
        variant_ids=None,
        output_dir=str(tmp_path),
        run_id="TEST",
    )

    summary_path = tmp_path / "ablation_summary_TEST.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert artifacts["summary"] == str(summary_path)
    assert set(summary["modes"]) == set(question3.ABLATION_MODES)
    assert set(summary["mode_batch_summaries"]) == set(question3.ABLATION_MODES)

    for mode in question3.ABLATION_MODES:
        mode_dir = tmp_path / f"ablation_{mode}_TEST"
        assert (mode_dir / "batch_summary.json").is_file()
        assert (mode_dir / "NM_000020_3_c_3A_G_HHT.json").is_file()
        assert summary["mode_output_dirs"][mode] == str(mode_dir)
        assert summary["mode_batch_summaries"][mode] == str(
            mode_dir / "batch_summary.json"
        )
