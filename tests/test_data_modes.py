import shutil
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest

import app
from app import attribution_statements, dataset_mode_label, verified_site_details
from config import (
    MAP_ATTRIBUTION,
    NRW_ATTRIBUTION,
    ONS_OS_ATTRIBUTION,
    OPEN_CHARGE_MAP_ATTRIBUTION,
    STATWALES_PROVIDER_STATEMENT,
    WEATHER_ATTRIBUTION,
    WIMD_ATTRIBUTION,
)
from data_loader import SAMPLE_CSV, VERIFIED_CSV, load_stations
from scoring import compute_scores

TIMESTAMP = "2026-07-20T12:00:00+00:00"


@pytest.fixture
def workspace_tmp_dir():
    path = Path(__file__).parent / ".tmp" / str(uuid4())
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_sample_mode_loads_existing_demonstrative_data():
    expected = pd.read_csv(SAMPLE_CSV)
    result = load_stations(mode="sample")
    assert len(result) == len(expected)
    assert result["station_id"].tolist() == expected["station_id"].tolist()
    assert "source" in result.columns


def test_verified_mode_loads_public_source_dataset():
    expected = pd.read_csv(VERIFIED_CSV)
    result = load_stations(mode="verified")
    assert len(result) == len(expected) == 66
    assert result["dataset_version"].notna().all()
    assert result["operator_name"].notna().all()


def test_missing_verified_file_has_clear_error_and_no_sample_fallback(workspace_tmp_dir):
    missing = workspace_tmp_dir / "missing-verified.csv"
    with pytest.raises(ValueError, match="Verified Cardiff dataset not found"):
        load_stations(
            mode="verified", verified_path=missing, sample_path=SAMPLE_CSV
        )


def test_malformed_verified_schema_has_clear_error(workspace_tmp_dir):
    malformed = workspace_tmp_dir / "malformed.csv"
    pd.DataFrame([{"station_id": "one"}]).to_csv(malformed, index=False)
    with pytest.raises(ValueError, match="Invalid verified dataset schema"):
        load_stations(mode="verified", verified_path=malformed)


def test_empty_verified_data_has_clear_error(workspace_tmp_dir):
    empty = workspace_tmp_dir / "empty.csv"
    pd.read_csv(VERIFIED_CSV, nrows=0).to_csv(empty, index=False)
    with pytest.raises(ValueError, match="dataset is empty"):
        load_stations(mode="verified", verified_path=empty)


def test_duplicate_verified_station_ids_have_clear_error(workspace_tmp_dir):
    duplicate = workspace_tmp_dir / "duplicate.csv"
    row = pd.read_csv(VERIFIED_CSV, nrows=1)
    pd.concat([row, row], ignore_index=True).to_csv(duplicate, index=False)
    with pytest.raises(ValueError, match="Duplicate station_id values in verified dataset"):
        load_stations(mode="verified", verified_path=duplicate)


def test_verified_factors_are_used_unchanged_in_existing_scoring():
    station = load_stations(mode="verified").iloc[0]
    result = compute_scores(
        station["flood_score"], 27.5, station["deprivation_score"]
    )
    assert result["flood_score"] == station["flood_score"]
    assert result["deprivation_score"] == station["deprivation_score"]
    assert result["temperature_score"] == 50
    assert result["overall_score"] == pytest.approx(
        station["flood_score"] * 0.5 + 50 * 0.3
        + station["deprivation_score"] * 0.2
    )


def test_dashboard_forecast_uses_seven_day_maximum(monkeypatch):
    station = load_stations(mode="verified").iloc[0]
    monkeypatch.setattr(
        app,
        "cached_weather",
        lambda lat, lon: {
            "current_temperature_c": 19.0,
            "forecast_max_temperature_c": [20.0, 21.0, 22.0, 23.0, 24.0, 25.0, 35.0],
            "seven_day_max_temperature_c": 35.0,
            "retrieved_at": TIMESTAMP,
        },
    )
    current, forecast, error, _ = app.compute_site_scores_safe(station)
    assert error is None
    assert current["temperature_score"] == 10
    assert forecast["temperature_score"] == 100


def test_dataset_mode_labels_are_exact():
    assert dataset_mode_label("sample") == "Demonstrative sample data"
    assert dataset_mode_label("verified") == "Public-source, geospatially enriched Cardiff data"


def test_verified_attribution_contains_every_required_statement():
    statements = attribution_statements("verified")
    for expected in (
        OPEN_CHARGE_MAP_ATTRIBUTION,
        NRW_ATTRIBUTION,
        STATWALES_PROVIDER_STATEMENT,
        WIMD_ATTRIBUTION,
        ONS_OS_ATTRIBUTION,
        MAP_ATTRIBUTION,
        WEATHER_ATTRIBUTION,
    ):
        assert expected in statements


def test_sample_attribution_does_not_claim_verified_sources():
    statements = attribution_statements("sample")
    assert statements == [WEATHER_ATTRIBUTION, MAP_ATTRIBUTION]


def test_verified_site_details_include_available_traceability_fields():
    station = load_stations(mode="verified").iloc[0]
    labels = {label for label, _ in verified_site_details(station)}
    assert {
        "Operator", "Operational status", "Source provider", "Source last updated",
        "River flood band", "Sea flood band", "Surface-water flood band",
        "Dominant flood source", "LSOA", "Income-deprivation percentage",
        "Enrichment timestamp", "Dataset version",
    }.issubset(labels)
