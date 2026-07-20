from pathlib import Path
from datetime import timedelta
import os

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data" / "raw"

# Central dataset selection. Set AIRIS_DATA_MODE to "verified" for the
# public-source dataset; the default preserves the demonstrative experience.
DATA_MODE = os.environ.get("AIRIS_DATA_MODE", "verified").strip().lower()
DATA_MODE_LABELS = {
    "sample": "Demonstrative sample data",
    "verified": "Public-source, geospatially enriched Cardiff data",
}

OPEN_CHARGE_MAP_ATTRIBUTION = (
    "Charging locations: Open Charge Map and the applicable underlying data "
    "provider; provider-specific attribution and licence are retained per record."
)
NRW_ATTRIBUTION = (
    "Contains Natural Resources Wales information © Natural Resources Wales and "
    "database right. All rights reserved. Some features of this information are "
    "based on digital spatial data licensed from the UK Centre for Ecology & "
    "Hydrology © UKCEH. Defra, Met Office and DARD Rivers Agency © Crown copyright. "
    "© Cranfield University. © James Hutton Institute. Contains OS data © Crown "
    "copyright and database right."
)
WIMD_ATTRIBUTION = (
    "Source: Welsh Government, Welsh Index of Multiple Deprivation 2025 indicator "
    "data, licensed under the Open Government Licence v3.0. © Crown copyright 2025."
)
STATWALES_PROVIDER_STATEMENT = "Data source platform: Welsh Government / StatsWales."
ONS_OS_ATTRIBUTION = (
    "Source: Office for National Statistics licensed under the Open Government "
    "Licence v3.0. Contains OS data © Crown copyright and database right 2025."
)
MAP_ATTRIBUTION = "Map tiles: © OpenStreetMap contributors."
WEATHER_ATTRIBUTION = "Weather data: Open-Meteo."

if DATA_MODE not in DATA_MODE_LABELS:
    raise ValueError(
        f"Invalid AIRIS_DATA_MODE {DATA_MODE!r}; expected 'sample' or 'verified'"
    )

CARDIFF_CENTER = (51.4816, -3.1791)
CARDIFF_ZOOM = 12
MODEL_VERSION = "0.1.0"

RISK_BANDS = {
    "very_low": (0, 20),
    "low": (21, 40),
    "medium": (41, 70),
    "high": (71, 90),
    "very_high": (91, 100),
}

TEMPERATURE_THRESHOLDS = {
    "cold": 20,
    "warm": 25,
    "hot": 30,
    "very_hot": 35,
}

WEIGHTS = {"flood": 0.5, "temperature": 0.3, "deprivation": 0.2}

if abs(sum(WEIGHTS.values()) - 1.0) > 1e-9:
    raise ValueError("WEIGHTS must sum to 1.0")

CACHE_TTL = timedelta(hours=6)
OPEN_METEO_TIMEOUT = 10
