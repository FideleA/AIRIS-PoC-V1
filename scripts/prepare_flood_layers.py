"""Prepare bounded Cardiff subsets of the official FRAW flood layers."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import geopandas as gpd
import pandas as pd
import pyogrio
from shapely import make_valid
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = PROJECT_ROOT / "data" / "raw" / "flood"
PROCESSED_ROOT = PROJECT_ROOT / "data" / "processed"
CARDIFF_BOUNDARY = PROCESSED_ROOT / "cardiff_boundary.gpkg"
CARDIFF_BOUNDARY_LAYER = "cardiff_boundary"
PROCESSING_CRS = "EPSG:27700"
CATALOGUE_PUBLICATION_DATE = "2026-05-21"
SPATIAL_READ_MARGIN_METRES = 100.0
LICENCE = "Open Government Licence for Public Sector Information"
ATTRIBUTION = (
    "Contains Natural Resources Wales information © Natural Resources Wales "
    "and database right. All rights reserved. Some features of this information "
    "are based on digital spatial data licensed from the UK Centre for Ecology "
    "& Hydrology © UKCEH. Defra, Met Office and DARD Rivers Agency © Crown "
    "copyright. © Cranfield University. © James Hutton Institute. Contains OS "
    "data © Crown copyright and database right."
)

SOURCE_RISK_BANDS = ("Low", "Medium", "High")
NORMALISED_RISK_BANDS = ("Very Low", "Low", "Medium", "High")
ILLUSTRATIVE_AIRIS_RISK_SCORES = {
    "Very Low": 10,
    "Low": 35,
    "Medium": 65,
    "High": 90,
}


@dataclass(frozen=True)
class FloodLayerConfig:
    source_id: str
    flood_source: str
    source_path: Path
    source_layer: str
    output_path: Path
    output_layer: str
    risk_field: str
    publication_field: str
    objectid_field: str | None
    expected_layer_publication_date: str
    version_note: str


LAYER_CONFIGS = (
    FloodLayerConfig(
        source_id="FRAW_RIVERS",
        flood_source="rivers",
        source_path=RAW_ROOT / "fraw_rivers.gpkg",
        source_layer="NRW_FLOOD_RISK_FROM_RIVERS",
        output_path=PROCESSED_ROOT / "flood_rivers.gpkg",
        output_layer="flood_rivers",
        risk_field="risk",
        publication_field="pub_date",
        objectid_field="objectid",
        expected_layer_publication_date="2026-05-21",
        version_note=(
            "FRAW catalogue release 2026-05-21; source layer pub_date is "
            "preserved independently."
        ),
    ),
    FloodLayerConfig(
        source_id="FRAW_SEA",
        flood_source="sea",
        source_path=RAW_ROOT / "fraw_sea.gpkg",
        source_layer="NRW_FLOOD_RISK_FROM_SEA",
        output_path=PROCESSED_ROOT / "flood_sea.gpkg",
        output_layer="flood_sea",
        risk_field="risk",
        publication_field="pub_date",
        objectid_field=None,
        expected_layer_publication_date="2026-05-21",
        version_note=(
            "FRAW catalogue release 2026-05-21; the downloaded sea schema has "
            "no objectid field, so no source objectid is invented."
        ),
    ),
    FloodLayerConfig(
        source_id="FRAW_SURFACE_WATER",
        flood_source="surface_water_and_small_watercourses",
        source_path=RAW_ROOT / "fraw_surface_water.gpkg",
        source_layer="NRW_FLOOD_RISK_FROM_SURFACE_WATER_SMALL_WATERCOURSES",
        output_path=PROCESSED_ROOT / "flood_surface_water.gpkg",
        output_layer="flood_surface_water",
        risk_field="Risk",
        publication_field="pub_date",
        objectid_field="OBJECTID",
        expected_layer_publication_date="2022-11-28",
        version_note=(
            "FRAW catalogue release 2026-05-21; the downloaded surface-water "
            "layer retains the older internal pub_date 2022-11-28. The dates "
            "describe different metadata levels and are not overwritten."
        ),
    ),
)


class FloodPreparationError(ValueError):
    """Raised when a flood layer cannot be prepared without ambiguity."""


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def normalise_risk_band(value: object) -> str:
    """Return an exact canonical source band; Very Low is never a source band."""
    if value is None or pd.isna(value) or not str(value).strip():
        raise FloodPreparationError("Missing source flood-risk classification")
    band = str(value).strip()
    if band not in SOURCE_RISK_BANDS:
        raise FloodPreparationError(
            f"Unknown source flood-risk classification: {band!r}"
        )
    return band


def _polygonal_parts(geometry) -> Iterable[Polygon]:
    if isinstance(geometry, Polygon):
        yield geometry
    elif isinstance(geometry, MultiPolygon):
        yield from geometry.geoms
    elif hasattr(geometry, "geoms"):
        for part in geometry.geoms:
            yield from _polygonal_parts(part)


def repair_polygonal_geometry(geometry):
    """Repair one geometry and return polygonal content, or None on failure."""
    if geometry is None or geometry.is_empty:
        return None
    if geometry.is_valid and isinstance(geometry, (Polygon, MultiPolygon)):
        return geometry
    repaired = make_valid(geometry)
    polygons = list(_polygonal_parts(repaired))
    if not polygons:
        return None
    polygonal = unary_union(polygons)
    if polygonal.is_empty or not polygonal.is_valid:
        return None
    if not isinstance(polygonal, (Polygon, MultiPolygon)):
        return None
    return polygonal


def load_cardiff_boundary(path: Path = CARDIFF_BOUNDARY) -> gpd.GeoDataFrame:
    path = Path(path)
    if not path.is_file():
        raise FloodPreparationError(f"Cardiff boundary not found: {path}")
    boundary = gpd.read_file(path, layer=CARDIFF_BOUNDARY_LAYER)
    if len(boundary) != 1 or boundary.crs is None:
        raise FloodPreparationError(
            "Cardiff boundary must contain exactly one feature with a CRS"
        )
    if boundary.crs.to_string().upper() != PROCESSING_CRS:
        boundary = boundary.to_crs(PROCESSING_CRS)
    if boundary.geometry.iloc[0] is None or boundary.geometry.iloc[0].is_empty:
        raise FloodPreparationError("Cardiff boundary geometry is empty")
    return boundary


def processing_bbox(
    boundary: gpd.GeoDataFrame,
    margin_metres: float = SPATIAL_READ_MARGIN_METRES,
) -> tuple[float, float, float, float]:
    if margin_metres < 0:
        raise FloodPreparationError("Spatial-read margin cannot be negative")
    if boundary.crs is None:
        raise FloodPreparationError("Cardiff boundary has no CRS")
    projected = (
        boundary
        if boundary.crs.to_string().upper() == PROCESSING_CRS
        else boundary.to_crs(PROCESSING_CRS)
    )
    minx, miny, maxx, maxy = projected.total_bounds
    return (
        float(minx - margin_metres),
        float(miny - margin_metres),
        float(maxx + margin_metres),
        float(maxy + margin_metres),
    )


def read_bounded_source(
    config: FloodLayerConfig,
    boundary: gpd.GeoDataFrame,
    reader: Callable = pyogrio.read_dataframe,
) -> tuple[gpd.GeoDataFrame, int, tuple[float, float, float, float]]:
    """Read only the source features in an indexed Cardiff bounding box."""
    if not config.source_path.is_file():
        raise FloodPreparationError(f"Flood source not found: {config.source_path}")
    try:
        info = pyogrio.read_info(
            config.source_path,
            layer=config.source_layer,
            force_feature_count=True,
        )
    except Exception as exc:
        raise FloodPreparationError(f"Failed to inspect {config.source_layer}: {exc}") from exc
    source_crs = info.get("crs")
    if not source_crs:
        raise FloodPreparationError(f"{config.source_layer} has no CRS")
    source_boundary = boundary.to_crs(source_crs)
    bbox = processing_bbox(source_boundary)
    try:
        subset = reader(config.source_path, layer=config.source_layer, bbox=bbox)
    except Exception as exc:
        raise FloodPreparationError(
            f"Bounded read failed for {config.source_layer}: {exc}"
        ) from exc
    if subset.crs is None:
        raise FloodPreparationError(f"{config.source_layer} subset has no CRS")
    return subset, int(info["features"]), bbox


def _internal_feature_id(row: pd.Series, config: FloodLayerConfig) -> str:
    if config.objectid_field and config.objectid_field in row.index:
        source_id = row[config.objectid_field]
        if not pd.isna(source_id) and str(source_id).strip():
            return f"{config.source_id}:{source_id}"
    mm_id = row.get("mm_id")
    geometry = row.geometry
    seed = f"{config.source_id}|{'' if pd.isna(mm_id) else mm_id}|".encode()
    if geometry is not None:
        seed += geometry.wkb
    return f"{config.source_id}:sha256:{hashlib.sha256(seed).hexdigest()}"


def prepare_flood_subset(
    source: gpd.GeoDataFrame,
    boundary: gpd.GeoDataFrame,
    config: FloodLayerConfig,
    source_checksum: str,
) -> tuple[gpd.GeoDataFrame, dict[str, int]]:
    """Normalise and repair only source features relevant to Cardiff."""
    required = {config.risk_field, config.publication_field}
    missing = sorted(required - set(source.columns))
    if missing:
        raise FloodPreparationError(
            f"{config.source_layer} is missing required fields: {', '.join(missing)}"
        )
    if source.crs is None:
        raise FloodPreparationError(f"{config.source_layer} has no CRS")

    projected = source.to_crs(PROCESSING_CRS)
    projected_boundary = boundary.to_crs(PROCESSING_CRS)
    boundary_geometry = projected_boundary.geometry.iloc[0]
    selected = projected.loc[projected.geometry.intersects(boundary_geometry)].copy()
    selected["risk_band"] = selected[config.risk_field].map(normalise_risk_band)

    layer_dates = pd.to_datetime(
        selected[config.publication_field], errors="coerce"
    ).dt.strftime("%Y-%m-%d")
    if layer_dates.isna().any():
        raise FloodPreparationError(
            f"{config.source_layer} contains missing or invalid publication dates"
        )
    unexpected_dates = sorted(
        set(layer_dates.unique()) - {config.expected_layer_publication_date}
    )
    if unexpected_dates:
        raise FloodPreparationError(
            f"{config.source_layer} has unexpected layer publication dates: "
            f"{unexpected_dates}"
        )

    invalid_before = 0
    repaired_count = 0
    unrepaired_count = 0
    output_geometries = []
    statuses = []
    for geometry in selected.geometry:
        originally_valid_polygon = (
            geometry is not None
            and not geometry.is_empty
            and geometry.is_valid
            and isinstance(geometry, (Polygon, MultiPolygon))
        )
        if originally_valid_polygon:
            output_geometries.append(geometry)
            statuses.append("valid")
            continue
        invalid_before += 1
        repaired = repair_polygonal_geometry(geometry)
        if repaired is None:
            output_geometries.append(None)
            statuses.append("unrepaired")
            unrepaired_count += 1
        else:
            output_geometries.append(repaired)
            statuses.append("repaired")
            repaired_count += 1

    selected["geometry"] = gpd.GeoSeries(output_geometries, index=selected.index, crs=PROCESSING_CRS)
    selected["geometry_status"] = statuses
    selected["source_feature_id"] = [
        _internal_feature_id(row, config) for _, row in selected.iterrows()
    ]
    selected["flood_source"] = config.flood_source
    selected["illustrative_airis_score"] = selected["risk_band"].map(
        ILLUSTRATIVE_AIRIS_RISK_SCORES
    )
    selected["catalogue_publication_date"] = CATALOGUE_PUBLICATION_DATE
    selected["layer_publication_date"] = layer_dates
    selected["source_file_checksum"] = source_checksum
    selected["source_dataset_version_note"] = config.version_note
    selected["source_layer"] = config.source_layer
    selected["licence"] = LICENCE
    selected["attribution"] = ATTRIBUTION

    if selected.loc[selected["geometry_status"] != "unrepaired", "geometry"].is_valid.eq(False).any():
        raise FloodPreparationError("A repaired Cardiff geometry remains invalid")
    metrics = {
        "cardiff_subset_features": len(selected),
        "invalid_geometries": invalid_before,
        "repaired_geometries": repaired_count,
        "unrepaired_geometries": unrepaired_count,
    }
    return selected, metrics


def write_flood_geopackage(
    prepared: gpd.GeoDataFrame, output_path: Path, layer: str
) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.stem}.tmp.gpkg")
    if temporary.exists():
        temporary.unlink()
    try:
        prepared.to_file(temporary, layer=layer, driver="GPKG")
        os.replace(temporary, output_path)
    finally:
        if temporary.exists():
            temporary.unlink()


def prepare_layer(
    config: FloodLayerConfig,
    boundary: gpd.GeoDataFrame,
) -> dict[str, object]:
    source, national_count, bbox = read_bounded_source(config, boundary)
    checksum = sha256_file(config.source_path)
    prepared, metrics = prepare_flood_subset(source, boundary, config, checksum)
    write_flood_geopackage(prepared, config.output_path, config.output_layer)
    return {
        "source_id": config.source_id,
        "national_source_features": national_count,
        "bounded_read_features": len(source),
        "spatial_filter_bbox": bbox,
        "source_crs": source.crs.to_string(),
        "processed_crs": prepared.crs.to_string(),
        "catalogue_publication_date": CATALOGUE_PUBLICATION_DATE,
        "layer_publication_date": config.expected_layer_publication_date,
        "source_file_checksum": checksum,
        "output_path": str(config.output_path),
        **metrics,
    }


def main() -> int:
    boundary = load_cardiff_boundary()
    print(
        "Read method: GeoPackage spatial index via pyogrio bbox in EPSG:27700; "
        f"{SPATIAL_READ_MARGIN_METRES:g} m bounding-box safety margin; exact "
        "Cardiff-boundary intersection after read."
    )
    for config in LAYER_CONFIGS:
        result = prepare_layer(config, boundary)
        print(result)
    print(
        "Illustrative AIRIS mapping (not official NRW scores): "
        f"{ILLUSTRATIVE_AIRIS_RISK_SCORES}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
