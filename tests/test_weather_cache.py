from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

import app
from data_loader import load_stations
from weather_service import WeatherServiceError


def weather_result(current=18.0, forecast=24.0):
    return {
        "current_temperature_c": current,
        "forecast_max_temperature_c": [forecast] * 7,
        "seven_day_max_temperature_c": forecast,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "source": "Open-Meteo",
    }


@pytest.fixture(autouse=True)
def clear_weather_state():
    app._cached_provider_weather.clear()
    store = app.weather_runtime_store()
    with store["lock"]:
        store["last_known"].clear()
    yield
    app._cached_provider_weather.clear()
    with store["lock"]:
        store["last_known"].clear()


def test_identical_coordinates_use_shared_cache(monkeypatch):
    provider = Mock(return_value=weather_result())
    monkeypatch.setattr(app, "fetch_open_meteo", provider)

    first = app.cached_weather(51.4816123, -3.1791456)
    second = app.cached_weather(51.4816499, -3.1791499)

    assert provider.call_count == 1
    assert first["weather_status"] == "live"
    assert second["weather_status"] == "cached"


def test_stored_assessments_build_results_without_provider_calls(monkeypatch):
    stations = load_stations(mode="sample")
    selected = stations.iloc[0]
    provider = Mock(return_value=weather_result())
    monkeypatch.setattr(app, "fetch_open_meteo", provider)
    assessment = app.compute_site_scores_safe(selected)

    results = app.results_from_stored_assessments(
        stations,
        {str(selected["station_id"]): assessment},
    )
    rerun_results = app.results_from_stored_assessments(
        stations,
        {str(selected["station_id"]): assessment},
    )

    assert provider.call_count == 1
    assert len(results) == len(rerun_results) == 10
    assert sum(item["current"] is not None for item in results) == 1
    assert app.portfolio_metrics(results)["sites_mapped"] == 10


def test_last_known_weather_is_used_after_rate_limit(monkeypatch):
    monkeypatch.setattr(app, "fetch_open_meteo", Mock(return_value=weather_result()))
    live = app.cached_weather(51.48, -3.18)
    assert live["weather_status"] == "live"

    limited = WeatherServiceError(
        "Live weather is temporarily rate-limited",
        kind="rate_limit",
        status_code=429,
    )
    monkeypatch.setattr(app, "fetch_open_meteo", Mock(side_effect=limited))
    fallback = app.cached_weather(51.48, -3.18, force_refresh=True)

    assert fallback["weather_status"] == "last-known"
    assert fallback["retrieved_at"] == live["retrieved_at"]
    assert fallback["error_kind"] == "rate_limit"
    assert "error" not in fallback


def test_rate_limit_without_cached_result_is_gracefully_unavailable(monkeypatch):
    limited = WeatherServiceError(
        "Live weather is temporarily rate-limited",
        kind="rate_limit",
        status_code=429,
    )
    monkeypatch.setattr(app, "fetch_open_meteo", Mock(side_effect=limited))

    result = app.cached_weather(51.48, -3.18)

    assert result["weather_status"] == "unavailable"
    assert result["error_kind"] == "rate_limit"
    assert "rate-limited" in app.weather_availability_message(result)


def test_expired_last_known_result_remains_fallback(monkeypatch):
    old = weather_result()
    old["retrieved_at"] = (
        datetime.now(timezone.utc)
        - timedelta(seconds=app.WEATHER_CACHE_TTL_SECONDS + 1)
    ).isoformat()
    key = (*app.rounded_coordinates(51.48, -3.18), 7)
    store = app.weather_runtime_store()
    with store["lock"]:
        store["last_known"][key] = old
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

    result = app.cached_weather(51.48, -3.18, force_refresh=True)

    assert result["weather_status"] == "last-known"
    assert result["retrieved_at"] == old["retrieved_at"]


def test_proposed_site_uses_same_cached_weather_service(monkeypatch):
    provider = Mock(return_value=weather_result(current=19.0, forecast=35.0))
    monkeypatch.setattr(app, "fetch_open_meteo", provider)
    weather = app.cached_weather(51.48, -3.18)
    scenario = app.build_scenario_record([], 51.48, -3.18, 50, 20, weather)

    assert provider.call_count == 1
    assert scenario["temperature_risk_current"] == 10
    assert scenario["temperature_risk_forecast"] == 100
    assert scenario["weather_retrieved_at"] == weather["retrieved_at"]
