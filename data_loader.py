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

LAT_MIN = 51.35
LAT_MAX = 51.55
LON_MIN = -3.25
LON_MAX = -3.05


def _error(msg: str) -> ValueError:
    return ValueError(msg)


def load_stations(csv_path: Optional[Path] = None) -> pd.DataFrame:
    """Load and validate station CSV, returning a cleaned DataFrame."""
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

    df = df.rename(columns={c: c.strip() for c in df.columns})

    if df["station_id"].duplicated().any():
        dup = df[df["station_id"].duplicated(keep=False)]["station_id"].unique().tolist()
        raise _error(f"Duplicate station_id values found: {dup}")

    empty_names = df["station_name"].isna() | (df["station_name"].astype(str).str.strip() == "")
    if empty_names.any():
        ids = df.loc[empty_names, "station_id"].tolist()
        raise _error(f"Empty station_name for station_id(s): {ids}")

    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    if df["latitude"].isna().any() or df["longitude"].isna().any():
        bad = df[df["latitude"].isna() | df["longitude"].isna()]["station_id"].tolist()
        raise _error(f"Invalid numeric coordinates for station_id(s): {bad}")

    out_of_box = df[
        ~df.apply(
            lambda row: LAT_MIN <= row["latitude"] <= LAT_MAX
            and LON_MIN <= row["longitude"] <= LON_MAX,
            axis=1,
        )
    ]
    if not out_of_box.empty:
        raise _error(
            "Station coordinates outside Cardiff bounding box for station_id(s): "
            f"{out_of_box['station_id'].tolist()}"
        )

    df["flood_score"] = pd.to_numeric(df["flood_score"], errors="coerce")
    df["deprivation_score"] = pd.to_numeric(df["deprivation_score"], errors="coerce")
    if df["flood_score"].isna().any() or df["deprivation_score"].isna().any():
        bad = df[df["flood_score"].isna() | df["deprivation_score"].isna()]["station_id"].tolist()
        raise _error(f"Invalid numeric factor scores for station_id(s): {bad}")

    bad_scores = df[
        ~df.apply(
            lambda row: 0 <= row["flood_score"] <= 100
            and 0 <= row["deprivation_score"] <= 100,
            axis=1,
        )
    ]
    if not bad_scores.empty:
        raise _error(
            "Factor scores must be between 0 and 100 for station_id(s): "
            f"{bad_scores['station_id'].tolist()}"
        )

    empty_source = df["source"].isna() | (df["source"].astype(str).str.strip() == "")
    if empty_source.any():
        ids = df.loc[empty_source, "station_id"].tolist()
        raise _error(f"Empty source field for station_id(s): {ids}")

    out_cols = [
        "station_id",
        "station_name",
        "latitude",
        "longitude",
        "flood_score",
        "deprivation_score",
        "source",
    ]
    return df[out_cols].reset_index(drop=True)
