from unittest.mock import Mock

import pytest
import requests

from weather_service import WeatherServiceError, fetch_open_meteo


def response_with(payload, status=200):
    response = Mock()
    response.status_code = status
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
    with pytest.raises(WeatherServiceError):
        fetch_open_meteo(51.48, -3.18)


def test_timeout_is_handled_safely(monkeypatch):
    monkeypatch.setattr(
        "weather_service.requests.get", Mock(side_effect=requests.exceptions.Timeout)
    )
    with pytest.raises(WeatherServiceError):
        fetch_open_meteo(51.48, -3.18)
