import json
import shutil
from pathlib import Path
from uuid import uuid4

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import MultiPolygon, Point, box

from charging_schema import CANONICAL_CHARGING_FIELDS
from scripts.filter_charging_sites_to_cardiff import (
    BOUNDARY_FIELDS,
    BoundaryFilterError,
    classify_charging_locations,
    write_filter_outputs,
)


def canonical_record(station_id, latitude, longitude, **overrides):
    record = {
        "station_id": station_id,
        "source_record_id": station_id.removeprefix("airis_"),
        "station_name": f"Station {station_id}",
        "address": "Example address",
        "postcode": "CF10 1AA",
        "latitude": latitude,
        "longitude": longitude,
        "operator_name": "Example Operator",
        "data_provider": "Example Provider",
        "operational_status": "operational",
        "number_of_evses": 1,
        "number_of_connectors": 2,
        "maximum_power_kw": 50,
        "access_type": "public",
        "usage_cost": None,
        "source_url": "https://example.invalid/station",
        "source_last_updated": "2026-07-01T00:00:00Z",
        "licence": "Example licence",
        "attribution": "Example attribution",
        "verification_status": "unreviewed",
        "verification_notes": None,
    }
    record.update(overrides)
    return record


def projected_point_to_wgs84(easting, northing):
    point = gpd.GeoSeries([Point(easting, northing)], crs="EPSG:27700").to_crs(4326).iloc[0]
    return point.y, point.x


@pytest.fixture
def boundary():
    return gpd.GeoDataFrame(
        [
            {
                "authority_code": "W06000015",
                "name_en": "Cardiff",
                "source_dataset": "Synthetic Cardiff boundary",
                "geometry": MultiPolygon([box(310000, 170000, 320000, 180000)]),
            }
        ],
        geometry="geometry",
        crs="EPSG:27700",
    )


@pytest.fixture
def workspace_tmp_dir():
    path = Path(__file__).parent / ".tmp" / str(uuid4())
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def classify(records, boundary):
    return classify_charging_locations(
        pd.DataFrame(records, columns=CANONICAL_CHARGING_FIELDS),
        boundary,
        filter_timestamp="2026-07-20T12:00:00+00:00",
    )


def test_point_clearly_inside(boundary):
    latitude, longitude = projected_point_to_wgs84(315000, 175000)
    included, outside, report = classify(
        [canonical_record("airis_inside", latitude, longitude)], boundary
    )
    assert included.iloc[0]["boundary_status"] == "inside"
    assert outside.empty
    assert report["inside_count"] == 1


def test_point_clearly_outside(boundary):
    latitude, longitude = projected_point_to_wgs84(330000, 190000)
    included, outside, report = classify(
        [canonical_record("airis_outside", latitude, longitude)], boundary
    )
    assert included.empty
    assert outside.iloc[0]["boundary_status"] == "outside"
    assert report["outside_count"] == 1


def test_point_exactly_on_edge_is_included_as_boundary(boundary):
    latitude, longitude = projected_point_to_wgs84(310000, 175000)
    included, outside, report = classify(
        [canonical_record("airis_edge", latitude, longitude)], boundary
    )
    assert included.iloc[0]["boundary_status"] == "boundary"
    assert outside.empty
    assert report["boundary_count"] == 1


def test_point_exactly_on_vertex_is_included_as_boundary(boundary):
    latitude, longitude = projected_point_to_wgs84(310000, 170000)
    included, outside, _ = classify(
        [canonical_record("airis_vertex", latitude, longitude)], boundary
    )
    assert included.iloc[0]["boundary_status"] == "boundary"
    assert outside.empty


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(91, -3.18), (51.48, 181), (None, -3.18)],
    ids=["invalid-latitude", "invalid-longitude", "missing-coordinate"],
)
def test_invalid_or_missing_coordinates_are_flagged_and_retained(
    boundary, latitude, longitude
):
    included, outside, report = classify(
        [canonical_record("airis_invalid", latitude, longitude)], boundary
    )
    assert included.empty
    assert len(outside) == 1
    assert outside.iloc[0]["boundary_status"] == "invalid_coordinates"
    assert report["invalid_coordinates"] == 1
    assert report["record_accounting"]["accounted_records"] == 1


def test_duplicate_station_id_is_reported_without_dropping_rows(boundary):
    inside = projected_point_to_wgs84(315000, 175000)
    outside_point = projected_point_to_wgs84(330000, 190000)
    records = [
        canonical_record("airis_duplicate", *inside),
        canonical_record("airis_duplicate", *outside_point),
    ]
    included, outside, report = classify(records, boundary)
    assert len(included) + len(outside) == 2
    assert report["duplicate_station_ids"] == {
        "count": 1,
        "values": ["airis_duplicate"],
    }


def test_duplicate_coordinates_are_reported(boundary):
    latitude, longitude = projected_point_to_wgs84(315000, 175000)
    records = [
        canonical_record("airis_one", latitude, longitude),
        canonical_record("airis_two", latitude, longitude),
    ]
    included, outside, report = classify(records, boundary)
    assert len(included) == 2
    assert outside.empty
    assert report["duplicate_coordinates"]["group_count"] == 1
    assert report["duplicate_coordinates"]["record_count"] == 2


def test_crs_mismatch_is_reprojected_before_evaluation(boundary):
    boundary_web_mercator = boundary.to_crs("EPSG:3857")
    latitude, longitude = projected_point_to_wgs84(315000, 175000)
    included, outside, report = classify(
        [canonical_record("airis_crs", latitude, longitude)],
        boundary_web_mercator,
    )
    assert len(included) == 1
    assert outside.empty
    assert report["evaluation_crs"] == "EPSG:3857"


def test_all_source_and_boundary_provenance_fields_are_retained(boundary):
    latitude, longitude = projected_point_to_wgs84(315000, 175000)
    source = canonical_record(
        "airis_provenance",
        latitude,
        longitude,
        source_record_id="source-007",
        attribution="Provider attribution",
    )
    included, _, _ = classify([source], boundary)
    row = included.iloc[0]
    for field in CANONICAL_CHARGING_FIELDS:
        expected = source[field]
        actual = row[field]
        if expected is None:
            assert pd.isna(actual)
        else:
            assert actual == expected
    assert set(BOUNDARY_FIELDS) <= set(included.columns)
    assert row["boundary_authority_code"] == "W06000015"
    assert row["boundary_authority_name"] == "Cardiff"
    assert row["boundary_dataset"] == "Synthetic Cardiff boundary"


def test_missing_required_charger_field_fails_before_spatial_processing(boundary):
    latitude, longitude = projected_point_to_wgs84(315000, 175000)
    data = pd.DataFrame([canonical_record("airis_missing", latitude, longitude)]).drop(
        columns=["data_provider"]
    )
    with pytest.raises(BoundaryFilterError, match="Missing canonical charging fields"):
        classify_charging_locations(data, boundary)


def test_output_files_are_lossless_and_report_their_sizes(boundary, workspace_tmp_dir):
    inside = projected_point_to_wgs84(315000, 175000)
    outside_point = projected_point_to_wgs84(330000, 190000)
    included, outside, report = classify(
        [
            canonical_record("airis_inside", *inside),
            canonical_record("airis_outside", *outside_point),
        ],
        boundary,
    )
    included_path = workspace_tmp_dir / "included.csv"
    outside_path = workspace_tmp_dir / "outside.csv"
    report_path = workspace_tmp_dir / "report.json"
    written = write_filter_outputs(
        included,
        outside,
        report,
        included_path=included_path,
        outside_path=outside_path,
        report_path=report_path,
    )
    assert len(pd.read_csv(included_path)) == 1
    assert len(pd.read_csv(outside_path)) == 1
    stored = json.loads(report_path.read_text(encoding="utf-8"))
    assert stored == written
    assert stored["output_file_sizes"]["cardiff_charging_sites_csv_bytes"] == included_path.stat().st_size
    assert stored["output_file_sizes"]["outside_boundary_csv_bytes"] == outside_path.stat().st_size
    assert stored["output_file_sizes"]["quality_report_json_bytes"] == report_path.stat().st_size
