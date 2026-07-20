import json
import shutil
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest

from charging_schema import CANONICAL_CHARGING_FIELDS
from scripts.charging_sources.base import ChargingSearchConfig, ChargingSource, FetchResponse
from scripts.fetch_charging_sites import run_acquisition


@pytest.fixture
def workspace_tmp_dir():
    path = Path(__file__).parent / ".tmp" / str(uuid4())
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class FakeSource(ChargingSource):
    @property
    def provider_name(self):
        return "Fake Provider"

    def request_parameters(self, config):
        return {
            "latitude": config.centre_latitude,
            "longitude": config.centre_longitude,
            "distance": config.distance_km,
            "countrycode": config.country_code,
        }

    def fetch(self, config):
        return FetchResponse(records=[{"ID": 1}], raw_text='[{"ID":1}]')

    def normalise(self, records, config):
        row = {field: None for field in CANONICAL_CHARGING_FIELDS}
        row.update(
            {
                "station_id": "airis_0123456789abcdef0123",
                "source_record_id": "1",
                "station_name": "Test site",
                "latitude": 51.48,
                "longitude": -3.18,
                "data_provider": "Fake Provider",
                "verification_status": "unreviewed",
                "attribution": "Fake Provider attribution",
            }
        )
        return [row], {
            "provider": self.provider_name,
            "records_received": 1,
            "records_normalised": 1,
            "search": self.request_parameters(config),
            "issue_counts": {},
            "issues": [],
            "attribution": "Fake Provider attribution",
        }


def test_acquisition_writes_expected_raw_normalised_and_quality_files(workspace_tmp_dir):
    raw_path = workspace_tmp_dir / "open_charge_map_cardiff_raw.json"
    normalised_path = workspace_tmp_dir / "open_charge_map_cardiff_normalised.csv"
    quality_path = workspace_tmp_dir / "open_charge_map_quality_report.json"

    report = run_acquisition(
        FakeSource(),
        ChargingSearchConfig(),
        raw_path=raw_path,
        normalised_path=normalised_path,
        quality_path=quality_path,
    )

    assert raw_path.read_text(encoding="utf-8") == '[{"ID":1}]'
    normalised = pd.read_csv(normalised_path)
    assert list(normalised.columns) == list(CANONICAL_CHARGING_FIELDS)
    assert normalised.loc[0, "source_record_id"] == 1
    assert normalised.loc[0, "attribution"] == "Fake Provider attribution"
    assert json.loads(quality_path.read_text(encoding="utf-8")) == report


def test_acquisition_writes_header_only_csv_for_empty_response(workspace_tmp_dir):
    class EmptySource(FakeSource):
        def fetch(self, config):
            return FetchResponse(records=[], raw_text="[]")

        def normalise(self, records, config):
            return [], {
                "provider": self.provider_name,
                "records_received": 0,
                "records_normalised": 0,
                "search": self.request_parameters(config),
                "issue_counts": {},
                "issues": [],
                "attribution": "Fake Provider attribution",
            }

    raw_path = workspace_tmp_dir / "raw.json"
    normalised_path = workspace_tmp_dir / "normalised.csv"
    quality_path = workspace_tmp_dir / "quality.json"
    run_acquisition(
        EmptySource(),
        ChargingSearchConfig(),
        raw_path=raw_path,
        normalised_path=normalised_path,
        quality_path=quality_path,
    )
    assert raw_path.read_text(encoding="utf-8") == "[]"
    assert list(pd.read_csv(normalised_path).columns) == list(CANONICAL_CHARGING_FIELDS)
