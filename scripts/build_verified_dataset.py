"""Build the dashboard-ready verified Cardiff charging-location dataset."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "data/processed/cardiff_charging_sites_flood_deprivation_enriched.csv"
DEFAULT_VERIFIED = PROJECT_ROOT / "data/processed/cardiff_stations_verified.csv"
DEFAULT_UNRESOLVED = PROJECT_ROOT / "data/processed/cardiff_stations_verified_unresolved.csv"
DEFAULT_REPORT = PROJECT_ROOT / "data/processed/cardiff_verified_dataset_report.json"
DEFAULT_REVIEW = PROJECT_ROOT / "data/metadata/cardiff_verified_dataset_review.md"

DATASET_VERSION = "AIRIS_CARDIFF_VERIFIED_FRAW2026_WIMD2025_V1"
BUILD_REFERENCE_DATE = pd.Timestamp("2026-07-20T00:00:00Z")
OLD_SOURCE_CUTOFF = BUILD_REFERENCE_DATE - pd.DateOffset(years=5)
CARDIFF_LATITUDE_RANGE = (51.3, 51.7)
CARDIFF_LONGITUDE_RANGE = (-3.5, -2.9)
APPROVED_BOUNDARY_STATUSES = {"inside", "boundary"}

MINIMUM_FIELDS = [
    "station_id", "source_record_id", "station_name", "address", "postcode",
    "latitude", "longitude", "operator_name", "operational_status",
    "number_of_evses", "number_of_connectors", "maximum_power_kw", "access_type",
    "usage_cost", "data_provider", "source_url", "source_last_updated", "licence",
    "attribution", "verification_status", "boundary_status", "flood_river_band",
    "flood_river_score", "flood_sea_band", "flood_sea_score",
    "flood_surface_water_band", "flood_surface_water_score", "flood_score",
    "flood_dominant_source", "flood_match_count", "lsoa_code", "lsoa_name",
    "income_deprivation_percentage", "deprivation_score",
    "deprivation_match_status", "enrichment_timestamp", "dataset_version",
]
REQUIRED_INPUT_FIELDS = set(MINIMUM_FIELDS) - {"enrichment_timestamp", "dataset_version"}
REQUIRED_INPUT_FIELDS.update({
    "flood_enrichment_status", "deprivation_match_count",
    "deprivation_enrichment_timestamp", "deprivation_source",
    "deprivation_source_release",
})
PROVENANCE_FIELDS = [
    "data_provider", "source_url", "licence", "attribution",
    "flood_data_version", "deprivation_source", "deprivation_source_release",
]
FORBIDDEN_OFFLINE_FIELDS = {
    "current_temperature", "forecast_temperature", "temperature_score",
    "overall_score", "overall_risk_score", "airis_score",
}
SOURCE_RISK_BANDS = {"Low", "Medium", "High"}


class VerifiedDatasetError(ValueError):
    """Raised when the enriched source cannot be finalized safely."""


def _blank(value: object) -> bool:
    return pd.isna(value) or str(value).strip() == ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def load_input(path: Path = DEFAULT_INPUT) -> pd.DataFrame:
    path = Path(path)
    if not path.is_file():
        raise VerifiedDatasetError(f"Input not found: {path}")
    return pd.read_csv(path)


def _validate_schema(source: pd.DataFrame) -> None:
    missing = sorted(REQUIRED_INPUT_FIELDS - set(source.columns))
    if missing:
        raise VerifiedDatasetError(f"Input is missing required fields: {', '.join(missing)}")
    forbidden = sorted(FORBIDDEN_OFFLINE_FIELDS & set(source.columns))
    if forbidden:
        raise VerifiedDatasetError(
            f"Offline weather or overall-score fields are prohibited: {', '.join(forbidden)}"
        )


def _record_issues(row: pd.Series, duplicate_ids: set[str]) -> list[str]:
    issues = []
    station_id = "" if _blank(row.get("station_id")) else str(row["station_id"]).strip()
    if not station_id:
        issues.append("missing station_id")
    elif station_id in duplicate_ids:
        issues.append("duplicate station_id")

    lat = pd.to_numeric(pd.Series([row.get("latitude")]), errors="coerce").iloc[0]
    lon = pd.to_numeric(pd.Series([row.get("longitude")]), errors="coerce").iloc[0]
    if pd.isna(lat) or pd.isna(lon) or not (
        CARDIFF_LATITUDE_RANGE[0] <= lat <= CARDIFF_LATITUDE_RANGE[1]
        and CARDIFF_LONGITUDE_RANGE[0] <= lon <= CARDIFF_LONGITUDE_RANGE[1]
    ):
        issues.append("invalid Cardiff coordinates")
    if str(row.get("boundary_status", "")).strip().lower() not in APPROVED_BOUNDARY_STATUSES:
        issues.append("boundary status is not inside or boundary")

    flood_fields = [
        "flood_river_band", "flood_river_score", "flood_sea_band", "flood_sea_score",
        "flood_surface_water_band", "flood_surface_water_score", "flood_score",
        "flood_dominant_source", "flood_match_count",
    ]
    if any(_blank(row.get(field)) for field in flood_fields):
        issues.append("missing flood data")
    if str(row.get("flood_enrichment_status", "")).strip() != "enriched":
        issues.append("flood enrichment is unresolved")

    if _blank(row.get("lsoa_code")) or _blank(row.get("lsoa_name")):
        issues.append("missing LSOA assignment")
    match_count = pd.to_numeric(pd.Series([row.get("deprivation_match_count")]), errors="coerce").iloc[0]
    if str(row.get("deprivation_match_status", "")).strip() != "resolved" or match_count != 1:
        issues.append("LSOA assignment is not a resolved single match")
    percentage = pd.to_numeric(pd.Series([row.get("income_deprivation_percentage")]), errors="coerce").iloc[0]
    score = pd.to_numeric(pd.Series([row.get("deprivation_score")]), errors="coerce").iloc[0]
    if pd.isna(percentage) or not 0 <= percentage <= 100:
        issues.append("invalid deprivation percentage")
    elif pd.isna(score) or score != percentage:
        issues.append("deprivation score differs from source percentage")
    for field in PROVENANCE_FIELDS:
        if _blank(row.get(field)):
            issues.append(f"missing provenance: {field}")
    return list(dict.fromkeys(issues))


def _distribution(series: pd.Series) -> dict[str, int]:
    normalized = series.fillna("Missing").astype(str).replace("", "Missing")
    return {str(k): int(v) for k, v in normalized.value_counts().sort_index().items()}


def _manual_review_indices(data: pd.DataFrame) -> dict[int, list[str]]:
    selections: dict[int, list[str]] = {}
    def add(indices, reason):
        for index in indices:
            selections.setdefault(int(index), []).append(reason)

    add(data.index[data["verified_dataset_status"].eq("unresolved")], "unresolved")
    high = data[["flood_river_band", "flood_sea_band", "flood_surface_water_band"]].eq("High").any(axis=1)
    add(data.index[high], "High flood band")
    hazard_count = data[["flood_river_band", "flood_sea_band", "flood_surface_water_band"]].isin(SOURCE_RISK_BANDS).sum(axis=1)
    add(data.index[hazard_count.gt(1)], "multi-hazard")
    ambiguous = data.get("deprivation_match_ambiguous", pd.Series(False, index=data.index)).fillna(False).astype(bool)
    add(data.index[ambiguous], "ambiguous LSOA match")
    valid_scores = pd.to_numeric(data["deprivation_score"], errors="coerce")
    add(valid_scores.nlargest(5).index, "five highest deprivation scores")
    add(valid_scores.nsmallest(5).index, "five lowest deprivation scores")
    dates = pd.to_datetime(data["source_last_updated"], errors="coerce", utc=True)
    add(data.index[dates.lt(OLD_SOURCE_CUTOFF)], f"source update before {OLD_SOURCE_CUTOFF.date()}")
    return selections


def build_review(data: pd.DataFrame, selections: dict[int, list[str]]) -> str:
    lines = [
        "# Cardiff verified dataset manual review", "",
        f"Dataset version: `{DATASET_VERSION}`", "",
        "This sample is for manual verification only; no record was reclassified or removed.", "",
        f"Old source records are those updated before `{OLD_SOURCE_CUTOFF.date()}`.", "",
        f"Selected records: {len(selections)}", "",
        "| station_id | station_name | operator | flood_score | deprivation_score | source_last_updated | review reasons |",
        "|---|---|---|---:|---:|---|---|",
    ]
    for index in sorted(selections, key=lambda i: (str(data.loc[i, "station_id"]), i)):
        row = data.loc[index]
        values = [
            row.get("station_id", ""), row.get("station_name", ""), row.get("operator_name", ""),
            row.get("flood_score", ""), row.get("deprivation_score", ""),
            row.get("source_last_updated", ""), "; ".join(selections[index]),
        ]
        escaped = [str(value).replace("|", "\\|").replace("\n", " ") for value in values]
        lines.append("| " + " | ".join(escaped) + " |")
    return "\n".join(lines) + "\n"


def build_verified_dataset(
    source: pd.DataFrame,
    build_timestamp: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object], str]:
    _validate_schema(source)
    duplicate_ids = set(
        source.loc[source["station_id"].notna() & source["station_id"].duplicated(False), "station_id"].astype(str)
    )
    rows = []
    for _, original in source.iterrows():
        row = original.to_dict()
        issues = _record_issues(original, duplicate_ids)
        row["enrichment_timestamp"] = original["deprivation_enrichment_timestamp"]
        row["dataset_version"] = DATASET_VERSION
        row["verified_dataset_status"] = "usable" if not issues else "unresolved"
        row["verified_dataset_notes"] = "; ".join(issues)
        rows.append(row)
    all_records = pd.DataFrame(rows)
    ordered_columns = MINIMUM_FIELDS + [c for c in all_records.columns if c not in MINIMUM_FIELDS]
    all_records = all_records[ordered_columns].sort_values(
        ["station_id", "source_record_id"], kind="mergesort", na_position="last"
    ).reset_index(drop=True)
    usable = all_records.loc[all_records["verified_dataset_status"].eq("usable")].copy()
    unresolved = all_records.loc[all_records["verified_dataset_status"].eq("unresolved")].copy()

    score = pd.to_numeric(usable["deprivation_score"], errors="coerce").dropna()
    dates = pd.to_datetime(all_records["source_last_updated"], errors="coerce", utc=True)
    missing_summary = {
        field: int(all_records[field].isna().sum() + all_records[field].astype("string").str.strip().eq("").sum())
        for field in MINIMUM_FIELDS
    }
    provenance_complete = all_records[PROVENANCE_FIELDS].apply(
        lambda column: column.notna() & column.astype("string").str.strip().ne("")
    ).all(axis=1)
    report = {
        "source_record_count": len(source), "usable_verified_count": len(usable),
        "unresolved_count": len(unresolved),
        "operator_distribution": _distribution(all_records["operator_name"]),
        "operational_status_distribution": _distribution(all_records["operational_status"]),
        "flood_band_distribution": {
            hazard: _distribution(all_records[f"flood_{hazard}_band"])
            for hazard in ("river", "sea", "surface_water")
        },
        "dominant_hazard_distribution": _distribution(all_records["flood_dominant_source"]),
        "deprivation_score_statistics": {
            "minimum": float(score.min()) if len(score) else None,
            "maximum": float(score.max()) if len(score) else None,
            "mean": float(score.mean()) if len(score) else None,
            "median": float(score.median()) if len(score) else None,
        },
        "missing_data_summary": missing_summary,
        "duplicate_summary": {
            "duplicate_station_id_values": len(duplicate_ids),
            "records_with_duplicate_station_id": int(source["station_id"].isin(duplicate_ids).sum()),
        },
        "source_recency_summary": {
            "earliest": dates.min().isoformat() if dates.notna().any() else None,
            "latest": dates.max().isoformat() if dates.notna().any() else None,
            "missing_or_invalid": int(dates.isna().sum()),
            "old_before": str(OLD_SOURCE_CUTOFF.date()),
            "old_record_count": int(dates.lt(OLD_SOURCE_CUTOFF).sum()),
        },
        "provenance_completeness": {
            "complete_count": int(provenance_complete.sum()),
            "incomplete_count": int((~provenance_complete).sum()),
        },
        "dataset_version": DATASET_VERSION,
        "build_timestamp": build_timestamp or datetime.now(timezone.utc).isoformat(),
        "output_checksums": {},
    }
    review = build_review(all_records, _manual_review_indices(all_records))
    return usable, unresolved, report, review


def _atomic_text(text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_outputs(
    usable: pd.DataFrame, unresolved: pd.DataFrame, report: dict[str, object], review: str,
    verified_path: Path = DEFAULT_VERIFIED, unresolved_path: Path = DEFAULT_UNRESOLVED,
    report_path: Path = DEFAULT_REPORT, review_path: Path = DEFAULT_REVIEW,
) -> dict[str, object]:
    verified_path, unresolved_path, report_path, review_path = map(
        Path, (verified_path, unresolved_path, report_path, review_path)
    )
    _atomic_text(usable.to_csv(index=False), verified_path)
    _atomic_text(unresolved.to_csv(index=False), unresolved_path)
    _atomic_text(review, review_path)
    report["output_checksums"] = {
        path.name: _sha256(path) for path in (verified_path, unresolved_path, review_path)
    }
    _atomic_text(json.dumps(report, indent=2, sort_keys=True) + "\n", report_path)
    return report


def main() -> int:
    usable, unresolved, report, review = build_verified_dataset(load_input())
    write_outputs(usable, unresolved, report, review)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
