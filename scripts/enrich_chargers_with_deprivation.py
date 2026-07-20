"""Spatially enrich flood-enriched Cardiff chargers with WIMD percentages."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHARGERS = PROJECT_ROOT / "data/processed/cardiff_charging_sites_flood_enriched.csv"
DEFAULT_LSOAS = PROJECT_ROOT / "data/processed/cardiff_lsoa_income_deprivation.gpkg"
LSOA_LAYER = "cardiff_lsoa_income_deprivation"
DEFAULT_ENRICHED = PROJECT_ROOT / "data/processed/cardiff_charging_sites_flood_deprivation_enriched.csv"
DEFAULT_UNRESOLVED = PROJECT_ROOT / "data/processed/cardiff_charging_sites_deprivation_unresolved.csv"
DEFAULT_REPORT = PROJECT_ROOT / "data/processed/cardiff_deprivation_enrichment_report.json"
PROCESSING_CRS = "EPSG:27700"
MATCH_TOLERANCE_METRES = 0.1

REQUIRED_CHARGER_FIELDS = {
    "station_id", "latitude", "longitude", "data_provider", "source_url",
    "licence", "attribution",
}
REQUIRED_FLOOD_FIELDS = {
    "flood_river_band", "flood_river_score", "flood_river_match_count",
    "flood_sea_band", "flood_sea_score", "flood_sea_match_count",
    "flood_surface_water_band", "flood_surface_water_score",
    "flood_surface_water_match_count", "flood_match_count", "flood_score",
    "flood_dominant_source", "flood_data_version", "flood_enrichment_timestamp",
    "flood_enrichment_status",
}
REQUIRED_LSOA_FIELDS = {
    "lsoa_code", "lsoa_name", "lsoa_boundary_name_cy",
    "income_deprivation_percentage", "deprivation_score", "source_dataset",
    "release_name", "source_publication_date", "licence", "attribution", "geometry",
}
OUTPUT_FIELDS = {
    "lsoa_code", "lsoa_name", "lsoa_name_welsh", "income_deprivation_percentage",
    "deprivation_score", "deprivation_source", "deprivation_source_release",
    "deprivation_match_status", "deprivation_match_count",
    "deprivation_match_method", "deprivation_candidate_codes",
    "deprivation_match_ambiguous", "deprivation_enrichment_timestamp",
    "deprivation_enrichment_notes",
}


class DeprivationEnrichmentError(ValueError):
    """Raised when an enrichment input is structurally unusable."""


def _missing_columns(data, required: set[str], label: str) -> None:
    missing = sorted(required - set(data.columns))
    if missing:
        raise DeprivationEnrichmentError(f"{label} is missing required fields: {', '.join(missing)}")


def load_inputs(
    charger_path: Path = DEFAULT_CHARGERS,
    lsoa_path: Path = DEFAULT_LSOAS,
    layer: str = LSOA_LAYER,
) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    charger_path, lsoa_path = Path(charger_path), Path(lsoa_path)
    if not charger_path.is_file():
        raise DeprivationEnrichmentError(f"Charger input not found: {charger_path}")
    if not lsoa_path.is_file():
        raise DeprivationEnrichmentError(f"LSOA input not found: {lsoa_path}")
    return pd.read_csv(charger_path), gpd.read_file(lsoa_path, layer=layer)


def _valid_coordinate(latitude: object, longitude: object) -> tuple[bool, float, float]:
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError):
        return False, float("nan"), float("nan")
    valid = pd.notna(lat) and pd.notna(lon) and -90 <= lat <= 90 and -180 <= lon <= 180
    return valid, lat, lon


def _blank(value: object) -> bool:
    return pd.isna(value) or str(value).strip() == ""


def _prepare_lsoas(lsoas: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    _missing_columns(lsoas, REQUIRED_LSOA_FIELDS, "LSOA input")
    if lsoas.crs is None:
        raise DeprivationEnrichmentError("LSOA input has no CRS")
    if lsoas["lsoa_code"].isna().any() or lsoas["lsoa_code"].astype(str).str.strip().eq("").any():
        raise DeprivationEnrichmentError("LSOA input contains missing codes")
    if lsoas["lsoa_code"].duplicated().any():
        raise DeprivationEnrichmentError("LSOA input contains duplicate codes")
    if lsoas.geometry.isna().any() or lsoas.geometry.is_empty.any() or not lsoas.geometry.is_valid.all():
        raise DeprivationEnrichmentError("LSOA input contains missing, empty, or invalid geometry")
    return lsoas.to_crs(PROCESSING_CRS)


def _choose_candidate(point: Point, candidates: gpd.GeoDataFrame) -> tuple[pd.Series, str]:
    if len(candidates) == 1:
        return candidates.iloc[0], "polygon covers point"
    ranked = candidates.copy()
    ranked["_interior_distance"] = ranked.geometry.representative_point().distance(point)
    ranked = ranked.sort_values(["_interior_distance", "lsoa_code"], kind="mergesort")
    return ranked.iloc[0], "nearest interior representative point; tie by lsoa_code"


def enrich_chargers(
    chargers: pd.DataFrame,
    lsoas: gpd.GeoDataFrame,
    timestamp: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    _missing_columns(chargers, REQUIRED_CHARGER_FIELDS, "Charger input")
    _missing_columns(chargers, REQUIRED_FLOOD_FIELDS, "Charger flood input")
    prepared = _prepare_lsoas(lsoas)
    timestamp = timestamp or datetime.now(timezone.utc).isoformat()
    duplicate_ids = int(chargers["station_id"].duplicated(keep=False).sum())
    rows: list[dict[str, object]] = []
    valid_coordinate_count = 0

    for _, original in chargers.iterrows():
        row = original.to_dict()
        flood_snapshot = {field: row.get(field) for field in REQUIRED_FLOOD_FIELDS}
        issues = []
        if _blank(row.get("station_id")):
            issues.append("missing station_id")
        for field in ("data_provider", "source_url", "licence", "attribution"):
            if _blank(row.get(field)):
                issues.append(f"missing charger provenance: {field}")
        for field in ("flood_data_version", "flood_enrichment_timestamp", "flood_enrichment_status"):
            if _blank(row.get(field)):
                issues.append(f"missing flood provenance: {field}")

        valid, lat, lon = _valid_coordinate(row.get("latitude"), row.get("longitude"))
        candidates = prepared.iloc[0:0]
        chosen = None
        method = ""
        if valid:
            valid_coordinate_count += 1
            point = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326").to_crs(PROCESSING_CRS).iloc[0]
            # A 10 cm query tolerance makes exact shared-edge/vertex coverage
            # robust to sub-metre floating-point differences after reprojection.
            positions = prepared.sindex.query(
                point.buffer(MATCH_TOLERANCE_METRES), predicate="intersects"
            )
            candidates = prepared.iloc[positions].sort_values("lsoa_code")
            if len(candidates):
                chosen, method = _choose_candidate(point, candidates)
        else:
            issues.append("invalid charger coordinates")

        codes = sorted(candidates["lsoa_code"].astype(str).tolist())
        row["deprivation_match_count"] = len(candidates)
        row["deprivation_candidate_codes"] = "|".join(codes)
        row["deprivation_match_ambiguous"] = len(candidates) > 1
        row["deprivation_match_method"] = method
        if chosen is None:
            row.update({
                "lsoa_code": "", "lsoa_name": "", "lsoa_name_welsh": "",
                "income_deprivation_percentage": None, "deprivation_score": None,
                "deprivation_source": "", "deprivation_source_release": "",
            })
            if valid:
                issues.append("no covering Cardiff LSOA")
            status = "unresolved"
        else:
            percentage = pd.to_numeric(pd.Series([chosen["income_deprivation_percentage"]]), errors="coerce").iloc[0]
            if pd.isna(percentage) or not 0 <= float(percentage) <= 100:
                issues.append("missing or invalid WIMD percentage")
                percentage = None
            row.update({
                "lsoa_code": chosen["lsoa_code"],
                "lsoa_name": chosen["lsoa_name"],
                "lsoa_name_welsh": chosen["lsoa_boundary_name_cy"],
                "income_deprivation_percentage": percentage,
                "deprivation_score": percentage,
                "deprivation_source": chosen["source_dataset"],
                "deprivation_source_release": chosen["release_name"],
            })
            for field in ("source_dataset", "release_name", "source_publication_date", "licence", "attribution"):
                if _blank(chosen[field]):
                    issues.append(f"missing deprivation provenance: {field}")
            status = "unresolved" if issues else ("ambiguous_resolved" if len(candidates) > 1 else "resolved")
        row["deprivation_match_status"] = status
        row["deprivation_enrichment_timestamp"] = timestamp
        row["deprivation_enrichment_notes"] = "; ".join(dict.fromkeys(issues))
        if any(row.get(field) != value and not (pd.isna(row.get(field)) and pd.isna(value)) for field, value in flood_snapshot.items()):
            raise DeprivationEnrichmentError("Existing flood fields changed during enrichment")
        rows.append(row)

    enriched = pd.DataFrame(rows)
    unresolved = enriched.loc[enriched["deprivation_match_status"].eq("unresolved")].copy()
    matched = enriched.loc[enriched["deprivation_match_status"].isin(["resolved", "ambiguous_resolved"])]
    scores = pd.to_numeric(matched["deprivation_score"], errors="coerce").dropna()
    provenance_fields = ["data_provider", "source_url", "licence", "attribution", "flood_data_version", "deprivation_source", "deprivation_source_release"]
    complete_provenance = int(enriched[provenance_fields].notna().all(axis=1).sum())
    report = {
        "total_input_chargers": len(chargers),
        "output_record_count": len(enriched),
        "valid_coordinate_count": valid_coordinate_count,
        "matched_count": len(matched),
        "unmatched_count": int(enriched["deprivation_match_count"].eq(0).sum()),
        "unresolved_count": len(unresolved),
        "ambiguous_match_count": int(enriched["deprivation_match_ambiguous"].sum()),
        "missing_wimd_percentage_count": int(enriched["income_deprivation_percentage"].isna().sum()),
        "duplicate_station_id_count": duplicate_ids,
        "deprivation_score_minimum": float(scores.min()) if len(scores) else None,
        "deprivation_score_maximum": float(scores.max()) if len(scores) else None,
        "deprivation_score_mean": float(scores.mean()) if len(scores) else None,
        "deprivation_score_median": float(scores.median()) if len(scores) else None,
        "unique_lsoa_count": int(matched["lsoa_code"].nunique()),
        "provenance_complete_count": complete_provenance,
        "provenance_incomplete_count": len(enriched) - complete_provenance,
        "analysis_crs": PROCESSING_CRS,
        "ambiguity_rule": "nearest interior representative point; exact distance ties use lsoa_code",
        "boundary_candidate_tolerance_metres": MATCH_TOLERANCE_METRES,
        "score_rule": "deprivation_score equals the source income_deprivation_percentage without rescaling",
        "enrichment_timestamp": timestamp,
        "output_checksums": {},
    }
    return enriched, unresolved, report


def _atomic_csv(data: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        data.to_csv(temporary, index=False)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def write_outputs(
    enriched: pd.DataFrame,
    unresolved: pd.DataFrame,
    report: dict[str, object],
    enriched_path: Path = DEFAULT_ENRICHED,
    unresolved_path: Path = DEFAULT_UNRESOLVED,
    report_path: Path = DEFAULT_REPORT,
) -> dict[str, object]:
    enriched_path, unresolved_path, report_path = map(Path, (enriched_path, unresolved_path, report_path))
    _atomic_csv(enriched, enriched_path)
    _atomic_csv(unresolved, unresolved_path)
    report["output_checksums"] = {
        enriched_path.name: _sha256(enriched_path),
        unresolved_path.name: _sha256(unresolved_path),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = report_path.with_name(f".{report_path.name}.tmp")
    try:
        temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, report_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return report


def main() -> int:
    chargers, lsoas = load_inputs()
    enriched, unresolved, report = enrich_chargers(chargers, lsoas)
    write_outputs(enriched, unresolved, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
