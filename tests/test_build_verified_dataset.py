import json
import shutil
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest

from scripts.build_verified_dataset import (
    DATASET_VERSION,
    MINIMUM_FIELDS,
    VerifiedDatasetError,
    build_verified_dataset,
    write_outputs,
)


TIMESTAMP = "2026-07-20T12:00:00+00:00"


@pytest.fixture
def workspace_tmp_dir():
    path = Path(__file__).parent / ".tmp" / str(uuid4())
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def record(station_id="station-1", **changes):
    row = {
        "station_id": station_id, "source_record_id": "source-1",
        "station_name": "Station", "address": "1 Example Street", "postcode": "CF10 1AA",
        "latitude": 51.5, "longitude": -3.2, "operator_name": "Operator",
        "operational_status": "operational", "number_of_evses": 2,
        "number_of_connectors": 4, "maximum_power_kw": 50, "access_type": "public",
        "usage_cost": "provider tariff", "data_provider": "provider",
        "source_url": "https://example.test/1", "source_last_updated": "2025-01-01T00:00:00Z",
        "licence": "licence", "attribution": "attribution", "verification_status": "unreviewed",
        "boundary_status": "inside", "flood_river_band": "Low", "flood_river_score": 35,
        "flood_sea_band": "Very Low", "flood_sea_score": 10,
        "flood_surface_water_band": "Medium", "flood_surface_water_score": 65,
        "flood_score": 65, "flood_dominant_source": "surface_water", "flood_match_count": 2,
        "flood_enrichment_status": "enriched", "flood_data_version": "FRAW 2026",
        "lsoa_code": "W01000001", "lsoa_name": "Cardiff LSOA",
        "income_deprivation_percentage": 12.5, "deprivation_score": 12.5,
        "deprivation_match_status": "resolved", "deprivation_match_count": 1,
        "deprivation_enrichment_timestamp": TIMESTAMP,
        "deprivation_source": "WIMD indicators", "deprivation_source_release": "WIMD 2025",
    }
    row.update(changes)
    return row


def build(*rows):
    return build_verified_dataset(pd.DataFrame(rows), build_timestamp=TIMESTAMP)


def test_usable_record_classification():
    usable, unresolved, report, _ = build(record())
    assert len(usable) == 1 and unresolved.empty
    assert report["usable_verified_count"] == 1


def test_unresolved_record_classification_preserves_record():
    usable, unresolved, report, _ = build(record(boundary_status="outside"))
    assert usable.empty and len(unresolved) == 1
    assert "boundary status" in unresolved.iloc[0]["verified_dataset_notes"]
    assert report["source_record_count"] == 1


def test_required_output_schema():
    usable, _, _, _ = build(record())
    assert set(MINIMUM_FIELDS).issubset(usable.columns)


def test_duplicate_station_ids_are_all_unresolved():
    usable, unresolved, report, _ = build(record(), record(source_record_id="source-2"))
    assert usable.empty and len(unresolved) == 2
    assert report["duplicate_summary"]["records_with_duplicate_station_id"] == 2


def test_missing_flood_data_is_unresolved():
    usable, unresolved, _, _ = build(record(flood_score=None))
    assert usable.empty and "missing flood data" in unresolved.iloc[0]["verified_dataset_notes"]


def test_missing_lsoa_is_unresolved():
    usable, unresolved, _, _ = build(record(lsoa_code=""))
    assert usable.empty and "missing LSOA" in unresolved.iloc[0]["verified_dataset_notes"]


@pytest.mark.parametrize("percentage", [None, -1, 101, "bad"])
def test_invalid_deprivation_percentage_is_unresolved(percentage):
    usable, unresolved, _, _ = build(record(income_deprivation_percentage=percentage, deprivation_score=percentage))
    assert usable.empty and "invalid deprivation percentage" in unresolved.iloc[0]["verified_dataset_notes"]


def test_deprivation_percentage_is_not_rescaled():
    usable, _, _, _ = build(record(income_deprivation_percentage=12.5, deprivation_score=12.5))
    assert usable.iloc[0]["deprivation_score"] == 12.5


def test_missing_provenance_is_unresolved():
    usable, unresolved, report, _ = build(record(attribution=""))
    assert usable.empty and "missing provenance: attribution" in unresolved.iloc[0]["verified_dataset_notes"]
    assert report["provenance_completeness"]["incomplete_count"] == 1


def test_weather_and_overall_score_fields_are_prohibited():
    with pytest.raises(VerifiedDatasetError, match="prohibited"):
        build_verified_dataset(pd.DataFrame([record(overall_score=50)]))
    usable, _, _, _ = build(record())
    assert not {"current_temperature", "forecast_temperature", "overall_score", "airis_score"} & set(usable.columns)


def test_output_ordering_is_deterministic():
    first = record("station-b", source_record_id="2")
    second = record("station-a", source_record_id="1")
    forward = build(first, second)[0]
    reverse = build(second, first)[0]
    assert forward["station_id"].tolist() == reverse["station_id"].tolist() == ["station-a", "station-b"]


def test_dataset_version_and_enrichment_timestamp():
    usable, _, report, _ = build(record())
    assert usable.iloc[0]["dataset_version"] == DATASET_VERSION
    assert usable.iloc[0]["enrichment_timestamp"] == TIMESTAMP
    assert report["dataset_version"] == DATASET_VERSION


def test_checksum_generation(workspace_tmp_dir):
    usable, unresolved, report, review = build(record())
    verified_path = workspace_tmp_dir / "verified.csv"
    unresolved_path = workspace_tmp_dir / "unresolved.csv"
    report_path = workspace_tmp_dir / "report.json"
    review_path = workspace_tmp_dir / "review.md"
    write_outputs(usable, unresolved, report, review, verified_path, unresolved_path, report_path, review_path)
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert set(saved["output_checksums"]) == {"verified.csv", "unresolved.csv", "review.md"}
    assert all(len(value) == 64 for value in saved["output_checksums"].values())
