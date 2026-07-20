# Flood Risk Assessment Wales data notes

## Source and permitted use

AIRIS uses the Natural Resources Wales (NRW) Flood Risk Assessment Wales (FRAW) layers for rivers, sea, and surface water and small watercourses. The catalogue release date is `2026-05-21`. The raw GeoPackages are reproducible downloads from the [DataMapWales FRAW catalogue](https://datamap.gov.wales/layergroups/inspire-nrw%3AFloodRiskAssessmentWales) and remain ignored because of their size.

Licence: Open Government Licence for Public Sector Information.

Required attribution:

> Contains Natural Resources Wales information © Natural Resources Wales and database right. All rights reserved. Some features of this information are based on digital spatial data licensed from the UK Centre for Ecology & Hydrology © UKCEH. Defra, Met Office and DARD Rivers Agency © Crown copyright. © Cranfield University. © James Hutton Institute. Contains OS data © Crown copyright and database right.

## Risk bands and AIRIS configuration

The source polygons contain only `High`, `Medium`, and `Low`. AIRIS normalises the complete point-matching result set to `Very Low`, `Low`, `Medium`, and `High`. `Very Low` is never constructed as a polygon: it may be inferred later only when a location is outside all published High/Medium/Low polygons for the relevant flood source. NRW guidance describes Very Low as an annual probability below 1 in 1,000; it does not mean no risk.

The configurable illustrative AIRIS transformation is:

| Band | AIRIS value |
|---|---:|
| Very Low | 10 |
| Low | 35 |
| Medium | 65 |
| High | 90 |

These values are illustrative AIRIS transformations, not official NRW scores. Charger-level matching and scoring are deliberately outside the preparation pipeline.

## Version handling

Every processed feature preserves `catalogue_publication_date`, `layer_publication_date`, `source_file_checksum`, and `source_dataset_version_note`. Source `pub_date` is never overwritten.

- Rivers: internal `pub_date` is `2026-05-21`.
- Sea: internal `pub_date` is `2026-05-21`. The downloaded schema has no `objectid`; none is invented. A deterministic AIRIS internal feature identifier is generated from source content where needed.
- Surface water and small watercourses: internal `pub_date` is `2022-11-28`, which differs from the 2026-05-21 catalogue release. Both dates are retained because they describe different metadata levels.

## Bounded Cardiff preparation

Processing uses EPSG:27700. `scripts/prepare_flood_layers.py` obtains each national feature count from layer metadata, reads only the indexed bounding box of the official Cardiff boundary with a 100 metre safety margin, and then retains only features intersecting the exact Cardiff administrative boundary. The full 3.99 GB surface-water layer is never loaded.

Polygon and MultiPolygon geometries are supported. Only the Cardiff subset is validated. Invalid subset geometries are passed through `shapely.make_valid`, polygonal components are retained and unioned, and empty or non-polygonal outcomes are retained as flagged records with null output geometry. Failed repairs are never silently discarded.

## Prepared Cardiff outputs

Preparation on 2026-07-20 produced:

| Flood source | National features | Bounded read | Cardiff subset | Invalid before repair | Repaired | Unrepaired | Layer `pub_date` | Raw SHA-256 |
|---|---:|---:|---:|---:|---:|---:|---|---|
| Rivers | 105,679 | 3,293 | 2,531 | 0 | 0 | 0 | 2026-05-21 | `5E26DD370C446C48BC69F7CAC19FC71633F771E4C04B53A55AD8F2C48DF06CF2` |
| Sea | 29,494 | 4,275 | 3,158 | 0 | 0 | 0 | 2026-05-21 | `125999A7F1C4C46F281B03F2B2E98985BFBE88BA8F61424132FAA364F3E7DFFA` |
| Surface water and small watercourses | 2,805,540 | 51,822 | 27,217 | 359 | 359 | 0 | 2022-11-28 | `432444DC177277C9CEF467E24A798224C27E053904B5AA471B7604646204D22D` |

All source and processed layers use EPSG:27700. The spatial read bounding box was `(306782.3988999787, 164486.29699965226, 326032.9011000097, 185366.8971996551)` metres, comprising the Cardiff boundary bounds plus the documented 100 metre margin. Exact intersection with the unbuffered administrative boundary determined the output subset.
