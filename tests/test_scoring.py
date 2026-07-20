import pytest

from app import describe_score_change
from config import RISK_BANDS, TEMPERATURE_THRESHOLDS, WEIGHTS
from scoring import classify_score, compute_scores, temperature_c_to_risk_score


def test_factor_weights_total_one():
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)


def test_weighted_score_and_contributions_are_correct():
    result = compute_scores(70, 40, 50)
    assert result["flood_contribution"] == pytest.approx(35)
    assert result["temperature_contribution"] == pytest.approx(30)
    assert result["deprivation_contribution"] == pytest.approx(10)
    assert result["overall_score"] == pytest.approx(75)


def test_contributions_sum_to_overall_score():
    result = compute_scores(55, 27.5, 60)
    contributions = (
        result["flood_contribution"]
        + result["temperature_contribution"]
        + result["deprivation_contribution"]
    )
    assert contributions == pytest.approx(result["overall_score"])


@pytest.mark.parametrize(
    ("flood", "temperature", "deprivation"),
    [(0, -10, 0), (100, 35, 100), (20, 22, 80), (80, 32, 20)],
)
def test_overall_score_remains_between_zero_and_one_hundred(
    flood, temperature, deprivation
):
    score = compute_scores(flood, temperature, deprivation)["overall_score"]
    assert 0 <= score <= 100


def test_risk_category_boundaries_match_configuration():
    for category, (minimum, maximum) in RISK_BANDS.items():
        assert classify_score(minimum) == category
        assert classify_score(maximum) == category


def test_zero_forecast_difference_is_no_change():
    assert describe_score_change(42.0, 42.0) == "No change"


def test_temperature_transformation_lower_threshold():
    assert temperature_c_to_risk_score(TEMPERATURE_THRESHOLDS["cold"]) == 25


def test_temperature_transformation_intermediate_value():
    assert temperature_c_to_risk_score(27.5) == 50


def test_temperature_transformation_upper_threshold():
    assert temperature_c_to_risk_score(TEMPERATURE_THRESHOLDS["very_hot"]) == 100


def test_temperature_transformation_above_upper_threshold():
    assert temperature_c_to_risk_score(40) == 100

