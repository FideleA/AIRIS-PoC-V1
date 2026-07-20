"""Provider-neutral interfaces for charging-location acquisition."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class AcquisitionError(RuntimeError):
    """Safe, user-facing acquisition failure with no credential content."""


@dataclass(frozen=True)
class ChargingSearchConfig:
    centre_latitude: float = 51.4816
    centre_longitude: float = -3.1791
    distance_km: float = 15.0
    country_code: str = "GB"
    timeout_seconds: float = 10.0
    max_results: int = 500

    def __post_init__(self) -> None:
        if not -90 <= float(self.centre_latitude) <= 90:
            raise ValueError("centre_latitude must be between -90 and 90")
        if not -180 <= float(self.centre_longitude) <= 180:
            raise ValueError("centre_longitude must be between -180 and 180")
        if float(self.distance_km) <= 0:
            raise ValueError("distance_km must be greater than zero")
        if not str(self.country_code).strip():
            raise ValueError("country_code is required")
        if not 0 < float(self.timeout_seconds) <= 30:
            raise ValueError("timeout_seconds must be greater than zero and no more than 30")
        if not 0 < int(self.max_results) <= 1000:
            raise ValueError("max_results must be between 1 and 1000")


@dataclass(frozen=True)
class FetchResponse:
    records: list[dict[str, Any]]
    raw_text: str


class ChargingSource(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name used in provenance."""

    @abstractmethod
    def request_parameters(self, config: ChargingSearchConfig) -> dict[str, Any]:
        """Return non-secret request parameters."""

    @abstractmethod
    def fetch(self, config: ChargingSearchConfig) -> FetchResponse:
        """Fetch provider records without writing files."""

    @abstractmethod
    def normalise(
        self, records: list[dict[str, Any]], config: ChargingSearchConfig
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Normalise records and return rows plus a quality report."""
