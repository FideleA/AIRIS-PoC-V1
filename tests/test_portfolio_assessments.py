import json
from pathlib import Path
from unittest.mock import Mock

import app
from data_loader import load_stations
from portfolio_assessments import (
    DEFAULT_SNAPSHOT_PATH,
    SNAPSHOT_VERSION,
    baseline_assessments_for_stations,
    load_snapshot,
    snapshot_validation_summary,
    validate_snapshot,
)
from scripts.refresh_portfolio_assessments import (
    build_snapshot,
    write_snapshot_atomically,
)
from weather_service import WeatherServiceError, rounded_coordinates


def live_weather():
    return {
        "current_temperature_c": 19.0,
        "forecast_max_temperature_c": [26.0] * 7,
        "seven_day_max_temperature_c": 26.0,
        "retrieved_at": "2026-07-30T14:00:00+00:00",
        "source": "Open-Meteo",
    }


def datasets():
    return {
        "sample": load_stations(mode="sample"),
        "verified": load_stations(mode="verified"),
    }


def test_snapshot_matches_sample_and_verified_stable_ids():
    stations_by_mode = datasets()
    payload = load_snapshot()
    validate_snapshot(
        payload,
        {
            mode: stations["station_id"].astype(str).tolist()
            for mode, stations in stations_by_mode.items()
        },
    )
    assert len(payload["assessments"]["sample"]) == 10
    assert len(payload["assessments"]["verified"]) == 66
    summary = snapshot_validation_summary(
        payload, stations_by_mode["verified"], "verified"
    )
    assert summary == {
        "record_count": 66,
        "matched_site_count": 66,
        "missing_site_count": 0,
        "duplicate_count": 0,
        "invalid_score_count": 0,
        "average_current_score": 21.17,
    }


def test_initial_results_use_all_baselines_without_weather_calls(monkeypatch):
    provider = Mock()
    monkeypatch.setattr(app, "fetch_open_meteo", provider)
    stations = load_stations(mode="sample")
    baseline = baseline_assessments_for_stations(stations, "sample")
    results = app.results_from_stored_assessments(stations, baseline)
    assert provider.call_count == 0
    assert len(results) == 10
    assert all(result["current"] is not None for result in results)
    assert all(
        app.risk_color(result["current"]["risk_band"]) != "gray"
        for result in results
    )
    assert app.portfolio_metrics(results)["average_current"] is not None


def test_baseline_survives_simulated_process_and_session_restart():
    stations = load_stations(mode="sample")
    first = baseline_assessments_for_stations(stations, "sample")
    del first
    second = baseline_assessments_for_stations(stations, "sample")
    assert len(second) == 10
    assert second["S1"][0]["overall_score"] > 0
    assert second["S1"][3]["weather_status"] == "stored"


def test_selecting_site_needs_at_most_one_provider_call(monkeypatch):
    app._cached_provider_weather.clear()
    store = app.weather_runtime_store()
    with store["lock"]:
        store["last_known"].clear()
    provider = Mock(return_value=live_weather())
    monkeypatch.setattr(app, "fetch_open_meteo", provider)
    station = load_stations(mode="sample").iloc[0]
    refreshed = app.compute_site_scores_safe(station)
    repeated = app.compute_site_scores_safe(station)
    assert provider.call_count == 1
    assert refreshed[0] is not None
    assert repeated[0] is not None


def test_live_result_supplements_stored_marker_assessment(monkeypatch):
    app._cached_provider_weather.clear()
    store = app.weather_runtime_store()
    with store["lock"]:
        store["last_known"].clear()
    monkeypatch.setattr(app, "fetch_open_meteo", Mock(return_value=live_weather()))
    stations = load_stations(mode="sample")
    baseline = baseline_assessments_for_stations(stations, "sample")
    original_calculated_at = baseline["S1"][0]["calculated_at"]
    refreshed = app.compute_site_scores_safe(stations.iloc[0])
    baseline["S1"] = app.retain_stored_assessment_on_failure(
        refreshed, baseline["S1"]
    )
    assert baseline["S1"][3]["weather_status"] == "live"
    assert baseline["S1"][0]["calculated_at"] != original_calculated_at


def test_provider_failure_does_not_replace_stored_score(monkeypatch):
    app._cached_provider_weather.clear()
    store = app.weather_runtime_store()
    with store["lock"]:
        store["last_known"].clear()
    monkeypatch.setattr(
        app,
        "fetch_open_meteo",
        Mock(
            side_effect=WeatherServiceError(
                "provider unavailable",
                kind="provider_5xx",
                status_code=503,
            )
        ),
    )
    stations = load_stations(mode="sample")
    stored = baseline_assessments_for_stations(stations, "sample")["S1"]
    failed = app.compute_site_scores_safe(stations.iloc[0], force_refresh=True)
    retained = app.retain_stored_assessment_on_failure(failed, stored)
    assert retained[0]["overall_score"] == stored[0]["overall_score"]
    assert retained[3]["weather_status"] == "stored"
    assert retained[3]["weather_warning"] == "provider unavailable"


def test_missing_one_baseline_does_not_affect_other_sites(tmp_path):
    payload = load_snapshot()
    payload["assessments"]["sample"] = payload["assessments"]["sample"][1:]
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    baseline = baseline_assessments_for_stations(
        load_stations(mode="sample"), "sample", path
    )
    assert "S1" not in baseline
    assert len(baseline) == 9
    assert all(assessment[0] is not None for assessment in baseline.values())


def test_failed_individual_refresh_retains_existing_record():
    stations_by_mode = datasets()
    existing = load_snapshot()
    weather = {}
    for stations in stations_by_mode.values():
        for _, station in stations.iterrows():
            coordinate = rounded_coordinates(
                station["latitude"], station["longitude"]
            )
            weather[coordinate] = {
                "current_temperature_c": 20.0,
                "forecast_temperature_c": 25.0,
            }
    missing_station = stations_by_mode["sample"].iloc[0]
    weather.pop(
        rounded_coordinates(
            missing_station["latitude"], missing_station["longitude"]
        )
    )
    refreshed = build_snapshot(
        stations_by_mode,
        weather,
        existing_payload=existing,
        generated_at="2026-07-30T15:00:00+00:00",
    )
    old = existing["assessments"]["sample"][0]
    new = refreshed["assessments"]["sample"][0]
    assert new == old


def test_atomic_writer_produces_valid_complete_json(tmp_path):
    payload = load_snapshot(DEFAULT_SNAPSHOT_PATH)
    output = tmp_path / "portfolio.json"
    write_snapshot_atomically(payload, output)
    assert output.is_file()
    assert not Path(str(output) + ".tmp").exists()
    assert json.loads(output.read_text(encoding="utf-8"))["snapshot_version"] == (
        SNAPSHOT_VERSION
    )
