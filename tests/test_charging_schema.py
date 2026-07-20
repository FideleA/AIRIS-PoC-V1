import pandas as pd
import pytest

from charging_schema import (
    CANONICAL_CHARGING_FIELDS,
    VERIFICATION_STATUSES,
    generate_station_id,
    validate_charging_locations,
)


def valid_record(**overrides):
    record = {
        "station_id": "airis_0123456789abcdef0123",
        "source_record_id": "000123",
        "station_name": "Cardiff Central Charging Hub",
        "address": "1 Example Street, Cardiff",
        "postcode": "CF10 1AA",
        "latitude": 51.4816,
        "longitude": -3.1791,
        "operator_name": "Example Operator",
        "data_provider": "Example Provider",
        "operational_status": "operational",
        "number_of_evses": 4,
        "number_of_connectors": 8,
        "maximum_power_kw": 150.0,
        "access_type": "public",
        "usage_cost": "See operator tariff",
        "source_url": "https://example.invalid/charging/000123",
        "source_last_updated": "2026-07-01T12:00:00Z",
        "licence": "Example licence",
        "attribution": "Example attribution",
        "verification_status": "unreviewed",
        "verification_notes": None,
    }
    record.update(overrides)
    return record


def frame(**overrides):
    return pd.DataFrame([valid_record(**overrides)], columns=CANONICAL_CHARGING_FIELDS)


def test_valid_canonical_record_passes_and_preserves_columns():
    validated = validate_charging_locations(frame())
    assert list(validated.columns) == list(CANONICAL_CHARGING_FIELDS)


def test_all_canonical_columns_are_required():
    data = frame().drop(columns=["operator_name"])
    with pytest.raises(ValueError, match="Missing canonical charging fields"):
        validate_charging_locations(data)


@pytest.mark.parametrize(
    "field",
    [
        "station_id",
        "station_name",
        "latitude",
        "longitude",
        "data_provider",
        "verification_status",
    ],
)
def test_required_values_cannot_be_missing(field):
    with pytest.raises(ValueError, match=field):
        validate_charging_locations(frame(**{field: None}))


def test_optional_values_may_be_missing():
    optional = set(CANONICAL_CHARGING_FIELDS) - {
        "station_id",
        "station_name",
        "latitude",
        "longitude",
        "data_provider",
        "verification_status",
    }
    validated = validate_charging_locations(frame(**{field: None for field in optional}))
    assert len(validated) == 1


def test_station_id_must_be_unique():
    data = pd.DataFrame([valid_record(), valid_record()])
    with pytest.raises(ValueError, match="station_id must be unique"):
        validate_charging_locations(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("latitude", "not-a-number"),
        ("longitude", "not-a-number"),
        ("latitude", 90.01),
        ("latitude", -90.01),
        ("longitude", 180.01),
        ("longitude", -180.01),
    ],
)
def test_coordinates_must_be_numeric_and_in_global_ranges(field, value):
    with pytest.raises(ValueError, match=field):
        validate_charging_locations(frame(**{field: value}))


def test_numeric_coordinate_strings_are_normalised_to_numbers():
    validated = validate_charging_locations(frame(latitude="51.4816", longitude="-3.1791"))
    assert validated.loc[0, "latitude"] == pytest.approx(51.4816)
    assert validated.loc[0, "longitude"] == pytest.approx(-3.1791)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("number_of_evses", -1),
        ("number_of_connectors", -1),
        ("number_of_evses", 1.5),
        ("number_of_connectors", 2.25),
        ("maximum_power_kw", -0.1),
        ("maximum_power_kw", "invalid"),
    ],
)
def test_counts_and_power_must_be_non_negative(field, value):
    with pytest.raises(ValueError, match=field):
        validate_charging_locations(frame(**{field: value}))


@pytest.mark.parametrize("status", sorted(VERIFICATION_STATUSES))
def test_each_verification_status_is_valid(status):
    validated = validate_charging_locations(frame(verification_status=status))
    assert validated.loc[0, "verification_status"] == status


def test_unknown_verification_status_is_rejected():
    with pytest.raises(ValueError, match="verification_status must be one of"):
        validate_charging_locations(frame(verification_status="verified"))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_url", "https://user:password@example.invalid/records/1"),
        ("source_url", "https://example.invalid/data?api_key=secret-value"),
        ("verification_notes", "client_secret=do-not-store-this"),
        ("verification_notes", "-----BEGIN PRIVATE KEY-----"),
    ],
)
def test_embedded_credentials_are_rejected(field, value):
    with pytest.raises(ValueError, match="embedded credentials"):
        validate_charging_locations(frame(**{field: value}))


def test_station_id_is_stable_from_provider_and_source_record():
    first = generate_station_id("Example Provider", "000123")
    second = generate_station_id("  EXAMPLE   PROVIDER ", "000123")
    assert first == second
    assert first.startswith("airis_")
    assert len(first) == 26


def test_station_id_changes_for_different_source_records():
    assert generate_station_id("Example Provider", "1") != generate_station_id(
        "Example Provider", "2"
    )


def test_station_id_fallback_uses_normalised_name_and_rounded_coordinates():
    first = generate_station_id(
        "Example Provider",
        station_name="Cardiff  Central Hub",
        latitude=51.481601,
        longitude=-3.179101,
    )
    second = generate_station_id(
        "example provider",
        station_name=" cardiff central hub ",
        latitude=51.481602,
        longitude=-3.179102,
    )
    assert first == second


def test_station_id_fallback_requires_name_and_coordinates():
    with pytest.raises(ValueError, match="station_name, latitude and longitude"):
        generate_station_id("Example Provider", station_name="Incomplete")


def test_schema_retains_existing_airis_location_keys_for_later_scoring_enrichment():
    assert {"station_id", "station_name", "latitude", "longitude"} <= set(
        CANONICAL_CHARGING_FIELDS
    )
    assert {"flood_score", "deprivation_score"}.isdisjoint(CANONICAL_CHARGING_FIELDS)
