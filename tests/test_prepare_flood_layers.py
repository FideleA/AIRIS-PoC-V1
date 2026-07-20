import shutil
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Polygon, box

from scripts.prepare_flood_layers import (
    ATTRIBUTION,
    CATALOGUE_PUBLICATION_DATE,
    ILLUSTRATIVE_AIRIS_RISK_SCORES,
    LAYER_CONFIGS,
    PROCESSING_CRS,
    FloodPreparationError,
    normalise_risk_band,
    prepare_flood_subset,
    processing_bbox,
    read_bounded_source,
    repair_polygonal_geometry,
    write_flood_geopackage,
)


@pytest.fixture
def workspace_tmp_dir():
    path = Path(__file__).parent / ".tmp" / str(uuid4())
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def boundary(crs=PROCESSING_CRS):
    return gpd.GeoDataFrame(
        [{"authority_code": "W06000015", "geometry": box(0, 0, 100, 100)}],
        geometry="geometry",
        crs=crs,
    )


def source_frame(records=None, crs=PROCESSING_CRS):
    records = records or [
        {
            "objectid": 1,
            "mm_id": "one",
            "pub_date": "2026-05-21",
            "risk": "High",
            "geometry": box(10, 10, 20, 20),
        }
    ]
    return gpd.GeoDataFrame(records, geometry="geometry", crs=crs)


@pytest.mark.parametrize("band", ["High", "Medium", "Low"])
def test_source_risk_bands_normalise_exactly(band):
    assert normalise_risk_band(band) == band


def test_illustrative_mapping_includes_inferred_very_low():
    assert ILLUSTRATIVE_AIRIS_RISK_SCORES == {
        "Very Low": 10,
        "Low": 35,
        "Medium": 65,
        "High": 90,
    }


def test_unknown_classification_fails():
    with pytest.raises(FloodPreparationError, match="Unknown"):
        normalise_risk_band("Severe")


@pytest.mark.parametrize("value", [None, "", "   ", pd.NA])
def test_missing_classification_fails(value):
    with pytest.raises(FloodPreparationError, match="Missing"):
        normalise_risk_band(value)


def test_polygon_and_multipolygon_are_supported():
    polygon = box(1, 1, 2, 2)
    multipolygon = MultiPolygon([box(3, 3, 4, 4)])
    assert repair_polygonal_geometry(polygon).equals(polygon)
    assert repair_polygonal_geometry(multipolygon).equals(multipolygon)


def test_repairable_invalid_geometry_is_repaired():
    bow_tie = Polygon([(10, 10), (20, 20), (20, 10), (10, 20)])
    repaired = repair_polygonal_geometry(bow_tie)
    assert not bow_tie.is_valid
    assert repaired is not None
    assert repaired.is_valid


def test_unrecoverable_non_polygon_geometry_returns_none():
    geometry = GeometryCollection([LineString([(0, 0), (1, 1)])])
    assert repair_polygonal_geometry(geometry) is None


def test_processing_bbox_uses_documented_margin():
    assert processing_bbox(boundary(), margin_metres=5) == (-5.0, -5.0, 105.0, 105.0)


def test_bounded_read_passes_bbox_to_reader(workspace_tmp_dir, monkeypatch):
    source_path = workspace_tmp_dir / "source.gpkg"
    source_path.touch()
    config = replace(LAYER_CONFIGS[0], source_path=source_path)
    monkeypatch.setattr(
        "scripts.prepare_flood_layers.pyogrio.read_info",
        lambda *args, **kwargs: {"crs": PROCESSING_CRS, "features": 99},
    )
    calls = {}

    def reader(path, **kwargs):
        calls.update(kwargs)
        return source_frame()

    subset, count, bbox = read_bounded_source(config, boundary(), reader=reader)
    assert len(subset) == 1
    assert count == 99
    assert calls["layer"] == config.source_layer
    assert calls["bbox"] == bbox
    assert bbox == (-100.0, -100.0, 200.0, 200.0)


def test_subset_repairs_and_flags_without_discarding_records():
    bow_tie = Polygon([(10, 10), (20, 20), (20, 10), (10, 20)])
    unrecoverable = GeometryCollection([LineString([(30, 30), (40, 40)])])
    records = [
        {"objectid": 1, "mm_id": "a", "pub_date": "2026-05-21", "risk": "High", "geometry": box(1, 1, 2, 2)},
        {"objectid": 2, "mm_id": "b", "pub_date": "2026-05-21", "risk": "Medium", "geometry": bow_tie},
        {"objectid": 3, "mm_id": "c", "pub_date": "2026-05-21", "risk": "Low", "geometry": unrecoverable},
    ]
    prepared, metrics = prepare_flood_subset(
        source_frame(records), boundary(), LAYER_CONFIGS[0], "ABC123"
    )
    assert len(prepared) == 3
    assert metrics == {
        "cardiff_subset_features": 3,
        "invalid_geometries": 2,
        "repaired_geometries": 1,
        "unrepaired_geometries": 1,
    }
    assert prepared["geometry_status"].tolist() == ["valid", "repaired", "unrepaired"]
    assert prepared.geometry.iloc[2] is None


def test_crs_is_converted_to_project_processing_crs():
    projected_boundary = gpd.GeoDataFrame(
        [{"geometry": box(315000, 175000, 316000, 176000)}],
        geometry="geometry",
        crs=PROCESSING_CRS,
    )
    source = source_frame(
        [{"objectid": 1, "mm_id": "one", "pub_date": "2026-05-21", "risk": "High", "geometry": box(315100, 175100, 315200, 175200)}]
    ).to_crs("EPSG:4326")
    prepared, _ = prepare_flood_subset(
        source, projected_boundary, LAYER_CONFIGS[0], "ABC123"
    )
    assert len(prepared) == 1
    assert prepared.crs.to_epsg() == 27700


def test_catalogue_and_layer_dates_are_preserved_separately():
    prepared, _ = prepare_flood_subset(
        source_frame(), boundary(), LAYER_CONFIGS[0], "ABC123"
    )
    row = prepared.iloc[0]
    assert row["catalogue_publication_date"] == CATALOGUE_PUBLICATION_DATE
    assert row["layer_publication_date"] == "2026-05-21"
    assert row["source_file_checksum"] == "ABC123"
    assert row["attribution"] == ATTRIBUTION


def test_sea_schema_without_objectid_gets_deterministic_internal_id():
    config = LAYER_CONFIGS[1]
    records = [{"mm_id": "sea-1", "pub_date": "2026-05-21", "risk": "Low", "geometry": box(1, 1, 2, 2)}]
    first, _ = prepare_flood_subset(source_frame(records), boundary(), config, "ABC123")
    second, _ = prepare_flood_subset(source_frame(records), boundary(), config, "ABC123")
    assert "objectid" not in first.columns
    assert first.iloc[0]["source_feature_id"] == second.iloc[0]["source_feature_id"]
    assert first.iloc[0]["source_feature_id"].startswith("FRAW_SEA:sha256:")


def test_missing_exact_source_classification_field_fails():
    source = source_frame().rename(columns={"risk": "Risk"})
    with pytest.raises(FloodPreparationError, match="missing required fields"):
        prepare_flood_subset(source, boundary(), LAYER_CONFIGS[0], "ABC123")


def test_geopackage_write_retains_metadata(workspace_tmp_dir):
    prepared, _ = prepare_flood_subset(
        source_frame(), boundary(), LAYER_CONFIGS[0], "ABC123"
    )
    output = workspace_tmp_dir / "flood.gpkg"
    write_flood_geopackage(prepared, output, "flood")
    restored = gpd.read_file(output, layer="flood")
    assert restored.crs.to_epsg() == 27700
    assert restored.iloc[0]["catalogue_publication_date"] == CATALOGUE_PUBLICATION_DATE
    assert restored.iloc[0]["layer_publication_date"] == "2026-05-21"
