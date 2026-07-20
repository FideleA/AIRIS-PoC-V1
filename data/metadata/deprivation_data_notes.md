# WIMD 2025 income-deprivation preparation

## Sources and selection

AIRIS uses `data/raw/deprivation/wimd_2025_income_employment_indicators.csv`, the StatsWales WIMD 2025 indicator export (SHA-256 `098890A8209FF0E9D5DB2F035A8AA117950C7B70DF3D7C0C22F297BF94918D26`). Rows are retained only when `Indicator` is exactly `People in income deprivation`, `Data description` is exactly `Percentage`, and `Area code` matches `^W01\d{6}$`.

The source `Data values` are already percentages on a 0–100 scale. They are renamed to `income_deprivation_percentage` and copied unchanged to `deprivation_score`; they are not multiplied, ranked, or rescaled. The filter produces 1,917 unique 2021 LSOA records.

The files `wimd_2025_income_ranks_reference.csv` and `wimd_2025_ranks_reference.gpkg` contain rank/reference data. They remain reference-only and are not used to calculate `deprivation_score`.

## Boundary preparation and Cardiff selection

The source boundary is `data/raw/boundaries/wales_lsoa_2021.gpkg`, layer `lsoa_2021_w_hwm` (SHA-256 `CC5266EFE14D51A12E514433E92510A718D5344B29F5689493A0777EB0ED667E`). Its 2,173 polygon-part rows represent 1,917 unique LSOAs. Names are checked for consistency within each official code before parts are dissolved. The dissolved code set exactly matches the filtered WIMD code set.

The LSOA source has no local-authority code, so selection is spatial in EPSG:27700 against official Cardiff boundary `W06000015`. Inclusion requires more than 1 m² intersection and more than 50% of the LSOA's full area. This excludes edge/point contacts and neighbouring topology slivers. Full LSOA geometry is retained, not clipped.

The output `data/processed/cardiff_lsoa_income_deprivation.gpkg` contains 218 unique Cardiff LSOAs. All geometries are non-empty, valid MultiPolygons in EPSG:27700. No repair was required.

## Interpretation and limitations

`deprivation_score` is an illustrative contextual AIRIS factor based on area-level income deprivation. It is not a direct charger engineering, failure, claims, or insurance-pricing measure, and it does not describe the circumstances of every person or property in an LSOA.

## Licence and attribution

Both inputs are reusable under the Open Government Licence v3.0.

WIMD: Source: Welsh Government, Welsh Index of Multiple Deprivation 2025 indicator data, licensed under the Open Government Licence v3.0. © Crown copyright 2025.

Boundary: Source: Office for National Statistics licensed under the Open Government Licence v3.0. Contains OS data © Crown copyright and database right 2025.
