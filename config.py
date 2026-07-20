from pathlib import Path
from datetime import timedelta

# Project root
BASE_DIR = Path(__file__).resolve().parent

# Data directory (raw inputs)
DATA_DIR = BASE_DIR / "data" / "raw"

# Cardiff centre (lat, lon) and default zoom for map centring
CARDIFF_CENTER = (51.4816, -3.1791)
CARDIFF_ZOOM = 12

# Model and config
MODEL_VERSION = "0.1.0"

# Risk bands expressed as (min_inclusive, max_inclusive) on 0-100 scale.
RISK_BANDS = {
    "very_low": (0, 20),
    "low": (21, 40),
    "medium": (41, 70),
    "high": (71, 90),
    "very_high": (91, 100),
}

# Temperature thresholds used by scoring logic (degrees Celsius)
# These are configuration values only; scoring behaviour remains in scoring module.
TEMPERATURE_THRESHOLDS = {
    "cold": 20,
    "warm": 25,
    "hot": 30,
    "very_hot": 35,
}

# Factor weights (must sum to 1.0)
WEIGHTS = {"flood": 0.5, "temperature": 0.3, "deprivation": 0.2}

if abs(sum(WEIGHTS.values()) - 1.0) > 1e-9:
    raise ValueError("WEIGHTS must sum to 1.0")

# Cache and API defaults
CACHE_TTL = timedelta(hours=6)
OPEN_METEO_TIMEOUT = 10  # seconds
