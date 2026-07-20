import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import MultiPolygon, Polygon, box

from scripts.prepare_deprivation_data import (
    ATTRIBUTION,
    DeprivationPreparationError,
    add_provenance,
    dissolve_lsoa_parts,
    filter_wimd_percentage,
    join_wimd_to_boundaries,
    select_cardiff_lsoas,
)


def wimd_row(**changes):
    row = {
        "Indicator": "People in income deprivation",
        "Data description": "Percentage",
        "Area code": "W01000001",
        "Area name": "Example LSOA",
        "Data values": "12.5",
    }
    row.update(changes)
    return row


def boundary_parts(rows=None, crs="EPSG:27700"):
    rows = rows or [
        {"lsoa21cd": "W01000001", "lsoa21nm": "Area A", "lsoa21nmw": "Ardal A", "geometry": box(0, 0, 1, 1)}
    ]
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=crs)


def test_exact_indicator_and_percentage_filtering():
    source = pd.DataFrame([
        wimd_row(),
        wimd_row(**{"Indicator": "Children in income deprivation", "Area code": "W01000002"}),
        wimd_row(**{"Data description": "Rank", "Area code": "W01000003"}),
        wimd_row(**{"Area code": "E01000001"}),
    ])
    result = filter_wimd_percentage(source)
    assert result["lsoa_code"].tolist() == ["W01000001"]


def test_percentage_is_not_multiplied():
    result = filter_wimd_percentage(pd.DataFrame([wimd_row(**{"Data values": "12.5"})]))
    assert result.loc[0, "income_deprivation_percentage"] == 12.5
    assert result.loc[0, "deprivation_score"] == 12.5


def test_duplicate_percentage_rows_fail():
    with pytest.raises(DeprivationPreparationError, match="Duplicate"):
        filter_wimd_percentage(pd.DataFrame([wimd_row(), wimd_row()]))


@pytest.mark.parametrize("value", [None, "", "not-a-number"])
def test_missing_or_non_numeric_percentage_fails(value):
    with pytest.raises(DeprivationPreparationError, match="non-numeric"):
        filter_wimd_percentage(pd.DataFrame([wimd_row(**{"Data values": value})]))


def test_polygon_parts_are_dissolved_to_one_multipolygon():
    parts = boundary_parts([
        {"lsoa21cd": "W01000001", "lsoa21nm": "Area A", "lsoa21nmw": "Ardal A", "geometry": box(0, 0, 1, 1)},
        {"lsoa21cd": "W01000001", "lsoa21nm": "Area A", "lsoa21nmw": "Ardal A", "geometry": box(2, 0, 3, 1)},
    ])
    result = dissolve_lsoa_parts(parts)
    assert len(result) == 1
    assert isinstance(result.geometry.iloc[0], MultiPolygon)


def test_conflicting_names_within_code_fail():
    parts = boundary_parts([
        {"lsoa21cd": "W01000001", "lsoa21nm": "Area A", "lsoa21nmw": "Ardal A", "geometry": box(0, 0, 1, 1)},
        {"lsoa21cd": "W01000001", "lsoa21nm": "Different", "lsoa21nmw": "Ardal A", "geometry": box(1, 0, 2, 1)},
    ])
    with pytest.raises(DeprivationPreparationError, match="Conflicting"):
        dissolve_lsoa_parts(parts)


def test_polygon_and_multipolygon_outputs_are_supported():
    rows = [
        {"lsoa21cd": "W01000001", "lsoa21nm": "A", "lsoa21nmw": "A", "geometry": box(0, 0, 1, 1)},
        {"lsoa21cd": "W01000002", "lsoa21nm": "B", "lsoa21nmw": "B", "geometry": MultiPolygon([box(2, 0, 3, 1), box(4, 0, 5, 1)])},
    ]
    result = dissolve_lsoa_parts(boundary_parts(rows))
    assert set(result.geometry.geom_type) == {"Polygon", "MultiPolygon"}


def test_complete_code_join():
    boundaries = dissolve_lsoa_parts(boundary_parts())
    wimd = filter_wimd_percentage(pd.DataFrame([wimd_row()]))
    result = join_wimd_to_boundaries(boundaries, wimd)
    assert result.loc[0, "deprivation_score"] == 12.5


def test_unmatched_code_fails_join():
    boundaries = dissolve_lsoa_parts(boundary_parts())
    wimd = filter_wimd_percentage(pd.DataFrame([wimd_row(**{"Area code": "W01000002"})]))
    with pytest.raises(DeprivationPreparationError, match="code mismatch"):
        join_wimd_to_boundaries(boundaries, wimd)


def test_touching_only_geometry_is_excluded():
    lsoas = gpd.GeoDataFrame({"lsoa_code": ["W01000001"]}, geometry=[box(1, 0, 2, 1)], crs="EPSG:27700")
    cardiff = gpd.GeoDataFrame({"authority_code": ["W06000015"]}, geometry=[box(0, 0, 1, 1)], crs="EPSG:27700")
    assert select_cardiff_lsoas(lsoas, cardiff).empty


def test_meaningful_overlap_selects_and_preserves_full_geometry():
    geometry = box(0.5, 0, 1.4, 2)
    lsoas = gpd.GeoDataFrame({"lsoa_code": ["W01000001"]}, geometry=[geometry], crs="EPSG:27700")
    cardiff = gpd.GeoDataFrame({"authority_code": ["W06000015"]}, geometry=[box(0, 0, 1, 2)], crs="EPSG:27700")
    result = select_cardiff_lsoas(lsoas, cardiff, minimum_overlap_m2=0.1)
    assert len(result) == 1
    assert result.geometry.iloc[0].equals(geometry)


def test_small_boundary_misalignment_sliver_is_excluded():
    lsoas = gpd.GeoDataFrame(
        {"lsoa_code": ["W01000001"]}, geometry=[box(0, 0, 100, 100)], crs="EPSG:27700"
    )
    cardiff = gpd.GeoDataFrame(
        {"authority_code": ["W06000015"]}, geometry=[box(0, 0, 1, 100)], crs="EPSG:27700"
    )
    assert select_cardiff_lsoas(lsoas, cardiff).empty


def test_invalid_geometry_fails_validation():
    bowtie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])
    with pytest.raises(DeprivationPreparationError, match="invalid geometry"):
        dissolve_lsoa_parts(boundary_parts([{"lsoa21cd": "W01000001", "lsoa21nm": "A", "lsoa21nmw": "A", "geometry": bowtie}]))


def test_crs_is_converted_to_epsg_27700():
    source = boundary_parts(crs="EPSG:4326")
    assert dissolve_lsoa_parts(source).crs.to_epsg() == 27700


def test_output_schema_and_provenance():
    boundaries = dissolve_lsoa_parts(boundary_parts())
    joined = join_wimd_to_boundaries(boundaries, filter_wimd_percentage(pd.DataFrame([wimd_row()])))
    result = add_provenance(joined, timestamp="2026-01-01T00:00:00+00:00")
    expected = {
        "lsoa_code", "lsoa_name", "lsoa_boundary_name_cy",
        "income_deprivation_percentage", "deprivation_score", "release_name",
        "source_publication_date", "processing_timestamp", "licence", "attribution", "geometry",
    }
    assert expected.issubset(result.columns)
    assert result.loc[0, "attribution"] == ATTRIBUTION
    assert result.geometry.is_valid.all()
