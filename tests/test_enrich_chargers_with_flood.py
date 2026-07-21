import shutil
from pathlib import Path
from uuid import uuid4

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import MultiPolygon, box

from scripts.enrich_chargers_with_flood import (
    NO_MATCH_TEXT,
    VERY_LOW_BAND,
    enrich_chargers,
    write_outputs,
)
from scripts.prepare_flood_layers import (
    ATTRIBUTION,
    CATALOGUE_PUBLICATION_DATE,
    LICENCE,
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


def chargers(*coordinates):
    return pd.DataFrame(
        [
            {
                "station_id": f"station-{index}",
                "station_name": f"Station {index}",
                "latitude": latitude,
                "longitude": longitude,
                "data_provider": "test-provider",
            }
            for index, (latitude, longitude) in enumerate(coordinates, start=1)
        ]
    )


def flood_layer(records=None, crs="EPSG:4326"):
    records = records or []
    enriched = []
    for index, record in enumerate(records, start=1):
        enriched.append(
            {
                "risk_band": record["risk_band"],
                "catalogue_publication_date": CATALOGUE_PUBLICATION_DATE,
                "layer_publication_date": "2026-05-21",
                "source_file_checksum": "A" * 64,
                "source_dataset_version_note": "synthetic test layer",
                "source_layer": "synthetic",
                "licence": LICENCE,
                "attribution": ATTRIBUTION,
                "source_feature_id": f"feature-{index}",
                "geometry": record["geometry"],
            }
        )
    columns = [
        "risk_band", "catalogue_publication_date", "layer_publication_date",
        "source_file_checksum", "source_dataset_version_note", "source_layer",
        "licence", "attribution", "source_feature_id", "geometry",
    ]
    return gpd.GeoDataFrame(enriched, columns=columns, geometry="geometry", crs=crs)


def layers(river=None, sea=None, surface=None):
    return {
        "river": flood_layer(river),
        "sea": flood_layer(sea),
        "surface_water": flood_layer(surface),
    }


def test_site_outside_every_polygon_is_very_low_without_no_risk_claim():
    enriched, unresolved, report = enrich_chargers(
        chargers((51.5, -3.2)), layers(), TIMESTAMP
    )
    row = enriched.iloc[0]
    assert row["flood_score"] == 10
    assert row["flood_river_band"] == VERY_LOW_BAND
    assert row["flood_sea_band"] == VERY_LOW_BAND
    assert row["flood_surface_water_band"] == VERY_LOW_BAND
    assert row["flood_dominant_source"] == "river|sea|surface_water"
    assert "no flood risk" not in report["no_match_interpretation"].lower()
    assert unresolved.empty
    assert report["no_match_count"] == 1
    assert report["no_match_band"] == VERY_LOW_BAND
    assert report["no_match_score"] == 10


@pytest.mark.parametrize(
    ("band", "score"), [("Low", 35), ("Medium", 65), ("High", 90)]
)
def test_low_medium_and_high_matches(band, score):
    polygon = box(-3.21, 51.49, -3.19, 51.51)
    enriched, _, _ = enrich_chargers(
        chargers((51.5, -3.2)), layers(river=[{"risk_band": band, "geometry": polygon}]), TIMESTAMP
    )
    assert enriched.iloc[0]["flood_river_band"] == band
    assert enriched.iloc[0]["flood_river_score"] == score
    assert enriched.iloc[0]["flood_score"] == score


def test_overlapping_hazard_sources_use_maximum_score():
    polygon = box(-3.21, 51.49, -3.19, 51.51)
    enriched, _, report = enrich_chargers(
        chargers((51.5, -3.2)),
        layers(
            river=[{"risk_band": "Low", "geometry": polygon}],
            sea=[{"risk_band": "Medium", "geometry": polygon}],
        ),
        TIMESTAMP,
    )
    row = enriched.iloc[0]
    assert row["flood_score"] == 65
    assert row["flood_dominant_source"] == "sea"
    assert row["flood_hazard_source_count"] == 2
    assert report["overlapping_hazard_count"] == 1


def test_multiple_polygons_from_one_source_retain_highest_and_count_overlap():
    polygon = box(-3.21, 51.49, -3.19, 51.51)
    enriched, _, _ = enrich_chargers(
        chargers((51.5, -3.2)),
        layers(river=[
            {"risk_band": "Low", "geometry": polygon},
            {"risk_band": "High", "geometry": MultiPolygon([polygon])},
        ]),
        TIMESTAMP,
    )
    row = enriched.iloc[0]
    assert row["flood_river_band"] == "High"
    assert row["flood_river_match_count"] == 2
    assert row["flood_match_count"] == 2


def test_equal_maximum_scores_record_all_tied_sources():
    polygon = box(-3.21, 51.49, -3.19, 51.51)
    enriched, _, _ = enrich_chargers(
        chargers((51.5, -3.2)),
        layers(
            river=[{"risk_band": "High", "geometry": polygon}],
            sea=[{"risk_band": "High", "geometry": polygon}],
        ),
        TIMESTAMP,
    )
    assert enriched.iloc[0]["flood_dominant_source"] == "river|sea"


def test_boundary_edge_point_is_included():
    polygon = box(-3.2, 51.5, -3.1, 51.6)
    enriched, _, _ = enrich_chargers(
        chargers((51.5, -3.2)), layers(river=[{"risk_band": "Low", "geometry": polygon}]), TIMESTAMP
    )
    assert enriched.iloc[0]["flood_river_band"] == "Low"
    assert enriched.iloc[0]["flood_river_match_count"] == 1


@pytest.mark.parametrize("coordinate", [(None, -3.2), (95, -3.2), (51.5, -181), ("bad", -3.2)])
def test_invalid_coordinates_are_preserved_and_unresolved(coordinate):
    enriched, unresolved, report = enrich_chargers(
        chargers(coordinate), layers(), TIMESTAMP
    )
    assert len(enriched) == 1
    assert len(unresolved) == 1
    assert enriched.iloc[0]["flood_enrichment_status"] == "unresolved"
    assert "invalid charger coordinates" in enriched.iloc[0]["flood_enrichment_notes"]
    assert pd.isna(enriched.iloc[0]["flood_score"])
    assert report["unresolved_count"] == 1


def test_charger_provenance_is_retained():
    source = chargers((51.5, -3.2))
    enriched, _, _ = enrich_chargers(source, layers(), TIMESTAMP)
    assert enriched.iloc[0]["station_id"] == source.iloc[0]["station_id"]
    assert enriched.iloc[0]["data_provider"] == "test-provider"
    assert enriched.iloc[0]["flood_data_version"].startswith("FRAW catalogue")
    assert enriched.iloc[0]["flood_enrichment_timestamp"] == TIMESTAMP


def test_unknown_matching_risk_band_is_unresolved():
    polygon = box(-3.21, 51.49, -3.19, 51.51)
    enriched, unresolved, _ = enrich_chargers(
        chargers((51.5, -3.2)), layers(river=[{"risk_band": "Severe", "geometry": polygon}]), TIMESTAMP
    )
    assert len(unresolved) == 1
    assert enriched.iloc[0]["flood_river_band"] == "Severe"
    assert "unknown flood-risk classification" in enriched.iloc[0]["flood_enrichment_notes"]


def test_incomplete_flood_provenance_flags_record():
    test_layers = layers()
    test_layers["river"] = test_layers["river"].drop(columns="attribution")
    enriched, unresolved, _ = enrich_chargers(
        chargers((51.5, -3.2)), test_layers, TIMESTAMP
    )
    assert len(unresolved) == 1
    assert "missing provenance fields attribution" in enriched.iloc[0]["flood_enrichment_notes"]


def test_write_outputs_preserves_every_record(workspace_tmp_dir):
    enriched, unresolved, report = enrich_chargers(
        chargers((51.5, -3.2), (95, -3.2)), layers(), TIMESTAMP
    )
    enriched_path = workspace_tmp_dir / "enriched.csv"
    unresolved_path = workspace_tmp_dir / "unresolved.csv"
    report_path = workspace_tmp_dir / "report.json"
    write_outputs(enriched, unresolved, report, enriched_path, unresolved_path, report_path)
    assert len(pd.read_csv(enriched_path)) == 2
    assert len(pd.read_csv(unresolved_path)) == 1
    assert report_path.is_file()
