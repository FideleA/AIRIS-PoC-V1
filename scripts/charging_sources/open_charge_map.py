"""Open Charge Map acquisition adapter for AIRIS."""

from __future__ import annotations

import json
import math
import os
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Mapping

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from charging_schema import CANONICAL_CHARGING_FIELDS, generate_station_id
from scripts.charging_sources.base import (
    AcquisitionError,
    ChargingSearchConfig,
    ChargingSource,
    FetchResponse,
)


OPEN_CHARGE_MAP_ENDPOINT = "https://api.openchargemap.io/v3/poi/"
OPEN_CHARGE_MAP_ATTRIBUTION = (
    "Open Charge Map and the applicable Data Provider; provider-specific licence "
    "and attribution are retained per record."
)
AIRIS_USER_AGENT = "AIRIS-Cardiff-PoC/0.1 (verified charging-data acquisition)"
NEAR_DUPLICATE_METRES = 50.0


def load_open_charge_map_api_key(
    environ: Mapping[str, str] | None = None, secrets: Mapping[str, Any] | None = None
) -> str:
    """Load the API key from the environment, then Streamlit secrets."""
    environment = os.environ if environ is None else environ
    environment_key = str(environment.get("OPEN_CHARGE_MAP_API_KEY", "")).strip()
    if environment_key:
        return environment_key

    secret_values = secrets
    if secret_values is None:
        try:
            from streamlit import secrets as streamlit_secrets

            secret_values = streamlit_secrets
        except Exception:
            secret_values = {}
    try:
        secret_key = str(secret_values.get("OPEN_CHARGE_MAP_API_KEY", "")).strip()
    except Exception:
        secret_key = ""
    if secret_key:
        return secret_key
    raise AcquisitionError(
        "OPEN_CHARGE_MAP_API_KEY is required in the environment or Streamlit secrets"
    )


def _retrying_session() -> requests.Session:
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        status=2,
        backoff_factor=0.25,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def _value(mapping: Any, key: str) -> Any:
    return mapping.get(key) if isinstance(mapping, dict) else None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int | None:
    numeric = _number(value)
    if numeric is None or numeric < 0 or not numeric.is_integer():
        return None
    return int(numeric)


def _join_address(address: dict[str, Any]) -> str | None:
    parts = [
        _text(address.get("AddressLine1")),
        _text(address.get("AddressLine2")),
        _text(address.get("Town")),
        _text(address.get("StateOrProvince")),
    ]
    distinct = []
    for part in parts:
        if part and part not in distinct:
            distinct.append(part)
    return ", ".join(distinct) or None


def _normalise_status(status: dict[str, Any] | None) -> tuple[str | None, bool]:
    if not isinstance(status, dict):
        return None, True
    title = (_text(status.get("Title")) or "").casefold()
    if status.get("IsOperational") is True or title in {"operational", "available"}:
        return "operational", False
    if any(term in title for term in ("temporarily", "unavailable", "not operational")):
        return "temporarily_unavailable", False
    if any(term in title for term in ("planned", "awaiting", "under construction")):
        return "planned", False
    if any(term in title for term in ("removed", "decommission", "closed")):
        return "decommissioned", False
    if title:
        return "unknown", True
    return None, True


def _normalise_access(usage: dict[str, Any] | None) -> str | None:
    if not isinstance(usage, dict):
        return None
    title = (_text(usage.get("Title")) or "").casefold()
    if "public" in title:
        return "public"
    if any(term in title for term in ("private", "residents only")):
        return "private"
    if any(term in title for term in ("restricted", "customers only", "membership")):
        return "restricted"
    return "unknown" if title else None


def _haversine_metres(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class OpenChargeMapSource(ChargingSource):
    def __init__(
        self,
        api_key: str | None = None,
        *,
        session: requests.Session | None = None,
        environ: Mapping[str, str] | None = None,
        secrets: Mapping[str, Any] | None = None,
    ) -> None:
        self._api_key = api_key or load_open_charge_map_api_key(environ, secrets)
        if not str(self._api_key).strip():
            raise AcquisitionError("OPEN_CHARGE_MAP_API_KEY is required")
        self._session = session or _retrying_session()

    @property
    def provider_name(self) -> str:
        return "Open Charge Map"

    def request_parameters(self, config: ChargingSearchConfig) -> dict[str, Any]:
        return {
            "output": "json",
            "latitude": float(config.centre_latitude),
            "longitude": float(config.centre_longitude),
            "distance": float(config.distance_km),
            "distanceunit": "KM",
            "countrycode": config.country_code.strip().upper(),
            "maxresults": int(config.max_results),
            "compact": "false",
            "verbose": "false",
        }

    def fetch(self, config: ChargingSearchConfig) -> FetchResponse:
        headers = {
            "X-API-Key": self._api_key,
            "User-Agent": AIRIS_USER_AGENT,
            "Accept": "application/json",
        }
        try:
            response = self._session.get(
                OPEN_CHARGE_MAP_ENDPOINT,
                params=self.request_parameters(config),
                headers=headers,
                timeout=float(config.timeout_seconds),
            )
        except requests.Timeout as exc:
            raise AcquisitionError("Open Charge Map request timed out") from exc
        except requests.RequestException as exc:
            raise AcquisitionError("Open Charge Map request failed") from exc

        if response.status_code != 200:
            raise AcquisitionError(
                f"Open Charge Map returned HTTP {response.status_code}"
            )
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise AcquisitionError("Open Charge Map returned malformed JSON") from exc
        if not isinstance(payload, list):
            raise AcquisitionError("Open Charge Map returned an unexpected JSON structure")
        raw_text = response.text
        return FetchResponse(records=payload, raw_text=raw_text)

    def _normalise_record(self, record: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        issues: list[str] = []
        source_record_id = _text(record.get("ID")) or _text(record.get("UUID"))
        address = record.get("AddressInfo") if isinstance(record.get("AddressInfo"), dict) else {}
        latitude = _number(address.get("Latitude"))
        longitude = _number(address.get("Longitude"))
        station_name = _text(address.get("Title"))
        provider = record.get("DataProvider") if isinstance(record.get("DataProvider"), dict) else {}
        provider_name = _text(provider.get("Title"))
        if latitude is None or longitude is None:
            issues.append("missing_coordinates")
        if not provider_name:
            issues.append("missing_provider")

        station_id = None
        if provider_name and source_record_id:
            station_id = generate_station_id(provider_name, source_record_id)
        elif provider_name and station_name and latitude is not None and longitude is not None:
            station_id = generate_station_id(
                provider_name,
                station_name=station_name,
                latitude=latitude,
                longitude=longitude,
            )

        status, unknown_status = _normalise_status(record.get("StatusType"))
        if unknown_status:
            issues.append("unknown_operational_status")

        connections = record.get("Connections") if isinstance(record.get("Connections"), list) else []
        quantities = [_integer(_value(connection, "Quantity")) for connection in connections]
        known_quantities = [quantity for quantity in quantities if quantity is not None]
        powers = [_number(_value(connection, "PowerKW")) for connection in connections]
        known_powers = [power for power in powers if power is not None and power >= 0]
        number_of_connectors = sum(known_quantities) if known_quantities else None
        maximum_power = max(known_powers) if known_powers else None

        licence = provider.get("License")
        if isinstance(licence, dict):
            licence = _text(licence.get("Title"))
        else:
            licence = _text(licence)
        attribution = _text(provider.get("Title"))
        if attribution:
            attribution = f"Open Charge Map; Data Provider: {attribution}"

        source_url = (
            f"https://openchargemap.org/site/poi/details/{source_record_id}"
            if source_record_id
            else None
        )
        usage = record.get("UsageType") if isinstance(record.get("UsageType"), dict) else None
        operator = record.get("OperatorInfo") if isinstance(record.get("OperatorInfo"), dict) else {}

        row = {
            "station_id": station_id,
            "source_record_id": source_record_id,
            "station_name": station_name,
            "address": _join_address(address),
            "postcode": _text(address.get("Postcode")),
            "latitude": latitude,
            "longitude": longitude,
            "operator_name": _text(operator.get("Title")),
            "data_provider": provider_name,
            "operational_status": status,
            "number_of_evses": _integer(record.get("NumberOfPoints")),
            "number_of_connectors": number_of_connectors,
            "maximum_power_kw": maximum_power,
            "access_type": _normalise_access(usage),
            "usage_cost": _text(record.get("UsageCost")),
            "source_url": source_url,
            "source_last_updated": _text(record.get("DateLastStatusUpdate")),
            "licence": licence,
            "attribution": attribution,
            "verification_status": "unreviewed",
            "verification_notes": None,
        }
        return {field: row[field] for field in CANONICAL_CHARGING_FIELDS}, issues

    def normalise(
        self, records: list[dict[str, Any]], config: ChargingSearchConfig
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                issues.append({"type": "malformed_record", "record_index": index})
                continue
            row, record_issues = self._normalise_record(record)
            rows.append(row)
            for issue in record_issues:
                issues.append(
                    {
                        "type": issue,
                        "record_index": index,
                        "source_record_id": row["source_record_id"],
                    }
                )

        source_ids = [row["source_record_id"] for row in rows if row["source_record_id"]]
        duplicates = {value for value, count in Counter(source_ids).items() if count > 1}
        for source_id in sorted(duplicates):
            issues.append({"type": "duplicate_source_id", "source_record_id": source_id})

        coordinate_rows = [
            (index, row)
            for index, row in enumerate(rows)
            if row["latitude"] is not None and row["longitude"] is not None
        ]
        for position, (left_index, left) in enumerate(coordinate_rows):
            distance_from_centre = _haversine_metres(
                float(config.centre_latitude),
                float(config.centre_longitude),
                left["latitude"],
                left["longitude"],
            )
            if distance_from_centre > float(config.distance_km) * 1000:
                issues.append(
                    {
                        "type": "outside_search_area",
                        "record_index": left_index,
                        "source_record_id": left["source_record_id"],
                        "distance_from_centre_metres": round(distance_from_centre, 1),
                    }
                )
            for right_index, right in coordinate_rows[position + 1 :]:
                separation = _haversine_metres(
                    left["latitude"],
                    left["longitude"],
                    right["latitude"],
                    right["longitude"],
                )
                if separation <= NEAR_DUPLICATE_METRES:
                    issues.append(
                        {
                            "type": "duplicate_or_near_duplicate_coordinates",
                            "record_indices": [left_index, right_index],
                            "source_record_ids": [
                                left["source_record_id"],
                                right["source_record_id"],
                            ],
                            "separation_metres": round(separation, 1),
                        }
                    )

        issue_counts = Counter(issue["type"] for issue in issues)
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "provider": self.provider_name,
            "search": self.request_parameters(config),
            "records_received": len(records),
            "records_normalised": len(rows),
            "issue_counts": dict(sorted(issue_counts.items())),
            "issues": issues,
            "attribution": OPEN_CHARGE_MAP_ATTRIBUTION,
        }
        return rows, report
