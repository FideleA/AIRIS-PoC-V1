from pathlib import Path
from typing import Optional

import pandas as pd

from config import BASE_DIR, DATA_MODE, DATA_MODE_LABELS


SAMPLE_CSV = BASE_DIR / "data" / "stations.csv"
VERIFIED_CSV = BASE_DIR / "data" / "processed" / "cardiff_stations_verified.csv"

REQUIRED_COLUMNS = {
    "station_id", "station_name", "latitude", "longitude",
    "flood_score", "deprivation_score", "source",
}
VERIFIED_REQUIRED_COLUMNS = {
    "station_id", "station_name", "latitude", "longitude", "flood_score",
    "deprivation_score", "operator_name", "operational_status", "data_provider",
    "source_last_updated", "flood_river_band", "flood_sea_band",
    "flood_surface_water_band", "flood_dominant_source", "lsoa_name",
    "income_deprivation_percentage", "enrichment_timestamp", "dataset_version",
    "attribution", "licence",
}

LAT_MIN = 51.35
LAT_MAX = 51.55
LON_MIN = -3.25
LON_MAX = -3.05
VERIFIED_LAT_MIN = 51.3
VERIFIED_LAT_MAX = 51.7
VERIFIED_LON_MIN = -3.5
VERIFIED_LON_MAX = -2.9


def _error(msg: str) -> ValueError:
    return ValueError(msg)


def _safe_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(BASE_DIR.resolve()).as_posix()
    except ValueError:
        return path.name


def _read_csv(path: Path, mode: str) -> pd.DataFrame:
    if not path.exists():
        if mode == "verified":
            raise _error(f"Verified Cardiff dataset not found: {_safe_path(path)}")
        raise _error(f"Sample stations CSV not found: {_safe_path(path)}")
    try:
        data = pd.read_csv(path)
    except Exception as exc:
        raise _error(f"Failed to read {mode} station data") from exc
    if data.empty:
        raise _error(f"{DATA_MODE_LABELS[mode]} dataset is empty")
    return data.rename(columns={column: column.strip() for column in data.columns})


def _validate_common(
    data: pd.DataFrame,
    required: set[str],
    mode: str,
    coordinate_bounds: tuple[float, float, float, float],
) -> pd.DataFrame:
    missing = sorted(required - set(data.columns))
    if missing:
        raise _error(f"Invalid {mode} dataset schema; missing columns: {missing}")
    if data["station_id"].isna().any() or data["station_id"].astype(str).str.strip().eq("").any():
        raise _error(f"{mode.title()} dataset contains an empty station_id")
    if data["station_id"].duplicated().any():
        duplicates = data.loc[data["station_id"].duplicated(False), "station_id"].unique().tolist()
        raise _error(f"Duplicate station_id values in {mode} dataset: {duplicates}")
    empty_names = data["station_name"].isna() | data["station_name"].astype(str).str.strip().eq("")
    if empty_names.any():
        raise _error(
            f"Empty station_name for station_id(s): {data.loc[empty_names, 'station_id'].tolist()}"
        )

    for field in ("latitude", "longitude", "flood_score", "deprivation_score"):
        data[field] = pd.to_numeric(data[field], errors="coerce")
    invalid_numeric = data[["latitude", "longitude", "flood_score", "deprivation_score"]].isna().any(axis=1)
    if invalid_numeric.any():
        raise _error(
            f"Invalid numeric coordinates or factor scores for station_id(s): "
            f"{data.loc[invalid_numeric, 'station_id'].tolist()}"
        )
    lat_min, lat_max, lon_min, lon_max = coordinate_bounds
    outside = ~data["latitude"].between(lat_min, lat_max) | ~data["longitude"].between(lon_min, lon_max)
    if outside.any():
        raise _error(
            f"Station coordinates outside the {mode} Cardiff bounds for station_id(s): "
            f"{data.loc[outside, 'station_id'].tolist()}"
        )
    invalid_scores = ~data["flood_score"].between(0, 100) | ~data["deprivation_score"].between(0, 100)
    if invalid_scores.any():
        raise _error(
            f"Factor scores must be between 0 and 100 for station_id(s): "
            f"{data.loc[invalid_scores, 'station_id'].tolist()}"
        )
    return data


def load_stations(
    csv_path: Optional[Path] = None,
    mode: Optional[str] = None,
    sample_path: Optional[Path] = None,
    verified_path: Optional[Path] = None,
) -> pd.DataFrame:
    """Load one explicitly selected data mode; verified failures never fall back."""
    selected_mode = (mode or DATA_MODE).strip().lower()
    if selected_mode not in DATA_MODE_LABELS:
        raise _error(f"Unknown data mode {selected_mode!r}; expected 'sample' or 'verified'")

    # csv_path remains a backwards-compatible explicit sample fixture hook.
    if csv_path is not None:
        selected_mode = "sample"
        path = Path(csv_path)
    elif selected_mode == "verified":
        path = Path(verified_path) if verified_path is not None else VERIFIED_CSV
    else:
        path = Path(sample_path) if sample_path is not None else SAMPLE_CSV

    data = _read_csv(path, selected_mode)
    if selected_mode == "verified":
        return _validate_common(
            data, VERIFIED_REQUIRED_COLUMNS, selected_mode,
            (VERIFIED_LAT_MIN, VERIFIED_LAT_MAX, VERIFIED_LON_MIN, VERIFIED_LON_MAX),
        ).reset_index(drop=True)

    data = _validate_common(
        data, REQUIRED_COLUMNS, selected_mode, (LAT_MIN, LAT_MAX, LON_MIN, LON_MAX)
    )
    empty_source = data["source"].isna() | data["source"].astype(str).str.strip().eq("")
    if empty_source.any():
        raise _error(f"Empty source field for station_id(s): {data.loc[empty_source, 'station_id'].tolist()}")
    return data[[
        "station_id", "station_name", "latitude", "longitude",
        "flood_score", "deprivation_score", "source",
    ]].reset_index(drop=True)
