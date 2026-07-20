import pandas as pd
import pytest

from data_loader import load_stations


def make_csv(path, df):
    df.to_csv(path, index=False)


def valid_df():
    return pd.DataFrame([
        {
            "station_id": "A1",
            "station_name": "Station A",
            "latitude": 51.48,
            "longitude": -3.18,
            "flood_score": 50,
            "deprivation_score": 30,
            "source": "sample",
        },
        {
            "station_id": "B2",
            "station_name": "Station B",
            "latitude": 51.49,
            "longitude": -3.17,
            "flood_score": 20,
            "deprivation_score": 60,
            "source": "sample",
        },
    ])


def test_load_valid(tmp_path):
    p = tmp_path / "stations.csv"
    make_csv(p, valid_df())
    df = load_stations(p)
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == [
        "station_id",
        "station_name",
        "latitude",
        "longitude",
        "flood_score",
        "deprivation_score",
        "source",
    ]


def test_missing_columns(tmp_path):
    df = valid_df().drop(columns=["source"])  # remove required column
    p = tmp_path / "stations.csv"
    make_csv(p, df)
    with pytest.raises(ValueError):
        load_stations(p)


def test_duplicate_ids(tmp_path):
    df = valid_df()
    df.loc[1, "station_id"] = "A1"
    p = tmp_path / "stations.csv"
    make_csv(p, df)
    with pytest.raises(ValueError):
        load_stations(p)


def test_invalid_coordinates(tmp_path):
    df = valid_df()
    df.loc[0, "latitude"] = 60.0  # outside Cardiff
    p = tmp_path / "stations.csv"
    make_csv(p, df)
    with pytest.raises(ValueError):
        load_stations(p)


def test_invalid_scores(tmp_path):
    df = valid_df()
    df.loc[0, "flood_score"] = 200
    p = tmp_path / "stations.csv"
    make_csv(p, df)
    with pytest.raises(ValueError):
        load_stations(p)


def test_missing_source(tmp_path):
    df = valid_df()
    df.loc[0, "source"] = ""
    p = tmp_path / "stations.csv"
    make_csv(p, df)
    with pytest.raises(ValueError):
        load_stations(p)
