import json
from unittest.mock import Mock

import pytest
import requests

from charging_schema import CANONICAL_CHARGING_FIELDS, generate_station_id
from scripts.charging_sources.base import AcquisitionError, ChargingSearchConfig
from scripts.charging_sources.open_charge_map import (
    AIRIS_USER_AGENT,
    OPEN_CHARGE_MAP_ENDPOINT,
    OpenChargeMapSource,
    load_open_charge_map_api_key,
)


def ocm_record(record_id=123, **overrides):
    record = {
        "ID": record_id,
        "AddressInfo": {
            "Title": "Cardiff Central Charging Hub",
            "AddressLine1": "1 Example Street",
            "Town": "Cardiff",
            "Postcode": "CF10 1AA",
            "Latitude": 51.4816,
            "Longitude": -3.1791,
        },
        "OperatorInfo": {"Title": "Example Operator"},
        "DataProvider": {
            "Title": "Example Data Provider",
            "License": "CC BY 4.0",
        },
        "StatusType": {"Title": "Operational", "IsOperational": True},
        "UsageType": {"Title": "Public"},
        "NumberOfPoints": 4,
        "Connections": [
            {"Quantity": 2, "PowerKW": 50},
            {"Quantity": 1, "PowerKW": 150},
        ],
        "UsageCost": "See operator tariff",
        "DateLastStatusUpdate": "2026-07-01T12:00:00Z",
    }
    record.update(overrides)
    return record


def response(payload, status=200):
    result = Mock()
    result.status_code = status
    result.text = json.dumps(payload, separators=(",", ":"))
    result.json.return_value = payload
    return result


def source_with_response(result):
    session = Mock()
    session.get.return_value = result
    return OpenChargeMapSource(api_key="test-key-never-print", session=session), session


def issue_types(report):
    return {issue["type"] for issue in report["issues"]}


def test_successful_response_uses_safe_request_and_normalises_provenance():
    source, session = source_with_response(response([ocm_record()]))
    config = ChargingSearchConfig()

    fetched = source.fetch(config)
    rows, report = source.normalise(fetched.records, config)

    assert len(rows) == 1
    row = rows[0]
    assert list(row) == list(CANONICAL_CHARGING_FIELDS)
    assert row["source_record_id"] == "123"
    assert row["station_id"] == generate_station_id("Example Data Provider", "123")
    assert row["number_of_evses"] == 4
    assert row["number_of_connectors"] == 3
    assert row["maximum_power_kw"] == 150
    assert row["data_provider"] == "Example Data Provider"
    assert row["licence"] == "CC BY 4.0"
    assert "Open Charge Map" in row["attribution"]
    assert "Example Data Provider" in row["attribution"]
    assert row["verification_status"] == "unreviewed"
    assert report["records_normalised"] == 1

    _, kwargs = session.get.call_args
    assert session.get.call_args.args[0] == OPEN_CHARGE_MAP_ENDPOINT
    assert kwargs["headers"]["X-API-Key"] == "test-key-never-print"
    assert kwargs["headers"]["User-Agent"] == AIRIS_USER_AGENT
    assert "key" not in {key.casefold() for key in kwargs["params"]}
    assert kwargs["timeout"] <= 30


def test_empty_response_is_valid():
    source, _ = source_with_response(response([]))
    fetched = source.fetch(ChargingSearchConfig())
    rows, report = source.normalise(fetched.records, ChargingSearchConfig())
    assert fetched.records == []
    assert rows == []
    assert report["records_received"] == 0


def test_timeout_is_reported_safely():
    session = Mock()
    session.get.side_effect = requests.Timeout("test-key-never-print")
    source = OpenChargeMapSource(api_key="test-key-never-print", session=session)
    with pytest.raises(AcquisitionError, match="request timed out") as error:
        source.fetch(ChargingSearchConfig())
    assert "test-key-never-print" not in str(error.value)


def test_http_error_does_not_expose_response_or_key():
    source, _ = source_with_response(response({"key": "test-key-never-print"}, 503))
    with pytest.raises(AcquisitionError, match="HTTP 503") as error:
        source.fetch(ChargingSearchConfig())
    assert "test-key-never-print" not in str(error.value)


def test_malformed_json_is_reported_safely():
    malformed = response([])
    malformed.text = "not-json"
    malformed.json.side_effect = ValueError("test-key-never-print")
    source, _ = source_with_response(malformed)
    with pytest.raises(AcquisitionError, match="malformed JSON") as error:
        source.fetch(ChargingSearchConfig())
    assert "test-key-never-print" not in str(error.value)


def test_missing_coordinates_are_flagged_without_inventing_values():
    record = ocm_record()
    record["AddressInfo"].pop("Latitude")
    record["AddressInfo"].pop("Longitude")
    source, _ = source_with_response(response([record]))
    rows, report = source.normalise([record], ChargingSearchConfig())
    assert rows[0]["latitude"] is None
    assert rows[0]["longitude"] is None
    assert "missing_coordinates" in issue_types(report)


def test_duplicate_source_ids_are_flagged():
    records = [ocm_record(123), ocm_record(123)]
    source, _ = source_with_response(response(records))
    _, report = source.normalise(records, ChargingSearchConfig())
    assert "duplicate_source_id" in issue_types(report)


def test_duplicate_or_near_duplicate_coordinates_are_flagged():
    second = ocm_record(124)
    second["AddressInfo"]["Latitude"] = 51.4817
    second["AddressInfo"]["Longitude"] = -3.1792
    records = [ocm_record(123), second]
    source, _ = source_with_response(response(records))
    _, report = source.normalise(records, ChargingSearchConfig())
    assert "duplicate_or_near_duplicate_coordinates" in issue_types(report)


def test_missing_optional_values_are_preserved_as_missing():
    record = ocm_record()
    for key in ("OperatorInfo", "UsageType", "Connections", "UsageCost", "DateLastStatusUpdate"):
        record.pop(key)
    record["AddressInfo"].pop("Postcode")
    rows, _ = OpenChargeMapSource(
        api_key="dummy", session=Mock()
    ).normalise([record], ChargingSearchConfig())
    row = rows[0]
    assert row["operator_name"] is None
    assert row["postcode"] is None
    assert row["number_of_connectors"] is None
    assert row["maximum_power_kw"] is None
    assert row["usage_cost"] is None
    assert row["source_last_updated"] is None


def test_missing_provider_unknown_status_and_outside_area_are_flagged():
    record = ocm_record(DataProvider=None, StatusType={"Title": "Mystery state"})
    record["AddressInfo"]["Latitude"] = 52.0
    rows, report = OpenChargeMapSource(
        api_key="dummy", session=Mock()
    ).normalise([record], ChargingSearchConfig(distance_km=5))
    assert rows[0]["data_provider"] is None
    assert rows[0]["station_id"] is None
    assert {
        "missing_provider",
        "unknown_operational_status",
        "outside_search_area",
    } <= issue_types(report)


def test_stable_station_id_across_repeated_normalisation():
    record = ocm_record()
    source = OpenChargeMapSource(api_key="dummy", session=Mock())
    first, _ = source.normalise([record], ChargingSearchConfig())
    second, _ = source.normalise([record], ChargingSearchConfig())
    assert first[0]["station_id"] == second[0]["station_id"]


def test_api_key_environment_precedes_streamlit_secrets():
    assert (
        load_open_charge_map_api_key(
            {"OPEN_CHARGE_MAP_API_KEY": "environment-key"},
            {"OPEN_CHARGE_MAP_API_KEY": "secret-key"},
        )
        == "environment-key"
    )


def test_api_key_falls_back_to_streamlit_secrets():
    assert (
        load_open_charge_map_api_key(
            {}, {"OPEN_CHARGE_MAP_API_KEY": "secret-key"}
        )
        == "secret-key"
    )


def test_missing_api_key_fails_clearly():
    with pytest.raises(AcquisitionError, match="OPEN_CHARGE_MAP_API_KEY is required"):
        load_open_charge_map_api_key({}, {})


def test_secret_is_not_printed_or_logged(capsys, caplog):
    secret = "super-secret-api-key"
    session = Mock()
    session.get.side_effect = requests.ConnectionError(secret)
    source = OpenChargeMapSource(api_key=secret, session=session)
    with pytest.raises(AcquisitionError) as error:
        source.fetch(ChargingSearchConfig())
    captured = capsys.readouterr()
    combined = captured.out + captured.err + caplog.text + str(error.value)
    assert secret not in combined


def test_timeout_cannot_exceed_thirty_seconds():
    with pytest.raises(ValueError, match="no more than 30"):
        ChargingSearchConfig(timeout_seconds=30.1)

