"""Prepare Cardiff LSOA income-deprivation data from verified public sources."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import MultiPolygon, Polygon


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WIMD_CSV = PROJECT_ROOT / "data/raw/deprivation/wimd_2025_income_employment_indicators.csv"
DEFAULT_LSOA_BOUNDARY = PROJECT_ROOT / "data/raw/boundaries/wales_lsoa_2021.gpkg"
DEFAULT_CARDIFF_BOUNDARY = PROJECT_ROOT / "data/processed/cardiff_boundary.gpkg"
DEFAULT_OUTPUT = PROJECT_ROOT / "data/processed/cardiff_lsoa_income_deprivation.gpkg"
LSOA_LAYER = "lsoa_2021_w_hwm"
CARDIFF_LAYER = "cardiff_boundary"
OUTPUT_LAYER = "cardiff_lsoa_income_deprivation"
PROCESSING_CRS = "EPSG:27700"
EXPECTED_WALES_LSOAS = 1917
MINIMUM_CARDIFF_OVERLAP_M2 = 1.0
MINIMUM_CARDIFF_OVERLAP_RATIO = 0.5

INDICATOR = "People in income deprivation"
DATA_DESCRIPTION = "Percentage"
LSOA_CODE_PATTERN = re.compile(r"^W01\d{6}$")
RELEASE_NAME = "WIMD 2025"
WIMD_PUBLICATION_DATE = "2025-11-27"
WIMD_DATASET = "WIMD 2025 income and employment indicators"
BOUNDARY_DATASET = "Lower Layer Super Output Areas (December 2021) Boundaries EW BGC"
LICENCE = "Open Government Licence v3.0"
ATTRIBUTION = (
    "Source: Welsh Government, Welsh Index of Multiple Deprivation 2025 indicator data, "
    "licensed under the Open Government Licence v3.0. © Crown copyright 2025. "
    "Source: Office for National Statistics licensed under the Open Government Licence "
    "v3.0. Contains OS data © Crown copyright and database right 2025."
)


class DeprivationPreparationError(ValueError):
    """Raised when deprivation data cannot be prepared safely."""


def filter_wimd_percentage(source: pd.DataFrame) -> pd.DataFrame:
    required = {"Indicator", "Data description", "Area code", "Area name", "Data values"}
    missing = sorted(required - set(source.columns))
    if missing:
        raise DeprivationPreparationError(f"WIMD source is missing columns: {missing}")

    mask = (
        source["Indicator"].eq(INDICATOR)
        & source["Data description"].eq(DATA_DESCRIPTION)
        & source["Area code"].astype("string").str.fullmatch(LSOA_CODE_PATTERN.pattern, na=False)
    )
    selected = source.loc[mask, ["Area code", "Area name", "Data values"]].copy()
    selected.columns = ["lsoa_code", "lsoa_name", "income_deprivation_percentage"]

    if selected.empty:
        raise DeprivationPreparationError("The exact WIMD filter selected no LSOA records")
    if selected["lsoa_code"].isna().any() or selected["lsoa_code"].astype(str).str.strip().eq("").any():
        raise DeprivationPreparationError("Filtered WIMD records contain a missing LSOA code")
    if selected["lsoa_name"].isna().any() or selected["lsoa_name"].astype(str).str.strip().eq("").any():
        raise DeprivationPreparationError("Filtered WIMD records contain a missing LSOA name")
    duplicate_codes = selected.loc[selected["lsoa_code"].duplicated(False), "lsoa_code"].unique()
    if len(duplicate_codes):
        raise DeprivationPreparationError(f"Duplicate WIMD LSOA codes: {sorted(duplicate_codes)}")

    numeric = pd.to_numeric(selected["income_deprivation_percentage"], errors="coerce")
    if numeric.isna().any():
        bad_codes = selected.loc[numeric.isna(), "lsoa_code"].tolist()
        raise DeprivationPreparationError(f"Missing or non-numeric WIMD percentages: {bad_codes}")
    if not numeric.between(0, 100, inclusive="both").all():
        raise DeprivationPreparationError("WIMD percentages must be between 0 and 100")
    selected["income_deprivation_percentage"] = numeric.astype(float)
    selected["deprivation_score"] = selected["income_deprivation_percentage"]
    return selected.reset_index(drop=True)


def _consistent_value(group: pd.DataFrame, column: str, code: str):
    values = group[column].dropna().astype(str).str.strip()
    unique = values[values.ne("")].unique()
    if len(unique) > 1:
        raise DeprivationPreparationError(
            f"Conflicting {column} values for LSOA {code}: {sorted(unique)}"
        )
    return unique[0] if len(unique) else None


def dissolve_lsoa_parts(source: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    required = {"lsoa21cd", "lsoa21nm", "lsoa21nmw", "geometry"}
    missing = sorted(required - set(source.columns))
    if missing:
        raise DeprivationPreparationError(f"LSOA boundary is missing columns: {missing}")
    if source.crs is None:
        raise DeprivationPreparationError("LSOA boundary has no CRS")
    working = source.to_crs(PROCESSING_CRS)
    if working["lsoa21cd"].isna().any() or working["lsoa21cd"].astype(str).str.strip().eq("").any():
        raise DeprivationPreparationError("LSOA boundary contains a missing code")
    if working.geometry.isna().any() or working.geometry.is_empty.any():
        raise DeprivationPreparationError("LSOA boundary contains missing or empty geometry")
    if not working.geometry.geom_type.isin(["Polygon", "MultiPolygon"]).all():
        raise DeprivationPreparationError("LSOA boundary contains non-polygonal geometry")
    if not working.geometry.is_valid.all():
        raise DeprivationPreparationError("LSOA boundary contains invalid geometry")

    rows = []
    for code, group in working.groupby("lsoa21cd", sort=True):
        names = {
            column: _consistent_value(group, column, code)
            for column in [
                "lsoa21nm",
                "lsoa21nmw",
                "lsoaalternativeenglish",
                "lsoaalternativewelsh",
            ]
            if column in group.columns
        }
        geometry = group.geometry.union_all()
        if geometry.is_empty or not geometry.is_valid or not isinstance(geometry, (Polygon, MultiPolygon)):
            raise DeprivationPreparationError(f"Invalid dissolved geometry for LSOA {code}")
        rows.append(
            {
                "lsoa_code": code,
                "lsoa_boundary_name_en": names["lsoa21nm"],
                "lsoa_boundary_name_cy": names["lsoa21nmw"],
                "lsoa_alternative_name_en": names.get("lsoaalternativeenglish"),
                "lsoa_alternative_name_cy": names.get("lsoaalternativewelsh"),
                "geometry": geometry,
            }
        )
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=PROCESSING_CRS)


def join_wimd_to_boundaries(
    boundaries: gpd.GeoDataFrame, wimd: pd.DataFrame
) -> gpd.GeoDataFrame:
    boundary_codes = set(boundaries["lsoa_code"])
    wimd_codes = set(wimd["lsoa_code"])
    if boundary_codes != wimd_codes:
        raise DeprivationPreparationError(
            "WIMD/boundary code mismatch: "
            f"WIMD-only={sorted(wimd_codes - boundary_codes)}, "
            f"boundary-only={sorted(boundary_codes - wimd_codes)}"
        )
    joined = boundaries.merge(wimd, on="lsoa_code", how="left", validate="one_to_one")
    return gpd.GeoDataFrame(joined, geometry="geometry", crs=boundaries.crs)


def select_cardiff_lsoas(
    lsoas: gpd.GeoDataFrame,
    cardiff: gpd.GeoDataFrame,
    minimum_overlap_m2: float = MINIMUM_CARDIFF_OVERLAP_M2,
    minimum_overlap_ratio: float = MINIMUM_CARDIFF_OVERLAP_RATIO,
) -> gpd.GeoDataFrame:
    if lsoas.crs is None or cardiff.crs is None:
        raise DeprivationPreparationError("Spatial selection inputs require a CRS")
    projected = lsoas.to_crs(PROCESSING_CRS)
    cardiff_projected = cardiff.to_crs(PROCESSING_CRS)
    if len(cardiff_projected) != 1:
        raise DeprivationPreparationError(
            f"Expected one Cardiff boundary feature; found {len(cardiff_projected)}"
        )
    authority = cardiff_projected.iloc[0]
    authority_code = authority.get("authority_code")
    if authority_code not in (None, "W06000015"):
        raise DeprivationPreparationError(f"Unexpected Cardiff authority code: {authority_code}")
    boundary = cardiff_projected.geometry.iloc[0]
    overlap = projected.geometry.intersection(boundary).area
    overlap_ratio = overlap / projected.geometry.area
    selected = projected.loc[
        overlap.gt(minimum_overlap_m2) & overlap_ratio.gt(minimum_overlap_ratio)
    ].copy()
    selected["cardiff_overlap_area_m2"] = overlap.loc[selected.index].astype(float)
    selected["cardiff_overlap_ratio"] = overlap_ratio.loc[selected.index].astype(float)
    selected["cardiff_selection_rule"] = (
        f"polygon overlap > {minimum_overlap_m2:g} m² and "
        f"> {minimum_overlap_ratio:.0%} of LSOA area"
    )
    return selected.reset_index(drop=True)


def add_provenance(data: gpd.GeoDataFrame, timestamp: str | None = None) -> gpd.GeoDataFrame:
    result = data.copy()
    result["source_dataset"] = WIMD_DATASET
    result["boundary_source_dataset"] = BOUNDARY_DATASET
    result["release_name"] = RELEASE_NAME
    result["source_publication_date"] = WIMD_PUBLICATION_DATE
    result["processing_timestamp"] = timestamp or datetime.now(timezone.utc).isoformat()
    result["licence"] = LICENCE
    result["attribution"] = ATTRIBUTION
    return result


def write_output(data: gpd.GeoDataFrame, output: Path = DEFAULT_OUTPUT) -> None:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.stem}.tmp.gpkg")
    if temporary.exists():
        temporary.unlink()
    try:
        data.to_file(temporary, layer=OUTPUT_LAYER, driver="GPKG")
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    wimd = filter_wimd_percentage(pd.read_csv(DEFAULT_WIMD_CSV, encoding="utf-8"))
    source_lsoas = gpd.read_file(DEFAULT_LSOA_BOUNDARY, layer=LSOA_LAYER)
    dissolved = dissolve_lsoa_parts(source_lsoas)
    if len(dissolved) != EXPECTED_WALES_LSOAS:
        raise DeprivationPreparationError(
            f"Expected {EXPECTED_WALES_LSOAS} dissolved LSOAs; found {len(dissolved)}"
        )
    joined = join_wimd_to_boundaries(dissolved, wimd)
    cardiff = gpd.read_file(DEFAULT_CARDIFF_BOUNDARY, layer=CARDIFF_LAYER)
    selected = add_provenance(select_cardiff_lsoas(joined, cardiff))
    if selected.empty or not selected.geometry.is_valid.all() or selected.geometry.is_empty.any():
        raise DeprivationPreparationError("Prepared Cardiff LSOA output failed validation")
    write_output(selected)
    print(f"Filtered WIMD records: {len(wimd)}")
    print(f"Dissolved Wales LSOAs: {len(dissolved)}")
    print(f"Cardiff LSOAs: {len(selected)}")
    print(f"Output: {DEFAULT_OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
