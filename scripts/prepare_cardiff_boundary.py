"""Prepare the official Cardiff local-authority boundary for AIRIS."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

import geopandas as gpd
from shapely import make_valid
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = (
    PROJECT_ROOT / "data" / "raw" / "boundaries" / "wales_local_authorities.gpkg"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "cardiff_boundary.gpkg"
SOURCE_LAYER = "local_authorities_wales_hwm"
PROJECTED_LAYER = "cardiff_boundary"
WEB_LAYER = "cardiff_boundary_wgs84"

CARDIFF_AUTHORITY_CODE = "W06000015"
CARDIFF_NAME_EN = "Cardiff"
CARDIFF_NAME_CY = "Caerdydd"
AUTHORITY_CODE_FIELD = "census_cod"
AUTHORITY_NAME_EN_FIELD = "name_en"
AUTHORITY_NAME_CY_FIELD = "name_cy"

PROJECTED_CRS = "EPSG:27700"
WEB_CRS = "EPSG:4326"
SOURCE_DATASET_NAME = "Local Authorities - High Water mark"
SOURCE_PUBLICATION_DATE = "2025-11-26"
SOURCE_LICENCE = "Open Government Licence for Public Sector Information"
SOURCE_ATTRIBUTION = (
    "Welsh Government / DataMapWales; derived from Ordnance Survey OpenData "
    "Boundary-Line"
)
COASTLINE_CONVENTION = "High water mark"


class BoundaryPreparationError(ValueError):
    """Raised when the Cardiff boundary cannot be prepared safely."""


def load_boundary_source(
    source_path: Path = DEFAULT_SOURCE, layer: str = SOURCE_LAYER
) -> gpd.GeoDataFrame:
    source_path = Path(source_path)
    if not source_path.is_file():
        raise BoundaryPreparationError(f"Boundary source not found: {source_path}")
    try:
        boundaries = gpd.read_file(source_path, layer=layer)
    except Exception as exc:
        raise BoundaryPreparationError(f"Failed to read boundary source: {exc}") from exc
    if boundaries.crs is None:
        raise BoundaryPreparationError("Boundary source has no coordinate reference system")
    return boundaries


def select_cardiff_boundary(boundaries: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Select exactly Cardiff, preferring the official authority code."""
    if AUTHORITY_CODE_FIELD in boundaries.columns:
        selected = boundaries.loc[
            boundaries[AUTHORITY_CODE_FIELD].astype("string").eq(CARDIFF_AUTHORITY_CODE)
        ]
        selection_rule = f"{AUTHORITY_CODE_FIELD}={CARDIFF_AUTHORITY_CODE}"
    elif AUTHORITY_NAME_EN_FIELD in boundaries.columns:
        selected = boundaries.loc[
            boundaries[AUTHORITY_NAME_EN_FIELD].astype("string").eq(CARDIFF_NAME_EN)
        ]
        selection_rule = f"{AUTHORITY_NAME_EN_FIELD}={CARDIFF_NAME_EN}"
    else:
        raise BoundaryPreparationError(
            "Boundary source has neither an authority code nor English-name field"
        )

    if len(selected) != 1:
        raise BoundaryPreparationError(
            f"Expected exactly one Cardiff feature using {selection_rule}; found {len(selected)}"
        )

    selected = selected.copy()
    if AUTHORITY_NAME_EN_FIELD in selected.columns:
        actual_name = selected.iloc[0][AUTHORITY_NAME_EN_FIELD]
        if actual_name != CARDIFF_NAME_EN:
            raise BoundaryPreparationError(
                f"Cardiff code resolved to unexpected English name: {actual_name!r}"
            )
    return selected


def _polygonal_parts(geometry) -> Iterable[Polygon]:
    if isinstance(geometry, Polygon):
        yield geometry
    elif isinstance(geometry, MultiPolygon):
        yield from geometry.geoms
    elif hasattr(geometry, "geoms"):
        for part in geometry.geoms:
            yield from _polygonal_parts(part)


def _repair_polygonal_geometry(geometry):
    repaired = make_valid(geometry)
    polygons = list(_polygonal_parts(repaired))
    if not polygons:
        raise BoundaryPreparationError(
            "Geometry repair did not produce polygonal boundary geometry"
        )
    polygonal = unary_union(polygons)
    if isinstance(polygonal, Polygon):
        polygonal = MultiPolygon([polygonal])
    if not isinstance(polygonal, MultiPolygon) or not polygonal.is_valid:
        raise BoundaryPreparationError("Geometry remains invalid after make_valid repair")
    return polygonal


def prepare_cardiff_boundary(
    boundaries: gpd.GeoDataFrame, projected_crs: str = PROJECTED_CRS
) -> gpd.GeoDataFrame:
    """Select, validate, conditionally repair, and annotate Cardiff geometry."""
    selected = select_cardiff_boundary(boundaries)
    geometry = selected.geometry.iloc[0]
    if geometry is None or geometry.is_empty:
        raise BoundaryPreparationError("Cardiff geometry is missing or empty")

    geometry_repaired = False
    if not geometry.is_valid:
        geometry = _repair_polygonal_geometry(geometry)
        geometry_repaired = True

    authority_code = (
        selected.iloc[0][AUTHORITY_CODE_FIELD]
        if AUTHORITY_CODE_FIELD in selected.columns
        else None
    )
    name_en = selected.iloc[0][AUTHORITY_NAME_EN_FIELD]
    name_cy = (
        selected.iloc[0][AUTHORITY_NAME_CY_FIELD]
        if AUTHORITY_NAME_CY_FIELD in selected.columns
        else None
    )

    prepared = gpd.GeoDataFrame(
        [
            {
                "authority_code": authority_code,
                "name_en": name_en,
                "name_cy": name_cy,
                "source_dataset": SOURCE_DATASET_NAME,
                "source_publication_date": SOURCE_PUBLICATION_DATE,
                "licence": SOURCE_LICENCE,
                "attribution": SOURCE_ATTRIBUTION,
                "coastline_convention": COASTLINE_CONVENTION,
                "geometry_repaired": geometry_repaired,
                "geometry": geometry,
            }
        ],
        geometry="geometry",
        crs=selected.crs,
    )

    if prepared.crs is None:
        raise BoundaryPreparationError("Prepared boundary has no CRS")
    if prepared.crs.to_string().upper() != projected_crs.upper():
        prepared = prepared.to_crs(projected_crs)
    if not prepared.geometry.is_valid.all():
        raise BoundaryPreparationError("Prepared Cardiff geometry is invalid")
    return prepared


def to_web_crs(boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Return a copy converted to WGS84 for web-map display."""
    if boundary.crs is None:
        raise BoundaryPreparationError("Cannot convert boundary without a CRS")
    converted = boundary.to_crs(WEB_CRS)
    if not converted.geometry.is_valid.all():
        raise BoundaryPreparationError("Web-map Cardiff geometry is invalid")
    return converted


def write_boundary_geopackage(
    projected: gpd.GeoDataFrame,
    output_path: Path = DEFAULT_OUTPUT,
) -> None:
    """Atomically write projected and WGS84 layers to one GeoPackage."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.stem}.tmp.gpkg")
    if temporary.exists():
        temporary.unlink()
    try:
        projected.to_file(temporary, layer=PROJECTED_LAYER, driver="GPKG")
        to_web_crs(projected).to_file(
            temporary, layer=WEB_LAYER, driver="GPKG", mode="a"
        )
        os.replace(temporary, output_path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    boundaries = load_boundary_source()
    prepared = prepare_cardiff_boundary(boundaries)
    write_boundary_geopackage(prepared)
    row = prepared.iloc[0]
    print(
        f"Prepared {row['name_en']} ({row['authority_code']}) in "
        f"{prepared.crs.to_string()}"
    )
    print(f"Output: {DEFAULT_OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
