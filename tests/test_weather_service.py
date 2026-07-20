import pytest
from unittest.mock import patch, Mock

import requests

from weather_service import fetch_open_meteo, WeatherServiceError


def make_resp(status=200, json_data=None):
    m = Mock()
    m.status_code = status
    m.json = Mock(return_value=json_data)
    return m


def test_successful_response():
    json_data = {
        "current_weather": {"temperature": 12.3},
        "daily": {"temperature_2m_max": [13, 14, 15, 16, 17, 18, 19]},
    }
    with patch("requests.get", return_value=make_resp(json_data=json_data)) as rg:
        out = fetch_open_meteo(51.48, -3.18)
        assert out["current_temperature_c"] == 12.3
        assert out["forecast_max_temperature_c"] == [13, 14, 15, 16, 17, 18, 19]
        assert out["source"] == "Open-Meteo"


def test_http_failure():
    with patch("requests.get", return_value=make_resp(status=500, json_data={})):
        with pytest.raises(WeatherServiceError):
            fetch_open_meteo(51.48, -3.18)


def test_malformed_response_missing_keys():
    json_data = {"foo": 1}
    with patch("requests.get", return_value=make_resp(json_data=json_data)):
        with pytest.raises(WeatherServiceError):
            fetch_open_meteo(51.48, -3.18)


def test_missing_forecast_values():
    json_data = {"current_weather": {"temperature": 10}, "daily": {"temperature_2m_max": [1, 2]}}
    with patch("requests.get", return_value=make_resp(json_data=json_data)):
        with pytest.raises(WeatherServiceError):
            fetch_open_meteo(51.48, -3.18)


def test_timeout_raises_weather_service_error():
    with patch("requests.get", side_effect=requests.exceptions.Timeout):
        with pytest.raises(WeatherServiceError):
            fetch_open_meteo(51.48, -3.18)
