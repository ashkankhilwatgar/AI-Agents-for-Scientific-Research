# test_variant_utils.py

from case_studies.jul_27.error_analysis import restore_hgvs, load_gold_predictions
import pytest

@pytest.fixture
def gold_csv(tmp_path):
    path = tmp_path / "gold_answers.csv"

    path.write_text(
        "hgvs_cdna,gt_criteria_applied\n"
        "NM_000020.3:c.557G>T,PM2_Supporting;PP3\n",
        encoding="utf-8"
    )

    return path

def test_restore_hgvs_substitution():
    # Arrange: prepare the input and expected result
    encoded_variant = "NM_000020_3_c_557G_T"
    expected_result = "NM_000020.3:c.557G>T"

    # Act: call the function
    actual_result = restore_hgvs(encoded_variant)

    # Assert: check whether the result is correct
    assert actual_result == expected_result


def test_restore_hgvs_deletion():
    # Arrange
    encoded_variant = "NM_001114753_3_c_1701del"
    expected_result = "NM_001114753.3:c.1701del"

    # Act
    actual_result = restore_hgvs(encoded_variant)

    # Assert
    assert actual_result == expected_result

def test_invalid_variant():
    # Arrange
    invalid_variant = "invalid_variant"

    with pytest.raises(ValueError):
        restore_hgvs(invalid_variant)

def test_load_gold_answer_df(gold_csv):
    # # Arrange
    # csv_file = tmp_path / "gold_answers.csv"

    # csv_file.write_text(
    #     "hgvs_cdna,gt_criteria_applied\n"
    #     "NM_000020.3:c.557G>T,PM2_Supporting;PP3\n",
    #     encoding="utf-8"
    # )

    # Act
    result = load_gold_predictions(
        gold_answer_path=str(gold_csv),
        variant="NM_000020.3:c.557G>T"
    )

    # Assert
    assert result == ["PM2", "PP3"]


def test_missing_variant(tmp_path):
    # Arrange 
    csv_file = tmp_path / "gold_answer.csv"
    csv_file.write_text(
        "hgvs_cdna,gt_criteria_applied\n"
        "NM_000020.3:c.557G>T,PM2_Supporting;PP3\n",
        encoding="utf-8"
    )

    # Act
    with pytest.raises(
        expected_exception=ValueError,
        match="No matching variant"
    ):
        result = load_gold_predictions(
            gold_answer_path=str(csv_file),
            variant="NM_001114753.3:c.1517T>A"
        )

def test_load_gold_criterion_missing_file(tmp_path):
    # Arrange
    csv_file = tmp_path / "gold_answers.csv"

    with pytest.raises(FileNotFoundError):
        result = load_gold_predictions(
            gold_answer_path=str(csv_file),
            variant="NM_001114753.3:c.1517T>A"
        )
