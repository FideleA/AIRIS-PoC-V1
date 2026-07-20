from pathlib import Path
from typing import Optional

import pandas as pd

from config import BASE_DIR


REQUIRED_COLUMNS = {
    "station_id",
    "station_name",
    "latitude",
    "longitude",
    "flood_score",
    "deprivation_score",
    "source",
}

# Reasonable Cardiff bounding box (lat, lon)
LAT_MIN = 51.35
LAT_MAX = 51.55
LON_MIN = -3.25
LON_MAX = -3.05


def _error(msg: str) -> ValueError:
    # helper to create readable errors for Streamlit display
    return ValueError(msg)


def load_stations(csv_path: Optional[Path] = None) -> pd.DataFrame:
    """Load and validate station CSV, returning a cleaned pandas DataFrame.

    The CSV path is relative to the project by default: `data/stations.csv`.
    Raises ValueError with readable messages for any validation failure.
    """
    csv_path = Path(csv_path) if csv_path is not None else BASE_DIR / "data" / "stations.csv"
    if not csv_path.exists():
        raise _error(f"Stations CSV not found: {csv_path}")

    try:
        df = pd.read_csv(csv_path)
    except Exception as exc:
        raise _error(f"Failed to read CSV: {exc}")

    cols = set(df.columns.str.strip())
    missing = REQUIRED_COLUMNS - cols
    if missing:
        raise _error(f"Stations CSV is missing required columns: {sorted(missing)}")

    # Standardise column names to expected names (strip whitespace)
    df = df.rename(columns={c: c.strip() for c in df.columns})

    # station_id uniqueness
    if df["station_id"].duplicated().any():
        dup = df[df["station_id"].duplicated(keep=False)]["station_id"].unique().tolist()
        raise _error(f"Duplicate station_id values found: {dup}")

    # station_name non-empty
    empty_names = df["station_name"].isna() | (df["station_name"].astype(str).str.strip() == "")
    if empty_names.any():
        ids = df.loc[empty_names, "station_id"].tolist()
        raise _error(f"Empty station_name for station_id(s): {ids}")

    # numeric latitude/longitude
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    if df["latitude"].isna().any() or df["longitude"].isna().any():
        bad = df[df["latitude"].isna() | df["longitude"].isna()]["station_id"].tolist()
        raise _error(f"Invalid numeric coordinates for station_id(s): {bad}")

    # coordinates within Cardiff bounding box
    out_of_box = df[~df.apply(lambda r: LAT_MIN <= r["latitude"] <= LAT_MAX and LON_MIN <= r["longitude"] <= LON_MAX, axis=1)]
    if not out_of_box.empty:
        ids = out_of_box["station_id"].tolist()
        raise _error(f"Station coordinates outside Cardiff bounding box for station_id(s): {ids}")

    # factor scores numeric and 0..100
    df["flood_score"] = pd.to_numeric(df["flood_score"], errors="coerce")
    df["deprivation_score"] = pd.to_numeric(df["deprivation_score"], errors="coerce")
    if df["flood_score"].isna().any() or df["deprivation_score"].isna().any():
        bad = df[df["flood_score"].isna() | df["deprivation_score"].isna()]["station_id"].tolist()
        raise _error(f"Invalid numeric factor scores for station_id(s): {bad}")

    bad_scores = df[~df.apply(lambda r: 0 <= r["flood_score"] <= 100 and 0 <= r["deprivation_score"] <= 100, axis=1)]
    if not bad_scores.empty:
        ids = bad_scores["station_id"].tolist()
        raise _error(f"Factor scores must be between 0 and 100 for station_id(s): {ids}")

    # source non-empty (treat NA and empty strings as missing)
    empty_source = df["source"].isna() | (df["source"].astype(str).str.strip() == "")
    if empty_source.any():
        ids = df.loc[empty_source, "station_id"].tolist()
        raise _error(f"Empty source field for station_id(s): {ids}")

    # Return cleaned DataFrame with columns in consistent order
    out_cols = ["station_id", "station_name", "latitude", "longitude", "flood_score", "deprivation_score", "source"]
    return df[out_cols].reset_index(drop=True)
