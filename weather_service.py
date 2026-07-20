from datetime import datetime, timezone
from typing import Any, Dict

import requests

from config import OPEN_METEO_TIMEOUT


class WeatherServiceError(Exception):
    """Friendly exception for weather service errors safe for UI display."""


def fetch_open_meteo(lat: float, lon: float) -> Dict[str, Any]:
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": float(lat),
        "longitude": float(lon),
        "current_weather": "true",
        "daily": "temperature_2m_max",
        "forecast_days": 7,
        "timezone": "Europe/London",
    }

    try:
        response = requests.get(url, params=params, timeout=OPEN_METEO_TIMEOUT)
    except requests.exceptions.Timeout:
        raise WeatherServiceError("Weather request timed out")
    except requests.RequestException:
        raise WeatherServiceError("Failed to retrieve weather data")

    if response.status_code != 200:
        raise WeatherServiceError(f"Weather API returned HTTP {response.status_code}")

    try:
        data = response.json()
    except ValueError:
        raise WeatherServiceError("Weather API returned invalid JSON")

    if "current_weather" not in data or "daily" not in data:
        raise WeatherServiceError("Weather API response missing expected fields")

    current = data.get("current_weather", {})
    daily = data.get("daily", {})
    if "temperature" not in current:
        raise WeatherServiceError("Weather API response missing current temperature")

    temperatures = daily.get("temperature_2m_max")
    if not isinstance(temperatures, list) or len(temperatures) < 7:
        raise WeatherServiceError(
            "Weather API response missing sufficient daily max temperatures"
        )

    try:
        current_temperature = float(current["temperature"])
        forecast_maxima = [float(value) for value in temperatures[:7]]
    except Exception:
        raise WeatherServiceError("Weather API returned non-numeric temperature values")

    return {
        "current_temperature_c": current_temperature,
        "forecast_max_temperature_c": forecast_maxima,
        "seven_day_max_temperature_c": max(forecast_maxima),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "source": "Open-Meteo",
    }
