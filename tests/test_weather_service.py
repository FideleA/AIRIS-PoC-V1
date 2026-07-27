from unittest.mock import Mock

import pytest
import requests

from weather_service import (
    MAX_ATTEMPTS,
    WeatherServiceError,
    fetch_open_meteo,
    parse_retry_after,
    rounded_coordinates,
)


def response_with(payload, status=200):
    response = Mock()
    response.status_code = status
    response.headers = {}
    response.json.return_value = payload
    return response


def valid_payload():
    return {
        "current_weather": {"temperature": 12.3},
        "daily": {"temperature_2m_max": [13, 18, 15, 21, 17, 19, 16]},
    }


def test_weather_response_reads_current_and_seven_day_forecast(monkeypatch):
    get = Mock(return_value=response_with(valid_payload()))
    monkeypatch.setattr("weather_service.requests.get", get)

    result = fetch_open_meteo(51.48, -3.18)

    assert result["current_temperature_c"] == pytest.approx(12.3)
    assert len(result["forecast_max_temperature_c"]) == 7
    assert result["seven_day_max_temperature_c"] == pytest.approx(21)
    assert result["seven_day_max_temperature_c"] == max(
        result["forecast_max_temperature_c"]
    )
    assert result["seven_day_max_temperature_c"] != result["current_temperature_c"]
    get.assert_called_once()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"current_weather": {}, "daily": {"temperature_2m_max": [1] * 7}},
        {"current_weather": {"temperature": 10}, "daily": {}},
        {
            "current_weather": {"temperature": 10},
            "daily": {"temperature_2m_max": [1, 2]},
        },
        {
            "current_weather": {"temperature": "invalid"},
            "daily": {"temperature_2m_max": [1] * 7},
        },
        {
            "current_weather": {"temperature": 10},
            "daily": {"temperature_2m_max": [1, 2, 3, None, 5, 6, 7]},
        },
    ],
)
def test_malformed_or_missing_values_are_handled_safely(monkeypatch, payload):
    monkeypatch.setattr(
        "weather_service.requests.get", Mock(return_value=response_with(payload))
    )
    with pytest.raises(WeatherServiceError):
        fetch_open_meteo(51.48, -3.18)


def test_http_failure_is_handled_safely(monkeypatch):
    monkeypatch.setattr(
        "weather_service.requests.get",
        Mock(return_value=response_with({}, status=503)),
    )
    with pytest.raises(WeatherServiceError) as raised:
        fetch_open_meteo(51.48, -3.18)
    assert raised.value.kind == "provider_5xx"


def test_timeout_is_handled_safely(monkeypatch):
    monkeypatch.setattr(
        "weather_service.requests.get", Mock(side_effect=requests.exceptions.Timeout)
    )
    with pytest.raises(WeatherServiceError) as raised:
        fetch_open_meteo(51.48, -3.18)
    assert raised.value.kind == "timeout"


def test_coordinates_are_rounded_consistently():
    assert rounded_coordinates(51.48161234, -3.17914567) == (51.4816, -3.1791)


def test_http_429_has_bounded_backoff(monkeypatch):
    responses = [response_with({}, status=429) for _ in range(MAX_ATTEMPTS)]
    get = Mock(side_effect=responses)
    sleeps = []
    monkeypatch.setattr("weather_service.requests.get", get)
    monkeypatch.setattr("weather_service.random.uniform", lambda *_: 0.0)

    with pytest.raises(WeatherServiceError) as raised:
        fetch_open_meteo(51.48, -3.18, sleep=sleeps.append)

    assert raised.value.kind == "rate_limit"
    assert raised.value.status_code == 429
    assert get.call_count == MAX_ATTEMPTS
    assert sleeps == [0.5, 1.0]


def test_retry_after_is_respected_before_success(monkeypatch):
    limited = response_with({}, status=429)
    limited.headers["Retry-After"] = "2"
    get = Mock(side_effect=[limited, response_with(valid_payload())])
    sleeps = []
    monkeypatch.setattr("weather_service.requests.get", get)

    result = fetch_open_meteo(51.48, -3.18, sleep=sleeps.append)

    assert result["current_temperature_c"] == pytest.approx(12.3)
    assert sleeps == [2.0]
    assert parse_retry_after("2") == pytest.approx(2.0)
