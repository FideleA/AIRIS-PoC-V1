from typing import Dict, Any
from datetime import datetime, timezone

from config import WEIGHTS, MODEL_VERSION, RISK_BANDS, TEMPERATURE_THRESHOLDS


def _validate_score(value: Any, name: str) -> float:
    """Validate that a value is numeric and within 0..100. Returns float.

    Raises ValueError for invalid inputs.
    """
    try:
        v = float(value)
    except Exception:
        raise TypeError(f"{name} must be numeric (got {type(value).__name__})")
    if v < 0 or v > 100:
        raise ValueError(f"{name} must be between 0 and 100 (got {v})")
    return v


def temperature_c_to_risk_score(temp_c: float) -> int:
    """Convert a maximum temperature in Celsius to a 0-100 illustrative risk score.

    Uses thresholds defined in `config.TEMPERATURE_THRESHOLDS`.
    Returns one of the illustrative scores: 10,25,50,75,100.
    """
    if temp_c is None:
        raise TypeError("temperature must be provided")
    try:
        t = float(temp_c)
    except Exception:
        raise TypeError("temperature must be numeric")
    # sanity check
    if t < -50 or t > 60:
        raise ValueError("temperature value appears unrealistic")

    cold = TEMPERATURE_THRESHOLDS.get("cold", 20)
    warm = TEMPERATURE_THRESHOLDS.get("warm", 25)
    hot = TEMPERATURE_THRESHOLDS.get("hot", 30)
    very_hot = TEMPERATURE_THRESHOLDS.get("very_hot", 35)

    if t < cold:
        return 10
    if t < warm:
        return 25
    if t < hot:
        return 50
    if t < very_hot:
        return 75
    return 100


def classify_score(score: float) -> str:
    """Return the risk band name for a score using `config.RISK_BANDS`.

    Bands are expected as dict of name -> (min_inclusive, max_inclusive).
    """
    s = float(score)
    for name, (mn, mx) in RISK_BANDS.items():
        if mn <= s <= mx:
            return name
    return "unknown"


def compute_scores(
    flood_score: Any, temperature_c: Any, deprivation_score: Any
) -> Dict[str, Any]:
    """Compute factor contributions and overall AIRIS score.

    Args:
        flood_score: flood score [0..100]
        temperature_c: temperature in Celsius (converted to 0..100 risk)
        deprivation_score: deprivation score [0..100]

    Returns dict with factor scores, contributions, overall score, risk band,
    model version and weights used.
    """
    f = _validate_score(flood_score, "flood_score")
    temp_c = temperature_c
    temp_score = temperature_c_to_risk_score(temp_c)
    d = _validate_score(deprivation_score, "deprivation_score")

    w_f = WEIGHTS.get("flood", 0.0)
    w_t = WEIGHTS.get("temperature", 0.0)
    w_d = WEIGHTS.get("deprivation", 0.0)

    f_contrib = round(f * w_f, 4)
    t_contrib = round(float(temp_score) * w_t, 4)
    d_contrib = round(d * w_d, 4)

    overall = round(f_contrib + t_contrib + d_contrib, 4)

    band = classify_score(overall)

    return {
        "flood_score": f,
        "temperature_score": temp_score,
        "deprivation_score": d,
        "flood_contribution": f_contrib,
        "temperature_contribution": t_contrib,
        "deprivation_contribution": d_contrib,
        "overall_score": overall,
        "risk_band": band,
        "model_version": MODEL_VERSION,
        "weights": WEIGHTS.copy(),
        "calculated_at": datetime.now(timezone.utc).isoformat(),
    }
