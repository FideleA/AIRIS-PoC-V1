from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import random
import time
from typing import Any, Dict

import requests

from config import OPEN_METEO_TIMEOUT


class WeatherServiceError(Exception):
    """Friendly exception for weather service errors safe for UI display."""

    def __init__(
        self,
        message: str,
        *,
        kind: str = "provider",
        status_code: int | None = None,
        retry_after_seconds: float | None = None,
    ):
        super().__init__(message)
        self.kind = kind
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds


OPEN_METEO_ENDPOINT = "https://api.open-meteo.com/v1/forecast"
FORECAST_DAYS = 7
MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 0.5
BACKOFF_JITTER_SECONDS = 0.25
COORDINATE_PRECISION = 4


def rounded_coordinates(lat: float, lon: float) -> tuple[float, float]:
    return (
        round(float(lat), COORDINATE_PRECISION),
        round(float(lon), COORDINATE_PRECISION),
    )


def parse_retry_after(value: str | None, now: datetime | None = None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        pass
    try:
        retry_at = parsedate_to_datetime(value)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        reference = now or datetime.now(timezone.utc)
        return max(0.0, (retry_at - reference).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


def _retry_delay(response, attempt: int) -> float:
    retry_after = parse_retry_after(response.headers.get("Retry-After"))
    if retry_after is not None:
        return retry_after
    return BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)) + random.uniform(
        0.0, BACKOFF_JITTER_SECONDS
    )


def _parse_open_meteo_response(data: dict) -> Dict[str, Any]:
    if "current_weather" not in data or "daily" not in data:
        raise WeatherServiceError(
            "Weather provider response is missing expected fields",
            kind="invalid_response",
        )

    current = data.get("current_weather", {})
    daily = data.get("daily", {})
    if "temperature" not in current:
        raise WeatherServiceError(
            "Weather provider response is missing the current temperature",
            kind="missing_values",
        )

    temperatures = daily.get("temperature_2m_max")
    if not isinstance(temperatures, list) or len(temperatures) < FORECAST_DAYS:
        raise WeatherServiceError(
            "Weather provider response is missing the seven-day forecast",
            kind="missing_values",
        )

    try:
        current_temperature = float(current["temperature"])
        forecast_maxima = [
            float(value) for value in temperatures[:FORECAST_DAYS]
        ]
    except (TypeError, ValueError):
        raise WeatherServiceError(
            "Weather provider returned invalid temperature values",
            kind="invalid_response",
        )

    return {
        "current_temperature_c": current_temperature,
        "forecast_max_temperature_c": forecast_maxima,
        "seven_day_max_temperature_c": max(forecast_maxima),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "source": "Open-Meteo",
    }


def fetch_open_meteo(
    lat: float,
    lon: float,
    *,
    forecast_days: int = FORECAST_DAYS,
    sleep=time.sleep,
) -> Dict[str, Any]:
    latitude, longitude = rounded_coordinates(lat, lon)
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current_weather": "true",
        "daily": "temperature_2m_max",
        "forecast_days": int(forecast_days),
        "timezone": "Europe/London",
    }

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(
                OPEN_METEO_ENDPOINT,
                params=params,
                timeout=OPEN_METEO_TIMEOUT,
            )
        except requests.exceptions.Timeout as exc:
            raise WeatherServiceError(
                "Live weather request timed out",
                kind="timeout",
            ) from exc
        except requests.RequestException as exc:
            raise WeatherServiceError(
                "Live weather provider could not be reached",
                kind="network",
            ) from exc

        if response.status_code == 429:
            retry_after = parse_retry_after(response.headers.get("Retry-After"))
            if attempt < MAX_ATTEMPTS:
                sleep(_retry_delay(response, attempt))
                continue
            raise WeatherServiceError(
                "Live weather is temporarily rate-limited",
                kind="rate_limit",
                status_code=429,
                retry_after_seconds=retry_after,
            )

        if 500 <= response.status_code <= 599:
            if attempt < MAX_ATTEMPTS:
                sleep(_retry_delay(response, attempt))
                continue
            raise WeatherServiceError(
                "Live weather provider is temporarily unavailable",
                kind="provider_5xx",
                status_code=response.status_code,
            )

        if response.status_code != 200:
            raise WeatherServiceError(
                "Live weather provider returned an unexpected response",
                kind="http",
                status_code=response.status_code,
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise WeatherServiceError(
                "Weather provider returned invalid JSON",
                kind="invalid_response",
            ) from exc
        return _parse_open_meteo_response(data)

    raise WeatherServiceError("Weather request failed", kind="provider")
