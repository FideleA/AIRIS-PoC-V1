# Charging data notes

No external charging dataset has been registered yet. Add a source-register entry only after its provider, URL, publication details, licence, attribution requirements, geographic coverage, and limitations have been verified.

The existing `data/raw/chargers_cardiff.csv` is preserved as received. It currently has no headers or records, so it has not been classified or copied into `data/sample/`.

Record future verification decisions here, including identifier quality, coordinate system, coverage, completeness, update frequency, and any transformations applied.

## Canonical processing contract

The canonical field definitions, missing-value policy, deterministic station identifier, and verification workflow are defined in `data/metadata/charging_schema.md`. Canonical records use one row per physical charging location. Provider-native EVSE and connector records must be aggregated without losing their source record IDs or provenance.

Canonical validation is implemented in `charging_schema.py`. It checks the complete column contract, required values, identifier uniqueness, coordinates, non-negative equipment counts and power, controlled verification status, and embedded credential patterns.

The canonical charging dataset is upstream of AIRIS risk scoring. Flood and deprivation scores are added only in a later verified enrichment step; the existing sample dataset and dashboard remain unchanged.

## Open Charge Map acquisition adapter

The provider adapter is isolated in `scripts/charging_sources/open_charge_map.py`; orchestration and file output are in `scripts/fetch_charging_sites.py`. One approved Cardiff acquisition occurred on 2026-07-20 using a 15 km radius. It returned 131 raw records and 131 canonical rows. The raw response is preserved separately from the normalised CSV and quality report.

Planned endpoint: `https://api.openchargemap.io/v3/poi/`. Authentication uses the `X-API-Key` header. `OPEN_CHARGE_MAP_API_KEY` is read from the environment first and Streamlit secrets second. The key must never be placed in request parameters, output files, errors, or logs.

The adapter preserves the untouched JSON response, a canonical CSV, and a quality report under `data/raw/charging/`. Open Charge Map records may contain data from third-party Data Providers with their own licence and attribution requirements. Each canonical row therefore retains the returned provider, licence, attribution, source record ID, record URL, and source update time. Attribution must identify Open Charge Map and the applicable Data Provider.

The quality report flags missing coordinates, duplicate source IDs, coordinates within 50 metres of another result, unknown status mappings, missing providers, malformed records, and records outside the configured search radius. Flags require review; they are not silently replaced with invented values.

The 2026-07-20 response identified Open Charge Map Contributors and the UK National Charge Point Registry as Data Providers. Returned licence text included Creative Commons Attribution 4.0 and Open Government Licence v2.0. Provider and licence attribution remain attached to each canonical row. The acquisition quality report recorded five duplicate or near-duplicate coordinate pairs and 68 unknown operational-status mappings for review.
