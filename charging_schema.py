"""Canonical charging-location identifiers and schema validation."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Iterable

import pandas as pd


CANONICAL_CHARGING_FIELDS = (
    "station_id",
    "source_record_id",
    "station_name",
    "address",
    "postcode",
    "latitude",
    "longitude",
    "operator_name",
    "data_provider",
    "operational_status",
    "number_of_evses",
    "number_of_connectors",
    "maximum_power_kw",
    "access_type",
    "usage_cost",
    "source_url",
    "source_last_updated",
    "licence",
    "attribution",
    "verification_status",
    "verification_notes",
)

REQUIRED_VALUE_FIELDS = {
    "station_id",
    "station_name",
    "latitude",
    "longitude",
    "data_provider",
    "verification_status",
}

VERIFICATION_STATUSES = {
    "unreviewed",
    "coordinates_checked",
    "operator_source_checked",
    "council_correlated",
    "excluded",
}

_CREDENTIAL_PATTERNS = (
    re.compile(r"(?i)://[^/\s:@]+:[^/\s@]+@"),
    re.compile(
        r"(?i)(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|client[_-]?secret)\s*[=:]\s*[^\s,;&]+"
    ),
    re.compile(
        r"(?i)[?&](?:api[_-]?key|access[_-]?token|token|password|client[_-]?secret)=[^&\s]+"
    ),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


def _normalise_identifier_part(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value)).strip().casefold()
    return re.sub(r"\s+", " ", text)


def generate_station_id(
    data_provider: str,
    source_record_id: object | None = None,
    *,
    station_name: str | None = None,
    latitude: object | None = None,
    longitude: object | None = None,
) -> str:
    """Generate a deterministic AIRIS station ID using SHA-256.

    Provider and source record ID are preferred. If the source has no stable
    record ID, normalised station name and coordinates rounded to five decimal
    places form the deterministic fallback identity.
    """
    provider = _normalise_identifier_part(data_provider)
    if not provider:
        raise ValueError("data_provider is required to generate station_id")

    if source_record_id is not None and _normalise_identifier_part(source_record_id):
        identity = f"provider={provider}|record={_normalise_identifier_part(source_record_id)}"
    else:
        name = _normalise_identifier_part(station_name or "")
        if not name or latitude is None or longitude is None:
            raise ValueError(
                "station_name, latitude and longitude are required when source_record_id is unavailable"
            )
        try:
            rounded_latitude = round(float(latitude), 5)
            rounded_longitude = round(float(longitude), 5)
        except (TypeError, ValueError):
            raise ValueError("latitude and longitude must be numeric")
        identity = (
            f"provider={provider}|name={name}|"
            f"latitude={rounded_latitude:.5f}|longitude={rounded_longitude:.5f}"
        )

    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return f"airis_{digest}"


def _missing_value(value: object) -> bool:
    if pd.isna(value):
        return True
    return isinstance(value, str) and not value.strip()


def _credential_findings(values: Iterable[object]) -> list[str]:
    findings = []
    for value in values:
        if _missing_value(value):
            continue
        text = str(value)
        if any(pattern.search(text) for pattern in _CREDENTIAL_PATTERNS):
            findings.append(text)
    return findings


def validate_charging_locations(data: pd.DataFrame) -> pd.DataFrame:
    """Validate canonical charging locations and return a defensive copy.

    Raises ValueError containing all detected schema violations. Validation
    does not mutate or silently discard source data.
    """
    if not isinstance(data, pd.DataFrame):
        raise TypeError("charging locations must be provided as a pandas DataFrame")

    errors: list[str] = []
    missing_columns = sorted(set(CANONICAL_CHARGING_FIELDS) - set(data.columns))
    if missing_columns:
        raise ValueError(f"Missing canonical charging fields: {missing_columns}")

    validated = data.copy()
    for field in REQUIRED_VALUE_FIELDS:
        missing_rows = validated[field].map(_missing_value)
        if missing_rows.any():
            errors.append(f"{field} is required at row(s) {missing_rows[missing_rows].index.tolist()}")

    station_ids = validated["station_id"].astype("string").str.strip()
    duplicate_ids = station_ids[station_ids.duplicated(keep=False) & station_ids.notna()]
    if not duplicate_ids.empty:
        errors.append(f"station_id must be unique: {sorted(duplicate_ids.unique().tolist())}")

    for field, minimum, maximum in (
        ("latitude", -90, 90),
        ("longitude", -180, 180),
    ):
        numeric = pd.to_numeric(validated[field], errors="coerce")
        invalid = numeric.isna() | ~numeric.between(minimum, maximum)
        if invalid.any():
            errors.append(
                f"{field} must be numeric and between {minimum} and {maximum} at row(s) "
                f"{invalid[invalid].index.tolist()}"
            )
        validated[field] = numeric

    for field in ("number_of_evses", "number_of_connectors", "maximum_power_kw"):
        present = ~validated[field].map(_missing_value)
        numeric = pd.to_numeric(validated[field], errors="coerce")
        invalid = present & (numeric.isna() | (numeric < 0))
        if field != "maximum_power_kw":
            invalid |= present & numeric.notna() & (numeric % 1 != 0)
        if invalid.any():
            qualifier = "a non-negative integer" if field != "maximum_power_kw" else "non-negative"
            errors.append(
                f"{field} must be {qualifier} when present at row(s) "
                f"{invalid[invalid].index.tolist()}"
            )
        validated[field] = numeric

    invalid_status = ~validated["verification_status"].isin(VERIFICATION_STATUSES)
    if invalid_status.any():
        errors.append(
            "verification_status must be one of "
            f"{sorted(VERIFICATION_STATUSES)} at row(s) "
            f"{invalid_status[invalid_status].index.tolist()}"
        )

    credential_rows = []
    for index, row in validated.iterrows():
        if _credential_findings(row.values):
            credential_rows.append(index)
    if credential_rows:
        errors.append(f"embedded credentials detected at row(s) {credential_rows}")

    if errors:
        raise ValueError("; ".join(errors))
    return validated
