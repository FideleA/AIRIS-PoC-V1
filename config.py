from pathlib import Path
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data" / "raw"

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
