from datetime import datetime
import json
import logging
from pathlib import Path

import pandas as pd

from config import BASE_DIR, MODEL_VERSION, RISK_BANDS, WEIGHTS


SNAPSHOT_VERSION = 1
DEFAULT_SNAPSHOT_PATH = (
    BASE_DIR / "data" / "processed" / "portfolio_assessments_v1.json"
)
REQUIRED_RECORD_FIELDS = {
    "site_id",
    "site_name",
    "latitude",
    "longitude",
    "flood_score",
    "deprivation_score",
    "temperature_risk_current",
    "temperature_risk_forecast",
    "current_temperature_c",
    "forecast_temperature_c",
    "current_overall_score",
    "forecast_overall_score",
    "current_risk_category",
    "forecast_risk_category",
    "calculated_at",
    "weather_retrieved_at",
    "model_version",
    "data_status",
}
LOGGER = logging.getLogger(__name__)
VALID_DATA_STATUSES = {"stored-baseline"}


def load_snapshot(path: Path = DEFAULT_SNAPSHOT_PATH) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"snapshot_version": SNAPSHOT_VERSION, "assessments": {}}
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid portfolio assessment snapshot: {path.name}") from exc
    if payload.get("snapshot_version") != SNAPSHOT_VERSION:
        raise ValueError("Unsupported portfolio assessment snapshot version")
    assessments = payload.get("assessments")
    if not isinstance(assessments, dict):
        raise ValueError("Portfolio assessment snapshot has no mode collections")
    return payload


def validate_record(record: dict) -> None:
    missing = REQUIRED_RECORD_FIELDS - set(record)
    if missing:
        raise ValueError(f"Assessment record missing fields: {sorted(missing)}")
    numeric = {}
    for field in (
        "latitude",
        "longitude",
        "flood_score",
        "deprivation_score",
        "temperature_risk_current",
        "temperature_risk_forecast",
        "current_temperature_c",
        "forecast_temperature_c",
        "current_overall_score",
        "forecast_overall_score",
    ):
        numeric[field] = float(record[field])
    if not str(record["site_id"]).strip():
        raise ValueError("Assessment record has an empty site_id")
    if record["model_version"] != MODEL_VERSION:
        raise ValueError("Assessment record model version does not match the app")
    if record["data_status"] not in VALID_DATA_STATUSES:
        raise ValueError("Assessment record has an invalid data status")
    if not -90 <= numeric["latitude"] <= 90 or not -180 <= numeric["longitude"] <= 180:
        raise ValueError("Assessment record has invalid coordinates")
    for field in (
        "flood_score",
        "deprivation_score",
        "temperature_risk_current",
        "temperature_risk_forecast",
        "current_overall_score",
        "forecast_overall_score",
    ):
        if not 0 <= numeric[field] <= 100:
            raise ValueError(f"Assessment record has invalid {field}")
    for field in ("calculated_at", "weather_retrieved_at"):
        try:
            datetime.fromisoformat(str(record[field]).replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Assessment record has invalid {field}") from exc

    for suffix in ("current", "forecast"):
        expected_score = round(
            numeric["flood_score"] * WEIGHTS["flood"]
            + numeric[f"temperature_risk_{suffix}"] * WEIGHTS["temperature"]
            + numeric["deprivation_score"] * WEIGHTS["deprivation"],
            4,
        )
        actual_score = numeric[f"{suffix}_overall_score"]
        if abs(expected_score - actual_score) > 1e-4:
            raise ValueError(f"Assessment record has inconsistent {suffix} score")
        expected_band = next(
            (
                name
                for name, (minimum, maximum) in RISK_BANDS.items()
                if minimum <= actual_score <= maximum
            ),
            "unknown",
        )
        if record[f"{suffix}_risk_category"] != expected_band:
            raise ValueError(f"Assessment record has inconsistent {suffix} risk")


def validate_snapshot(payload: dict, expected_ids_by_mode=None) -> None:
    if payload.get("snapshot_version") != SNAPSHOT_VERSION:
        raise ValueError("Invalid snapshot version")
    assessments = payload.get("assessments")
    if not isinstance(assessments, dict):
        raise ValueError("Invalid assessment collections")
    for mode, records in assessments.items():
        if not isinstance(records, list):
            raise ValueError(f"Invalid {mode} assessment collection")
        ids = []
        for record in records:
            validate_record(record)
            ids.append(str(record["site_id"]))
        if len(ids) != len(set(ids)):
            raise ValueError(f"Duplicate site_id in {mode} assessments")
        if expected_ids_by_mode and mode in expected_ids_by_mode:
            expected = {str(value) for value in expected_ids_by_mode[mode]}
            if set(ids) != expected:
                raise ValueError(f"{mode} assessment IDs do not match the dataset")


def snapshot_validation_summary(payload: dict, stations: pd.DataFrame, mode: str) -> dict:
    records = payload.get("assessments", {}).get(mode, [])
    source_by_id = {
        str(row["station_id"]): row for _, row in stations.iterrows()
    }
    seen = set()
    duplicates = 0
    matched = 0
    invalid_scores = 0
    valid_current_scores = []
    for record in records:
        site_id = str(record.get("site_id", ""))
        if site_id in seen:
            duplicates += 1
        seen.add(site_id)
        source = source_by_id.get(site_id)
        if source is not None:
            matched += 1
        try:
            validate_record(record)
            if source is None:
                raise ValueError("site ID is absent from source")
            if (
                abs(float(record["latitude"]) - float(source["latitude"])) > 1e-6
                or abs(float(record["longitude"]) - float(source["longitude"])) > 1e-6
            ):
                raise ValueError("coordinates do not match source")
            valid_current_scores.append(float(record["current_overall_score"]))
        except (TypeError, ValueError):
            invalid_scores += 1
    missing = set(source_by_id) - seen
    return {
        "record_count": len(records),
        "matched_site_count": matched,
        "missing_site_count": len(missing),
        "duplicate_count": duplicates,
        "invalid_score_count": invalid_scores,
        "average_current_score": (
            round(sum(valid_current_scores) / len(valid_current_scores), 2)
            if valid_current_scores
            else None
        ),
    }


def score_result_from_record(record: dict, forecast: bool = False) -> dict:
    suffix = "forecast" if forecast else "current"
    temperature_score = float(record[f"temperature_risk_{suffix}"])
    flood_score = float(record["flood_score"])
    deprivation_score = float(record["deprivation_score"])
    return {
        "flood_score": flood_score,
        "temperature_score": temperature_score,
        "deprivation_score": deprivation_score,
        "flood_contribution": round(flood_score * WEIGHTS["flood"], 4),
        "temperature_contribution": round(
            temperature_score * WEIGHTS["temperature"], 4
        ),
        "deprivation_contribution": round(
            deprivation_score * WEIGHTS["deprivation"], 4
        ),
        "overall_score": float(record[f"{suffix}_overall_score"]),
        "risk_band": record[f"{suffix}_risk_category"],
        "model_version": record["model_version"],
        "weights": WEIGHTS.copy(),
        "calculated_at": record["calculated_at"],
    }


def assessment_tuple_from_record(record: dict) -> tuple:
    weather = {
        "current_temperature_c": float(record["current_temperature_c"]),
        "forecast_max_temperature_c": [float(record["forecast_temperature_c"])],
        "seven_day_max_temperature_c": float(record["forecast_temperature_c"]),
        "retrieved_at": record["weather_retrieved_at"],
        "source": "Open-Meteo",
        "weather_status": "stored",
        "data_status": record["data_status"],
    }
    return (
        score_result_from_record(record),
        score_result_from_record(record, forecast=True),
        None,
        weather,
    )


def baseline_assessments_for_stations(
    stations: pd.DataFrame,
    mode: str,
    path: Path = DEFAULT_SNAPSHOT_PATH,
) -> dict[str, tuple]:
    payload = load_snapshot(path)
    records = payload.get("assessments", {}).get(mode, [])
    by_id = {str(record.get("site_id")): record for record in records}
    results = {}
    for _, station in stations.iterrows():
        station_id = str(station["station_id"])
        record = by_id.get(station_id)
        if record is None:
            LOGGER.warning("No stored assessment for site_id=%s", station_id)
            continue
        try:
            validate_record(record)
            if (
                abs(float(record["latitude"]) - float(station["latitude"])) > 1e-6
                or abs(float(record["longitude"]) - float(station["longitude"])) > 1e-6
            ):
                raise ValueError("stored coordinates do not match")
            results[station_id] = assessment_tuple_from_record(record)
        except (TypeError, ValueError) as exc:
            LOGGER.warning(
                "Invalid stored assessment for site_id=%s: %s", station_id, exc
            )
    return results
