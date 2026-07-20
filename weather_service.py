from typing import List, Dict, Any
from datetime import datetime, timezone

import requests

from config import OPEN_METEO_TIMEOUT


class WeatherServiceError(Exception):
    """Friendly exception for weather service errors (safe for UI display)."""


def fetch_open_meteo(lat: float, lon: float) -> Dict[str, Any]:
    """Call Open-Meteo forecast API and return parsed weather.

    Returns a dict with keys:
      - current_temperature_c: float
      - forecast_max_temperature_c: List[float]  (7 values)
      - retrieved_at: ISO8601 UTC timestamp
      - source: str

    Raises WeatherServiceError for any failure with a user-friendly message.
    """
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
        resp = requests.get(url, params=params, timeout=OPEN_METEO_TIMEOUT)
    except requests.exceptions.Timeout:
        raise WeatherServiceError("Weather request timed out")
    except requests.RequestException:
        raise WeatherServiceError("Failed to retrieve weather data")

    if resp.status_code != 200:
        raise WeatherServiceError(f"Weather API returned HTTP {resp.status_code}")

    try:
        data = resp.json()
    except ValueError:
        raise WeatherServiceError("Weather API returned invalid JSON")

    # Validate expected structure
    if "current_weather" not in data or "daily" not in data:
        raise WeatherServiceError("Weather API response missing expected fields")

    current = data.get("current_weather", {})
    daily = data.get("daily", {})

    if "temperature" not in current:
        raise WeatherServiceError("Weather API response missing current temperature")

    temps = daily.get("temperature_2m_max")
    if not isinstance(temps, list) or len(temps) < 7:
        raise WeatherServiceError("Weather API response missing sufficient daily max temperatures")

    try:
        current_temp = float(current["temperature"])
        forecast_max = [float(x) for x in temps[:7]]
    except Exception:
        raise WeatherServiceError("Weather API returned non-numeric temperature values")

    return {
        "current_temperature_c": current_temp,
        "forecast_max_temperature_c": forecast_max,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "source": "Open-Meteo",
    }
