"""Filter canonical charging locations against the official Cardiff boundary."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

from charging_schema import CANONICAL_CHARGING_FIELDS, validate_charging_locations


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHARGERS = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "charging"
    / "open_charge_map_cardiff_normalised.csv"
)
DEFAULT_BOUNDARY = PROJECT_ROOT / "data" / "processed" / "cardiff_boundary.gpkg"
DEFAULT_INCLUDED = PROJECT_ROOT / "data" / "processed" / "cardiff_charging_sites.csv"
DEFAULT_OUTSIDE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cardiff_charging_sites_outside_boundary.csv"
)
DEFAULT_REPORT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cardiff_charging_boundary_report.json"
)
BOUNDARY_LAYER = "cardiff_boundary"
BOUNDARY_FILTER_VERSION = "1.0.0"
FALLBACK_PROJECTED_CRS = "EPSG:27700"
# One millimetre accommodates reversible CRS floating-point noise only; it is
# not an administrative-boundary buffer.
BOUNDARY_NUMERIC_TOLERANCE_METRES = 1e-3

BOUNDARY_FIELDS = (
    "boundary_status",
    "boundary_authority_code",
    "boundary_authority_name",
    "boundary_dataset",
    "boundary_filter_timestamp",
    "boundary_filter_version",
)


class BoundaryFilterError(ValueError):
    """Raised when lossless boundary filtering cannot be completed safely."""


def load_charging_locations(path: Path = DEFAULT_CHARGERS) -> pd.DataFrame:
    path = Path(path)
    if not path.is_file():
        raise BoundaryFilterError(f"Charging dataset not found: {path}")
    try:
        return pd.read_csv(
            path, dtype={"station_id": "string", "source_record_id": "string"}
        )
    except Exception as exc:
        raise BoundaryFilterError(f"Failed to read charging dataset: {exc}") from exc


def load_cardiff_boundary(
    path: Path = DEFAULT_BOUNDARY, layer: str = BOUNDARY_LAYER
) -> gpd.GeoDataFrame:
    path = Path(path)
    if not path.is_file():
        raise BoundaryFilterError(f"Cardiff boundary not found: {path}")
    try:
        boundary = gpd.read_file(path, layer=layer)
    except Exception as exc:
        raise BoundaryFilterError(f"Failed to read Cardiff boundary: {exc}") from exc
    return boundary


def _validate_schema_without_coordinate_rejection(
    chargers: pd.DataFrame, latitude: pd.Series, longitude: pd.Series
) -> None:
    missing_columns = sorted(set(CANONICAL_CHARGING_FIELDS) - set(chargers.columns))
    if missing_columns:
        raise BoundaryFilterError(
            f"Missing canonical charging fields: {missing_columns}"
        )

    # Validate each row independently so duplicate station IDs can be reported
    # rather than preventing a complete, lossless spatial review. Coordinates
    # are validated separately below; temporary zeros are used only for rows
    # whose original coordinates are invalid and never enter output data.
    for position, (index, row) in enumerate(chargers.iterrows()):
        candidate = row.to_frame().T.reindex(columns=CANONICAL_CHARGING_FIELDS)
        if pd.isna(latitude.loc[index]) or not -90 <= latitude.loc[index] <= 90:
            candidate.loc[index, "latitude"] = 0.0
        else:
            candidate.loc[index, "latitude"] = latitude.loc[index]
        if pd.isna(longitude.loc[index]) or not -180 <= longitude.loc[index] <= 180:
            candidate.loc[index, "longitude"] = 0.0
        else:
            candidate.loc[index, "longitude"] = longitude.loc[index]
        try:
            validate_charging_locations(candidate)
        except (TypeError, ValueError) as exc:
            raise BoundaryFilterError(
                f"Invalid canonical charging data at input row {position}: {exc}"
            ) from exc


def classify_charging_locations(
    chargers: pd.DataFrame,
    boundary: gpd.GeoDataFrame,
    *,
    filter_timestamp: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Classify every charger as inside, boundary, outside, or invalid coordinates."""
    if len(boundary) != 1:
        raise BoundaryFilterError(
            f"Expected exactly one Cardiff boundary feature; found {len(boundary)}"
        )
    if boundary.crs is None:
        raise BoundaryFilterError("Cardiff boundary has no CRS")
    if boundary.geometry.iloc[0] is None or boundary.geometry.iloc[0].is_empty:
        raise BoundaryFilterError("Cardiff boundary geometry is missing or empty")
    if not boundary.geometry.iloc[0].is_valid:
        raise BoundaryFilterError("Cardiff boundary geometry is invalid")

    missing_columns = sorted(set(CANONICAL_CHARGING_FIELDS) - set(chargers.columns))
    if missing_columns:
        raise BoundaryFilterError(
            f"Missing canonical charging fields: {missing_columns}"
        )
    latitude = pd.to_numeric(chargers.get("latitude"), errors="coerce")
    longitude = pd.to_numeric(chargers.get("longitude"), errors="coerce")
    _validate_schema_without_coordinate_rejection(chargers, latitude, longitude)

    valid_coordinates = (
        latitude.notna()
        & longitude.notna()
        & latitude.between(-90, 90)
        & longitude.between(-180, 180)
    )
    statuses = pd.Series("invalid_coordinates", index=chargers.index, dtype="string")

    target_crs = (
        boundary.crs
        if boundary.crs.is_projected
        else gpd.GeoSeries([], crs=FALLBACK_PROJECTED_CRS).crs
    )
    projected_boundary = boundary.to_crs(target_crs)
    boundary_geometry = projected_boundary.geometry.iloc[0]

    valid_index = chargers.index[valid_coordinates]
    if len(valid_index):
        points = gpd.GeoDataFrame(
            chargers.loc[valid_index].copy(),
            geometry=gpd.points_from_xy(
                longitude.loc[valid_index], latitude.loc[valid_index], crs="EPSG:4326"
            ),
            crs="EPSG:4326",
        ).to_crs(target_crs)

        for index, point in points.geometry.items():
            if boundary_geometry.boundary.covers(point) or (
                boundary_geometry.boundary.distance(point)
                <= BOUNDARY_NUMERIC_TOLERANCE_METRES
            ):
                statuses.loc[index] = "boundary"
            elif boundary_geometry.covers(point):
                statuses.loc[index] = "inside"
            else:
                statuses.loc[index] = "outside"

    timestamp = filter_timestamp or datetime.now(timezone.utc).isoformat()
    authority_code = boundary.iloc[0].get("authority_code")
    authority_name = boundary.iloc[0].get("name_en")
    boundary_dataset = boundary.iloc[0].get("source_dataset")

    enriched = chargers.copy()
    enriched["boundary_status"] = statuses
    enriched["boundary_authority_code"] = authority_code
    enriched["boundary_authority_name"] = authority_name
    enriched["boundary_dataset"] = boundary_dataset
    enriched["boundary_filter_timestamp"] = timestamp
    enriched["boundary_filter_version"] = BOUNDARY_FILTER_VERSION

    included_mask = statuses.isin(["inside", "boundary"])
    included = enriched.loc[included_mask].copy()
    outside = enriched.loc[~included_mask].copy()

    duplicate_ids = sorted(
        enriched.loc[
            enriched["station_id"].astype("string").duplicated(keep=False), "station_id"
        ]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )
    coordinate_frame = pd.DataFrame(
        {"latitude": latitude[valid_coordinates], "longitude": longitude[valid_coordinates]}
    )
    duplicated_coordinates = coordinate_frame.duplicated(keep=False)
    duplicate_groups = (
        coordinate_frame.loc[duplicated_coordinates]
        .drop_duplicates()
        .sort_values(["latitude", "longitude"])
    )

    report = {
        "boundary_filter_timestamp": timestamp,
        "boundary_filter_version": BOUNDARY_FILTER_VERSION,
        "boundary_authority_code": authority_code,
        "boundary_authority_name": authority_name,
        "boundary_dataset": boundary_dataset,
        "evaluation_crs": target_crs.to_string(),
        "total_input_records": int(len(chargers)),
        "valid_coordinates": int(valid_coordinates.sum()),
        "invalid_coordinates": int((~valid_coordinates).sum()),
        "inside_count": int(statuses.eq("inside").sum()),
        "boundary_count": int(statuses.eq("boundary").sum()),
        "outside_count": int(statuses.eq("outside").sum()),
        "invalid_coordinate_count": int(statuses.eq("invalid_coordinates").sum()),
        "duplicate_station_ids": {
            "count": len(duplicate_ids),
            "values": duplicate_ids,
        },
        "duplicate_coordinates": {
            "group_count": int(len(duplicate_groups)),
            "record_count": int(duplicated_coordinates.sum()),
            "values": duplicate_groups.to_dict(orient="records"),
        },
        "record_accounting": {
            "included_records": int(len(included)),
            "outside_review_records": int(len(outside)),
            "accounted_records": int(len(included) + len(outside)),
        },
        "output_file_sizes": {},
    }
    return included, outside, report


def _atomic_write_text(path: Path, content: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content.encode("utf-8"))
    os.replace(temporary, path)


def write_filter_outputs(
    included: pd.DataFrame,
    outside: pd.DataFrame,
    report: dict[str, Any],
    *,
    included_path: Path = DEFAULT_INCLUDED,
    outside_path: Path = DEFAULT_OUTSIDE,
    report_path: Path = DEFAULT_REPORT,
) -> dict[str, Any]:
    """Atomically write both lossless partitions and a self-sized report."""
    included_path = Path(included_path)
    outside_path = Path(outside_path)
    report_path = Path(report_path)
    _atomic_write_text(included_path, included.to_csv(index=False, lineterminator="\n"))
    _atomic_write_text(outside_path, outside.to_csv(index=False, lineterminator="\n"))

    final_report = json.loads(json.dumps(report))
    sizes = {
        "cardiff_charging_sites_csv_bytes": included_path.stat().st_size,
        "outside_boundary_csv_bytes": outside_path.stat().st_size,
        "quality_report_json_bytes": 0,
    }
    final_report["output_file_sizes"] = sizes
    while True:
        content = json.dumps(final_report, indent=2, ensure_ascii=False) + "\n"
        new_size = len(content.encode("utf-8"))
        if sizes["quality_report_json_bytes"] == new_size:
            break
        sizes["quality_report_json_bytes"] = new_size
    _atomic_write_text(report_path, content)
    return final_report


def main() -> int:
    chargers = load_charging_locations()
    boundary = load_cardiff_boundary()
    included, outside, report = classify_charging_locations(chargers, boundary)
    final_report = write_filter_outputs(included, outside, report)
    print(f"Input records: {final_report['total_input_records']}")
    print(f"Included Cardiff records: {final_report['record_accounting']['included_records']}")
    print(f"Boundary records: {final_report['boundary_count']}")
    print(f"Outside/review records: {final_report['record_accounting']['outside_review_records']}")
    print(f"Invalid-coordinate records: {final_report['invalid_coordinate_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
