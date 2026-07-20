from pathlib import Path

import pandas as pd

from data_loader import (
    LAT_MAX,
    LAT_MIN,
    LON_MAX,
    LON_MIN,
    REQUIRED_COLUMNS,
    load_stations,
)


SAMPLE_CSV = Path(__file__).parents[1] / "data" / "stations.csv"


def test_sample_charger_csv_exists():
    assert SAMPLE_CSV.is_file()


def test_sample_charger_csv_has_required_columns():
    columns = set(pd.read_csv(SAMPLE_CSV, nrows=0).columns)
    assert REQUIRED_COLUMNS <= columns


def test_station_identifiers_are_present_and_unique():
    stations = load_stations(SAMPLE_CSV)
    assert stations["station_id"].notna().all()
    assert stations["station_id"].astype(str).str.strip().ne("").all()
    assert stations["station_id"].is_unique


def test_station_names_are_not_blank():
    stations = load_stations(SAMPLE_CSV)
    assert stations["station_name"].notna().all()
    assert stations["station_name"].astype(str).str.strip().ne("").all()


def test_coordinates_are_numeric_and_within_cardiff_area():
    stations = load_stations(SAMPLE_CSV)
    assert pd.api.types.is_numeric_dtype(stations["latitude"])
    assert pd.api.types.is_numeric_dtype(stations["longitude"])
    assert stations["latitude"].between(LAT_MIN, LAT_MAX).all()
    assert stations["longitude"].between(LON_MIN, LON_MAX).all()


def test_flood_and_deprivation_scores_are_numeric_and_bounded():
    stations = load_stations(SAMPLE_CSV)
    for column in ("flood_score", "deprivation_score"):
        assert pd.api.types.is_numeric_dtype(stations[column])
        assert stations[column].between(0, 100).all()

