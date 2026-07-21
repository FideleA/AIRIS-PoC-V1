import json
import shutil
from pathlib import Path
from uuid import uuid4

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from scripts.enrich_chargers_with_deprivation import (
    OUTPUT_FIELDS,
    enrich_chargers,
    write_outputs,
)


TIMESTAMP = "2026-07-20T12:00:00+00:00"
FLOOD_FIELDS = {
    "flood_river_band": "Low", "flood_river_score": 35,
    "flood_river_match_count": 1, "flood_sea_band": "Very Low",
    "flood_sea_score": 10, "flood_sea_match_count": 0,
    "flood_surface_water_band": "Very Low", "flood_surface_water_score": 10,
    "flood_surface_water_match_count": 0, "flood_match_count": 1,
    "flood_score": 35, "flood_dominant_source": "river",
    "flood_data_version": "FRAW test version",
    "flood_enrichment_timestamp": "2026-07-19T00:00:00+00:00",
    "flood_enrichment_status": "enriched",
}


@pytest.fixture
def workspace_tmp_dir():
    path = Path(__file__).parent / ".tmp" / str(uuid4())
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def chargers(*coordinates, duplicate=False):
    rows = []
    for index, (latitude, longitude) in enumerate(coordinates, start=1):
        row = {
            "station_id": "station-1" if duplicate else f"station-{index}",
            "latitude": latitude, "longitude": longitude,
            "data_provider": "provider", "source_url": "https://example.test/site",
            "licence": "test licence", "attribution": "test attribution",
        }
        row.update(FLOOD_FIELDS)
        rows.append(row)
    return pd.DataFrame(rows)


def lsoas(records=None, crs="EPSG:4326"):
    records = records or [{"code": "W01000001", "geometry": box(-3.21, 51.49, -3.19, 51.51), "percentage": 12.5}]
    rows = []
    for record in records:
        rows.append({
            "lsoa_code": record["code"], "lsoa_name": f"Name {record['code']}",
            "lsoa_boundary_name_cy": f"Enw {record['code']}",
            "income_deprivation_percentage": record.get("percentage"),
            "deprivation_score": record.get("percentage"),
            "source_dataset": "WIMD indicators", "release_name": "WIMD 2025",
            "source_publication_date": "2025-11-27", "licence": "OGL v3.0",
            "attribution": "Welsh Government", "geometry": record["geometry"],
        })
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=crs)


def test_one_correct_lsoa_match_and_percentage_assignment():
    enriched, unresolved, report = enrich_chargers(chargers((51.5, -3.2)), lsoas(), TIMESTAMP)
    row = enriched.iloc[0]
    assert row["lsoa_code"] == "W01000001"
    assert row["deprivation_score"] == 12.5
    assert row["income_deprivation_percentage"] == 12.5
    assert row["deprivation_match_status"] == "resolved"
    assert unresolved.empty and report["matched_count"] == 1


def test_no_match_is_preserved_and_unresolved():
    enriched, unresolved, report = enrich_chargers(chargers((52, -4)), lsoas(), TIMESTAMP)
    assert len(enriched) == len(unresolved) == 1
    assert enriched.iloc[0]["deprivation_match_count"] == 0
    assert report["unmatched_count"] == 1


@pytest.mark.parametrize("coordinate", [(51.5, -3.19), (51.51, -3.19)])
def test_point_on_edge_or_vertex_is_covered(coordinate):
    enriched, _, _ = enrich_chargers(chargers(coordinate), lsoas(), TIMESTAMP)
    assert enriched.iloc[0]["lsoa_code"] == "W01000001"


def test_multiple_candidates_are_flagged_and_listed():
    areas = lsoas([
        {"code": "W01000002", "geometry": box(-3.2, 51.49, -3.19, 51.51), "percentage": 20},
        {"code": "W01000001", "geometry": box(-3.21, 51.49, -3.2, 51.51), "percentage": 10},
    ])
    enriched, _, report = enrich_chargers(chargers((51.5, -3.2)), areas, TIMESTAMP)
    row = enriched.iloc[0]
    assert row["deprivation_match_count"] == 2
    assert bool(row["deprivation_match_ambiguous"])
    assert row["deprivation_candidate_codes"] == "W01000001|W01000002"
    assert row["deprivation_match_status"] == "ambiguous_resolved"
    assert report["ambiguous_match_count"] == 1


def test_ambiguity_resolution_is_deterministic_with_code_tiebreak():
    areas = lsoas([
        {"code": "W01000002", "geometry": box(-3.2, 51.49, -3.19, 51.51), "percentage": 20},
        {"code": "W01000001", "geometry": box(-3.21, 51.49, -3.2, 51.51), "percentage": 10},
    ])
    first = enrich_chargers(chargers((51.5, -3.2)), areas, TIMESTAMP)[0].iloc[0]
    second = enrich_chargers(chargers((51.5, -3.2)), areas.iloc[::-1], TIMESTAMP)[0].iloc[0]
    assert first["lsoa_code"] == second["lsoa_code"]
    assert "tie by lsoa_code" in first["deprivation_match_method"]


@pytest.mark.parametrize("coordinate", [(95, 0), (0, 181), (None, 0), (0, None)])
def test_invalid_or_missing_coordinates_are_unresolved(coordinate):
    enriched, unresolved, _ = enrich_chargers(chargers(coordinate), lsoas(), TIMESTAMP)
    assert len(enriched) == len(unresolved) == 1
    assert "invalid charger coordinates" in enriched.iloc[0]["deprivation_enrichment_notes"]


def test_missing_wimd_percentage_is_unresolved():
    enriched, unresolved, report = enrich_chargers(
        chargers((51.5, -3.2)), lsoas([{"code": "W01000001", "geometry": box(-3.21, 51.49, -3.19, 51.51), "percentage": None}]), TIMESTAMP
    )
    assert len(unresolved) == 1
    assert pd.isna(enriched.iloc[0]["deprivation_score"])
    assert report["missing_wimd_percentage_count"] == 1


def test_percentage_is_not_rescaled():
    enriched, _, _ = enrich_chargers(
        chargers((51.5, -3.2)), lsoas([{"code": "W01000001", "geometry": box(-3.21, 51.49, -3.19, 51.51), "percentage": 78.6}]), TIMESTAMP
    )
    assert enriched.iloc[0]["deprivation_score"] == 78.6


def test_all_flood_fields_are_preserved_unchanged():
    source = chargers((51.5, -3.2))
    enriched, _, _ = enrich_chargers(source, lsoas(), TIMESTAMP)
    for field, value in FLOOD_FIELDS.items():
        assert enriched.iloc[0][field] == value


def test_duplicate_station_ids_are_reported_without_deletion():
    enriched, _, report = enrich_chargers(chargers((51.5, -3.2), (51.501, -3.201), duplicate=True), lsoas(), TIMESTAMP)
    assert len(enriched) == 2
    assert report["duplicate_station_id_count"] == 2


def test_lsoa_crs_is_transformed_for_matching():
    projected = lsoas().to_crs("EPSG:3857")
    enriched, _, report = enrich_chargers(chargers((51.5, -3.2)), projected, TIMESTAMP)
    assert enriched.iloc[0]["lsoa_code"] == "W01000001"
    assert report["analysis_crs"] == "EPSG:27700"


def test_charger_and_deprivation_provenance_are_retained():
    enriched, _, report = enrich_chargers(chargers((51.5, -3.2)), lsoas(), TIMESTAMP)
    row = enriched.iloc[0]
    assert row["data_provider"] == "provider"
    assert row["deprivation_source"] == "WIMD indicators"
    assert row["deprivation_source_release"] == "WIMD 2025"
    assert row["deprivation_enrichment_timestamp"] == TIMESTAMP
    assert report["provenance_incomplete_count"] == 0


def test_output_schema_and_checksums(workspace_tmp_dir):
    enriched, unresolved, report = enrich_chargers(chargers((51.5, -3.2)), lsoas(), TIMESTAMP)
    assert OUTPUT_FIELDS.issubset(enriched.columns)
    output = workspace_tmp_dir / "enriched.csv"
    unresolved_output = workspace_tmp_dir / "unresolved.csv"
    report_output = workspace_tmp_dir / "report.json"
    write_outputs(enriched, unresolved, report, output, unresolved_output, report_output)
    saved = json.loads(report_output.read_text(encoding="utf-8"))
    assert set(saved["output_checksums"]) == {"enriched.csv", "unresolved.csv"}
    assert len(pd.read_csv(output)) == 1
