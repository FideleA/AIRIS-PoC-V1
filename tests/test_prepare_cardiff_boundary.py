import shutil
from pathlib import Path
from uuid import uuid4

import geopandas as gpd
import pytest
from shapely.geometry import MultiPolygon, Polygon, box

from scripts.prepare_cardiff_boundary import (
    CARDIFF_AUTHORITY_CODE,
    CARDIFF_NAME_EN,
    CARDIFF_NAME_CY,
    PROJECTED_LAYER,
    SOURCE_ATTRIBUTION,
    SOURCE_DATASET_NAME,
    SOURCE_LICENCE,
    SOURCE_PUBLICATION_DATE,
    WEB_LAYER,
    BoundaryPreparationError,
    prepare_cardiff_boundary,
    select_cardiff_boundary,
    to_web_crs,
    write_boundary_geopackage,
)


def boundaries(records, crs="EPSG:27700"):
    return gpd.GeoDataFrame(records, geometry="geometry", crs=crs)


def cardiff_record(**overrides):
    record = {
        "census_cod": CARDIFF_AUTHORITY_CODE,
        "name_en": CARDIFF_NAME_EN,
        "name_cy": CARDIFF_NAME_CY,
        "id": 14,
        "geometry": MultiPolygon([box(310000, 170000, 320000, 180000)]),
    }
    record.update(overrides)
    return record


@pytest.fixture
def workspace_tmp_dir():
    path = Path(__file__).parent / ".tmp" / str(uuid4())
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_selects_exactly_one_cardiff_feature_by_official_code():
    data = boundaries(
        [
            cardiff_record(),
            {
                "census_cod": "W06000016",
                "name_en": "Rhondda Cynon Taf",
                "name_cy": "Rhondda Cynon Taf",
                "id": 15,
                "geometry": MultiPolygon([box(290000, 180000, 300000, 190000)]),
            },
        ]
    )
    selected = select_cardiff_boundary(data)
    assert len(selected) == 1
    assert selected.iloc[0]["census_cod"] == CARDIFF_AUTHORITY_CODE


def test_exact_name_fallback_when_official_code_field_is_unavailable():
    data = boundaries(
        [
            {
                "name_en": CARDIFF_NAME_EN,
                "name_cy": CARDIFF_NAME_CY,
                "geometry": MultiPolygon([box(310000, 170000, 320000, 180000)]),
            },
            {
                "name_en": "Cardiff Bay",
                "name_cy": "Bae Caerdydd",
                "geometry": MultiPolygon([box(310000, 160000, 320000, 169000)]),
            },
        ]
    )
    selected = select_cardiff_boundary(data)
    assert len(selected) == 1
    assert selected.iloc[0]["name_en"] == CARDIFF_NAME_EN


def test_no_cardiff_feature_fails_safely():
    data = boundaries(
        [
            cardiff_record(
                census_cod="W06000016",
                name_en="Rhondda Cynon Taf",
                name_cy="Rhondda Cynon Taf",
            )
        ]
    )
    with pytest.raises(BoundaryPreparationError, match="found 0"):
        select_cardiff_boundary(data)


def test_duplicate_cardiff_features_fail_safely():
    data = boundaries([cardiff_record(), cardiff_record(id=114)])
    with pytest.raises(BoundaryPreparationError, match="found 2"):
        select_cardiff_boundary(data)


def test_invalid_geometry_is_repaired_only_when_needed():
    bow_tie = Polygon(
        [(310000, 170000), (320000, 180000), (320000, 170000), (310000, 180000)]
    )
    assert not bow_tie.is_valid
    prepared = prepare_cardiff_boundary(boundaries([cardiff_record(geometry=bow_tie)]))
    assert prepared.geometry.is_valid.all()
    assert bool(prepared.iloc[0]["geometry_repaired"]) is True


def test_valid_geometry_is_not_repaired_or_altered():
    data = boundaries([cardiff_record()])
    original = data.geometry.iloc[0]
    prepared = prepare_cardiff_boundary(data)
    assert bool(prepared.iloc[0]["geometry_repaired"]) is False
    assert prepared.geometry.iloc[0].equals_exact(original, tolerance=0)


def test_crs_conversion_supports_web_map_display():
    prepared = prepare_cardiff_boundary(boundaries([cardiff_record()]))
    web = to_web_crs(prepared)
    assert prepared.crs.to_epsg() == 27700
    assert web.crs.to_epsg() == 4326
    assert web.geometry.is_valid.all()


def test_required_metadata_is_retained():
    prepared = prepare_cardiff_boundary(boundaries([cardiff_record()]))
    row = prepared.iloc[0]
    assert row["authority_code"] == CARDIFF_AUTHORITY_CODE
    assert row["name_en"] == CARDIFF_NAME_EN
    assert row["name_cy"] == CARDIFF_NAME_CY
    assert row["source_dataset"] == SOURCE_DATASET_NAME
    assert row["source_publication_date"] == SOURCE_PUBLICATION_DATE
    assert row["licence"] == SOURCE_LICENCE
    assert row["attribution"] == SOURCE_ATTRIBUTION
    assert row["coastline_convention"] == "High water mark"


def test_geopackage_contains_projected_and_web_layers(workspace_tmp_dir):
    prepared = prepare_cardiff_boundary(boundaries([cardiff_record()]))
    output = workspace_tmp_dir / "cardiff_boundary.gpkg"
    write_boundary_geopackage(prepared, output)

    projected = gpd.read_file(output, layer=PROJECTED_LAYER)
    web = gpd.read_file(output, layer=WEB_LAYER)
    assert len(projected) == len(web) == 1
    assert projected.crs.to_epsg() == 27700
    assert web.crs.to_epsg() == 4326
    assert projected.iloc[0]["authority_code"] == CARDIFF_AUTHORITY_CODE
