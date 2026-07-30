"""Explicitly regenerate the persistent AIRIS portfolio assessment snapshot."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import MODEL_VERSION, OPEN_METEO_TIMEOUT
from data_loader import load_stations
from portfolio_assessments import (
    DEFAULT_SNAPSHOT_PATH,
    SNAPSHOT_VERSION,
    load_snapshot,
    validate_snapshot,
)
from scoring import compute_scores
from weather_service import OPEN_METEO_ENDPOINT, rounded_coordinates


def fetch_weather_batches(stations_by_mode: dict, batch_size: int = 25) -> dict:
    unique_coordinates = []
    seen = set()
    for stations in stations_by_mode.values():
        for _, station in stations.iterrows():
            coordinate = rounded_coordinates(
                station["latitude"], station["longitude"]
            )
            if coordinate not in seen:
                seen.add(coordinate)
                unique_coordinates.append(coordinate)

    weather_by_coordinate = {}
    with requests.Session() as session:
        for start in range(0, len(unique_coordinates), batch_size):
            batch = unique_coordinates[start : start + batch_size]
            response = session.get(
                OPEN_METEO_ENDPOINT,
                params={
                    "latitude": ",".join(str(item[0]) for item in batch),
                    "longitude": ",".join(str(item[1]) for item in batch),
                    "current_weather": "true",
                    "daily": "temperature_2m_max",
                    "forecast_days": 7,
                    "timezone": "Europe/London",
                },
                timeout=OPEN_METEO_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            payloads = payload if isinstance(payload, list) else [payload]
            if len(payloads) != len(batch):
                raise ValueError("Open-Meteo batch response count does not match")
            for coordinate, item in zip(batch, payloads):
                current = float(item["current_weather"]["temperature"])
                maxima = [
                    float(value)
                    for value in item["daily"]["temperature_2m_max"][:7]
                ]
                if len(maxima) != 7:
                    raise ValueError("Incomplete seven-day weather batch response")
                weather_by_coordinate[coordinate] = {
                    "current_temperature_c": current,
                    "forecast_temperature_c": max(maxima),
                }
    return weather_by_coordinate


def existing_records_by_key(payload: dict) -> dict:
    return {
        (mode, str(record["site_id"])): record
        for mode, records in payload.get("assessments", {}).items()
        for record in records
    }


def build_snapshot(
    stations_by_mode: dict,
    weather_by_coordinate: dict,
    existing_payload: dict | None = None,
    generated_at: str | None = None,
) -> dict:
    timestamp = generated_at or datetime.now(timezone.utc).isoformat()
    previous = existing_records_by_key(existing_payload or {})
    assessments = {}
    for mode, stations in stations_by_mode.items():
        records = []
        for _, station in stations.iterrows():
            station_id = str(station["station_id"])
            coordinate = rounded_coordinates(
                station["latitude"], station["longitude"]
            )
            weather = weather_by_coordinate.get(coordinate)
            if weather is None:
                old = previous.get((mode, station_id))
                if old is None:
                    raise ValueError(
                        f"No refreshed or stored assessment for {mode}:{station_id}"
                    )
                records.append(old)
                continue
            current = compute_scores(
                station["flood_score"],
                weather["current_temperature_c"],
                station["deprivation_score"],
            )
            forecast = compute_scores(
                station["flood_score"],
                weather["forecast_temperature_c"],
                station["deprivation_score"],
            )
            records.append(
                {
                    "site_id": station_id,
                    "site_name": str(station["station_name"]),
                    "latitude": float(station["latitude"]),
                    "longitude": float(station["longitude"]),
                    "flood_score": float(station["flood_score"]),
                    "deprivation_score": float(station["deprivation_score"]),
                    "temperature_risk_current": current["temperature_score"],
                    "temperature_risk_forecast": forecast["temperature_score"],
                    "current_temperature_c": weather["current_temperature_c"],
                    "forecast_temperature_c": weather["forecast_temperature_c"],
                    "current_overall_score": current["overall_score"],
                    "forecast_overall_score": forecast["overall_score"],
                    "current_risk_category": current["risk_band"],
                    "forecast_risk_category": forecast["risk_band"],
                    "calculated_at": timestamp,
                    "weather_retrieved_at": timestamp,
                    "model_version": MODEL_VERSION,
                    "data_status": "stored-baseline",
                }
            )
        assessments[mode] = records
    return {
        "snapshot_version": SNAPSHOT_VERSION,
        "generated_at": timestamp,
        "model_version": MODEL_VERSION,
        "assessments": assessments,
    }


def write_snapshot_atomically(payload: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_path, output_path)


def refresh_snapshot(output_path: Path, batch_size: int = 25) -> dict:
    stations_by_mode = {
        "sample": load_stations(mode="sample"),
        "verified": load_stations(mode="verified"),
    }
    existing = load_snapshot(output_path) if output_path.exists() else None
    weather = fetch_weather_batches(stations_by_mode, batch_size=batch_size)
    payload = build_snapshot(stations_by_mode, weather, existing_payload=existing)
    validate_snapshot(
        payload,
        {
            mode: stations["station_id"].astype(str).tolist()
            for mode, stations in stations_by_mode.items()
        },
    )
    write_snapshot_atomically(payload, output_path)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_SNAPSHOT_PATH)
    parser.add_argument("--batch-size", type=int, default=25)
    args = parser.parse_args()
    payload = refresh_snapshot(args.output, batch_size=args.batch_size)
    counts = {
        mode: len(records) for mode, records in payload["assessments"].items()
    }
    print(f"Wrote {args.output}: {counts}")


if __name__ == "__main__":
    main()
