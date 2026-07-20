"""Enrich filtered Cardiff charging locations with prepared FRAW risk bands."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.prepare_flood_layers import (
    ATTRIBUTION,
    CATALOGUE_PUBLICATION_DATE,
    ILLUSTRATIVE_AIRIS_RISK_SCORES,
    LICENCE,
    PROCESSING_CRS,
    SOURCE_RISK_BANDS,
)


DEFAULT_CHARGERS = PROJECT_ROOT / "data" / "processed" / "cardiff_charging_sites.csv"
DEFAULT_ENRICHED = (
    PROJECT_ROOT / "data" / "processed" / "cardiff_charging_sites_flood_enriched.csv"
)
DEFAULT_UNRESOLVED = (
    PROJECT_ROOT / "data" / "processed" / "cardiff_charging_sites_flood_unresolved.csv"
)
DEFAULT_REPORT = (
    PROJECT_ROOT / "data" / "processed" / "cardiff_flood_enrichment_report.json"
)

FLOOD_INPUTS = {
    "river": (
        PROJECT_ROOT / "data" / "processed" / "flood_rivers.gpkg",
        "flood_rivers",
    ),
    "sea": (
        PROJECT_ROOT / "data" / "processed" / "flood_sea.gpkg",
        "flood_sea",
    ),
    "surface_water": (
        PROJECT_ROOT / "data" / "processed" / "flood_surface_water.gpkg",
        "flood_surface_water",
    ),
}

HAZARD_SOURCES = ("river", "sea", "surface_water")
RISK_RANK = {"Low": 1, "Medium": 2, "High": 3}
NO_MATCH_TEXT = "No mapped Low, Medium or High classification matched."
REQUIRED_CHARGER_FIELDS = {"station_id", "latitude", "longitude"}
REQUIRED_FLOOD_FIELDS = {
    "risk_band",
    "catalogue_publication_date",
    "layer_publication_date",
    "source_file_checksum",
    "source_dataset_version_note",
    "source_layer",
    "licence",
    "attribution",
}


class FloodEnrichmentError(ValueError):
    """Raised when enrichment inputs or outputs are structurally unusable."""


def load_chargers(path: Path = DEFAULT_CHARGERS) -> pd.DataFrame:
    path = Path(path)
    if not path.is_file():
        raise FloodEnrichmentError(f"Charger input not found: {path}")
    chargers = pd.read_csv(path)
    missing = sorted(REQUIRED_CHARGER_FIELDS - set(chargers.columns))
    if missing:
        raise FloodEnrichmentError(
            f"Charger input is missing required fields: {', '.join(missing)}"
        )
    return chargers


def load_flood_layers(
    inputs: Mapping[str, tuple[Path, str]] = FLOOD_INPUTS,
) -> dict[str, gpd.GeoDataFrame]:
    layers = {}
    for source in HAZARD_SOURCES:
        path, layer = inputs[source]
        path = Path(path)
        if not path.is_file():
            raise FloodEnrichmentError(f"Flood input not found: {path}")
        data = gpd.read_file(path, layer=layer)
        if data.crs is None:
            raise FloodEnrichmentError(f"Flood layer {source} has no CRS")
        if data.crs.to_string().upper() != PROCESSING_CRS:
            data = data.to_crs(PROCESSING_CRS)
        layers[source] = data
    return layers


def _provenance_issues(source: str, layer: gpd.GeoDataFrame) -> list[str]:
    missing = sorted(REQUIRED_FLOOD_FIELDS - set(layer.columns))
    if missing:
        return [f"{source}: missing provenance fields {', '.join(missing)}"]
    issues = []
    for field in REQUIRED_FLOOD_FIELDS:
        values = layer[field]
        if values.isna().any() or values.astype("string").str.strip().eq("").any():
            issues.append(f"{source}: incomplete {field}")
    if not layer.empty:
        if not layer["catalogue_publication_date"].astype(str).eq(
            CATALOGUE_PUBLICATION_DATE
        ).all():
            issues.append(f"{source}: unexpected catalogue publication date")
        if not layer["licence"].astype(str).eq(LICENCE).all():
            issues.append(f"{source}: incomplete or unexpected licence")
        if not layer["attribution"].astype(str).eq(ATTRIBUTION).all():
            issues.append(f"{source}: incomplete or unexpected attribution")
    return issues


def _data_version(layers: Mapping[str, gpd.GeoDataFrame]) -> str:
    parts = [f"FRAW catalogue {CATALOGUE_PUBLICATION_DATE}"]
    for source in HAZARD_SOURCES:
        layer = layers[source]
        if REQUIRED_FLOOD_FIELDS.issubset(layer.columns) and not layer.empty:
            dates = "/".join(sorted(layer["layer_publication_date"].astype(str).unique()))
            checksums = "/".join(sorted(layer["source_file_checksum"].astype(str).unique()))
            parts.append(f"{source} layer {dates} sha256:{checksums}")
        else:
            parts.append(f"{source} provenance incomplete")
    return " | ".join(parts)


def _valid_coordinate(latitude: object, longitude: object) -> tuple[bool, float, float]:
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return False, float("nan"), float("nan")
    if pd.isna(lat) or pd.isna(lon) or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return False, lat, lon
    return True, lat, lon


def _match_one_source(
    point: Point, layer: gpd.GeoDataFrame
) -> tuple[str, int, int, str | None]:
    """Return band, score, polygon overlap count, and an optional issue."""
    try:
        positions = layer.sindex.query(point, predicate="intersects")
        matches = layer.iloc[positions]
    except Exception as exc:
        return "", 0, 0, f"spatial matching failed: {type(exc).__name__}"
    if matches.empty:
        return NO_MATCH_TEXT, 0, 0, None

    raw_bands = matches["risk_band"] if "risk_band" in matches.columns else pd.Series(dtype="object")
    if raw_bands.empty or raw_bands.isna().any() or raw_bands.astype("string").str.strip().eq("").any():
        return "", 0, len(matches), "missing flood-risk classification"
    bands = raw_bands.astype(str).str.strip().tolist()
    unknown = sorted(set(bands) - set(SOURCE_RISK_BANDS))
    if unknown:
        return "/".join(unknown), 0, len(matches), f"unknown flood-risk classification: {unknown}"
    highest = max(bands, key=RISK_RANK.__getitem__)
    return highest, ILLUSTRATIVE_AIRIS_RISK_SCORES[highest], len(matches), None


def enrich_chargers(
    chargers: pd.DataFrame,
    layers: Mapping[str, gpd.GeoDataFrame],
    timestamp: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    missing = sorted(REQUIRED_CHARGER_FIELDS - set(chargers.columns))
    if missing:
        raise FloodEnrichmentError(
            f"Charger input is missing required fields: {', '.join(missing)}"
        )
    missing_sources = sorted(set(HAZARD_SOURCES) - set(layers))
    if missing_sources:
        raise FloodEnrichmentError(
            f"Missing flood hazard sources: {', '.join(missing_sources)}"
        )

    prepared_layers = {}
    provenance_issues = []
    for source in HAZARD_SOURCES:
        layer = layers[source]
        if layer.crs is None:
            raise FloodEnrichmentError(f"Flood layer {source} has no CRS")
        prepared_layers[source] = (
            layer
            if layer.crs.to_string().upper() == PROCESSING_CRS
            else layer.to_crs(PROCESSING_CRS)
        )
        provenance_issues.extend(_provenance_issues(source, prepared_layers[source]))

    version = _data_version(prepared_layers)
    timestamp = timestamp or datetime.now(timezone.utc).isoformat()
    enriched_rows = []
    for _, original in chargers.iterrows():
        row = original.to_dict()
        issues = list(provenance_issues)
        valid, latitude, longitude = _valid_coordinate(
            original.get("latitude"), original.get("longitude")
        )
        total_matches = 0
        source_scores = {}
        matched_sources = []

        if valid:
            point_wgs84 = gpd.GeoSeries(
                [Point(longitude, latitude)], crs="EPSG:4326"
            )
            point = point_wgs84.to_crs(PROCESSING_CRS).iloc[0]
            for source in HAZARD_SOURCES:
                band, score, match_count, issue = _match_one_source(
                    point, prepared_layers[source]
                )
                row[f"flood_{source}_band"] = band
                row[f"flood_{source}_score"] = score
                row[f"flood_{source}_match_count"] = match_count
                total_matches += match_count
                source_scores[source] = score
                if match_count:
                    matched_sources.append(source)
                if issue:
                    issues.append(f"{source}: {issue}")
        else:
            issues.append("invalid charger coordinates")
            for source in HAZARD_SOURCES:
                row[f"flood_{source}_band"] = ""
                row[f"flood_{source}_score"] = None
                row[f"flood_{source}_match_count"] = 0

        row["flood_match_count"] = total_matches
        if valid:
            maximum = max(source_scores.values(), default=0)
            row["flood_score"] = maximum
            if maximum == 0:
                row["flood_dominant_source"] = NO_MATCH_TEXT
            else:
                row["flood_dominant_source"] = "|".join(
                    source
                    for source in HAZARD_SOURCES
                    if source_scores[source] == maximum
                )
        else:
            row["flood_score"] = None
            row["flood_dominant_source"] = ""
        row["flood_data_version"] = version
        row["flood_enrichment_timestamp"] = timestamp
        row["flood_enrichment_status"] = "unresolved" if issues else "enriched"
        row["flood_enrichment_notes"] = "; ".join(dict.fromkeys(issues))
        row["flood_hazard_source_count"] = len(set(matched_sources))
        enriched_rows.append(row)

    enriched = pd.DataFrame(enriched_rows)
    unresolved = enriched.loc[
        enriched["flood_enrichment_status"].eq("unresolved")
    ].copy()
    resolved = enriched.loc[enriched["flood_enrichment_status"].eq("enriched")]

    hazard_distribution = {}
    for source in HAZARD_SOURCES:
        hazard_distribution[source] = {
            str(key): int(value)
            for key, value in enriched[f"flood_{source}_band"]
            .replace("", "Unresolved")
            .fillna("Unresolved")
            .value_counts()
            .sort_index()
            .items()
        }
    report = {
        "input_count": len(chargers),
        "output_record_count": len(enriched),
        "enriched_count": len(resolved),
        "unresolved_count": len(unresolved),
        "no_match_count": int(
            (
                resolved["flood_river_band"].eq(NO_MATCH_TEXT)
                & resolved["flood_sea_band"].eq(NO_MATCH_TEXT)
                & resolved["flood_surface_water_band"].eq(NO_MATCH_TEXT)
            ).sum()
        ),
        "distribution_by_hazard_and_band": hazard_distribution,
        "overlapping_hazard_count": int(
            enriched["flood_hazard_source_count"].gt(1).sum()
        ),
        "dominant_source_distribution": {
            str(key): int(value)
            for key, value in enriched["flood_dominant_source"]
            .replace("", "Unresolved")
            .fillna("Unresolved")
            .value_counts()
            .sort_index()
            .items()
        },
        "analysis_crs": PROCESSING_CRS,
        "flood_data_version": version,
        "enrichment_timestamp": timestamp,
        "no_match_interpretation": NO_MATCH_TEXT,
        "score_method": (
            "Maximum illustrative AIRIS score across matched FRAW hazard "
            "sources; these are not official NRW scores."
        ),
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


def write_outputs(
    enriched: pd.DataFrame,
    unresolved: pd.DataFrame,
    report: dict[str, object],
    enriched_path: Path = DEFAULT_ENRICHED,
    unresolved_path: Path = DEFAULT_UNRESOLVED,
    report_path: Path = DEFAULT_REPORT,
) -> None:
    _atomic_csv(enriched, Path(enriched_path))
    _atomic_csv(unresolved, Path(unresolved_path))
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = report_path.with_name(f".{report_path.name}.tmp")
    try:
        temporary.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temporary, report_path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    chargers = load_chargers()
    layers = load_flood_layers()
    enriched, unresolved, report = enrich_chargers(chargers, layers)
    write_outputs(enriched, unresolved, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
