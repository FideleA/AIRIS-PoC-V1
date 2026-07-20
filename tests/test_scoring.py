import pytest

from scoring import (
    _validate_score,
    temperature_c_to_risk_score,
    compute_scores,
    classify_score,
)
from config import WEIGHTS


def test_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_temperature_conversion_boundaries_and_levels():
    assert temperature_c_to_risk_score(19.9) == 10
    assert temperature_c_to_risk_score(20) == 25
    assert temperature_c_to_risk_score(22.5) == 25
    assert temperature_c_to_risk_score(25) == 50
    assert temperature_c_to_risk_score(27.5) == 50
    assert temperature_c_to_risk_score(30) == 75
    assert temperature_c_to_risk_score(33.0) == 75
    assert temperature_c_to_risk_score(35) == 100
    assert temperature_c_to_risk_score(40) == 100


def test_compute_scores_example_and_contributions():
    # Example from user: flood 70, temperature 40C, deprivation 50
    res = compute_scores(70, 40, 50)
    # temperature 40 -> risk score 100
    assert res["temperature_score"] == 100
    # contributions
    assert res["flood_contribution"] == pytest.approx(70 * WEIGHTS["flood"])
    assert res["temperature_contribution"] == pytest.approx(100 * WEIGHTS["temperature"])
    assert res["deprivation_contribution"] == pytest.approx(50 * WEIGHTS["deprivation"])
    # overall
    expected_overall = round(
        70 * WEIGHTS["flood"] + 100 * WEIGHTS["temperature"] + 50 * WEIGHTS["deprivation"],
        4,
    )
    assert res["overall_score"] == pytest.approx(expected_overall)


def test_invalid_scores_out_of_range_and_non_numeric():
    with pytest.raises(ValueError):
        _validate_score(-1, "flood")
    with pytest.raises(ValueError):
        _validate_score(101, "flood")
    with pytest.raises(TypeError):
        _validate_score("abc", "flood")


def test_risk_band_boundaries():
    # Use classify_score directly for boundaries
    from config import RISK_BANDS

    for name, (mn, mx) in RISK_BANDS.items():
        assert classify_score(mn) == name
        assert classify_score(mx) == name

    # Ensure configured boundary values classify to the expected bands
    assert classify_score(20.0) == "very_low"
    assert classify_score(21.0) == "low"
    assert classify_score(40.0) == "low"
    assert classify_score(41.0) == "medium"
    assert classify_score(70.0) == "medium"
    assert classify_score(71.0) == "high"
    assert classify_score(90.0) == "high"
    assert classify_score(91.0) == "very_high"
