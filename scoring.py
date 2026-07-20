from datetime import datetime, timezone
from typing import Any, Dict

from config import MODEL_VERSION, RISK_BANDS, TEMPERATURE_THRESHOLDS, WEIGHTS


def _validate_score(value: Any, name: str) -> float:
    try:
        score = float(value)
    except Exception:
        raise TypeError(f"{name} must be numeric (got {type(value).__name__})")
    if score < 0 or score > 100:
        raise ValueError(f"{name} must be between 0 and 100 (got {score})")
    return score


def temperature_c_to_risk_score(temp_c: float) -> int:
    if temp_c is None:
        raise TypeError("temperature must be provided")
    try:
        temperature = float(temp_c)
    except Exception:
        raise TypeError("temperature must be numeric")
    if temperature < -50 or temperature > 60:
        raise ValueError("temperature value appears unrealistic")

    cold = TEMPERATURE_THRESHOLDS.get("cold", 20)
    warm = TEMPERATURE_THRESHOLDS.get("warm", 25)
    hot = TEMPERATURE_THRESHOLDS.get("hot", 30)
    very_hot = TEMPERATURE_THRESHOLDS.get("very_hot", 35)

    if temperature < cold:
        return 10
    if temperature < warm:
        return 25
    if temperature < hot:
        return 50
    if temperature < very_hot:
        return 75
    return 100


def classify_score(score: float) -> str:
    numeric_score = float(score)
    for name, (minimum, maximum) in RISK_BANDS.items():
        if minimum <= numeric_score <= maximum:
            return name
    return "unknown"


def compute_scores(
    flood_score: Any, temperature_c: Any, deprivation_score: Any
) -> Dict[str, Any]:
    flood = _validate_score(flood_score, "flood_score")
    temperature_score = temperature_c_to_risk_score(temperature_c)
    deprivation = _validate_score(deprivation_score, "deprivation_score")

    flood_contribution = round(flood * WEIGHTS.get("flood", 0.0), 4)
    temperature_contribution = round(
        float(temperature_score) * WEIGHTS.get("temperature", 0.0), 4
    )
    deprivation_contribution = round(
        deprivation * WEIGHTS.get("deprivation", 0.0), 4
    )
    overall = round(
        flood_contribution + temperature_contribution + deprivation_contribution, 4
    )

    return {
        "flood_score": flood,
        "temperature_score": temperature_score,
        "deprivation_score": deprivation,
        "flood_contribution": flood_contribution,
        "temperature_contribution": temperature_contribution,
        "deprivation_contribution": deprivation_contribution,
        "overall_score": overall,
        "risk_band": classify_score(overall),
        "model_version": MODEL_VERSION,
        "weights": WEIGHTS.copy(),
        "calculated_at": datetime.now(timezone.utc).isoformat(),
    }
