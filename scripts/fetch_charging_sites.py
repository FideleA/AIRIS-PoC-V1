"""Acquire and persist canonical AIRIS charging locations.

This module performs no work on import. Running its CLI makes the live request.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence

import pandas as pd

from charging_schema import CANONICAL_CHARGING_FIELDS
from scripts.charging_sources.base import ChargingSearchConfig, ChargingSource
from scripts.charging_sources.open_charge_map import OpenChargeMapSource


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_PATH = (
    PROJECT_ROOT / "data" / "raw" / "charging" / "open_charge_map_cardiff_raw.json"
)
DEFAULT_NORMALISED_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "charging"
    / "open_charge_map_cardiff_normalised.csv"
)
DEFAULT_QUALITY_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "charging"
    / "open_charge_map_quality_report.json"
)


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def run_acquisition(
    source: ChargingSource,
    config: ChargingSearchConfig,
    *,
    raw_path: Path = DEFAULT_RAW_PATH,
    normalised_path: Path = DEFAULT_NORMALISED_PATH,
    quality_path: Path = DEFAULT_QUALITY_PATH,
) -> dict:
    """Fetch once, then atomically persist raw, canonical, and quality outputs."""
    fetched = source.fetch(config)
    rows, report = source.normalise(fetched.records, config)

    _atomic_write_text(Path(raw_path), fetched.raw_text)
    normalised = pd.DataFrame(rows, columns=CANONICAL_CHARGING_FIELDS)
    csv_text = normalised.to_csv(index=False, lineterminator="\n")
    _atomic_write_text(Path(normalised_path), csv_text)
    _atomic_write_text(
        Path(quality_path),
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch Cardiff-area Open Charge Map records for AIRIS"
    )
    parser.add_argument("--centre-latitude", type=float, default=51.4816)
    parser.add_argument("--centre-longitude", type=float, default=-3.1791)
    parser.add_argument("--distance-km", type=float, default=15.0)
    parser.add_argument("--country-code", default="GB")
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--max-results", type=int, default=500)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = ChargingSearchConfig(
        centre_latitude=args.centre_latitude,
        centre_longitude=args.centre_longitude,
        distance_km=args.distance_km,
        country_code=args.country_code,
        timeout_seconds=args.timeout_seconds,
        max_results=args.max_results,
    )
    report = run_acquisition(OpenChargeMapSource(), config)
    print(
        f"Acquired {report['records_received']} records; "
        f"normalised {report['records_normalised']}."
    )
    print(f"Raw response: {DEFAULT_RAW_PATH}")
    print(f"Normalised CSV: {DEFAULT_NORMALISED_PATH}")
    print(f"Quality report: {DEFAULT_QUALITY_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
