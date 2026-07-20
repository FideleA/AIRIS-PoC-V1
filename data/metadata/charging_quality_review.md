# Cardiff charging-location quality review

Review date: 2026-07-20  
Acquisition date: 2026-07-20  
Source: Open Charge Map Cardiff-centred 15 km query  
Files reviewed: provider-native JSON, canonical CSV, and generated quality report under `data/raw/charging/`

No source or canonical records were modified, excluded, merged, or deduplicated during this review.

## Executive assessment

The acquisition is structurally strong but is not yet suitable as a Cardiff-only dashboard source. All 131 source records became canonical rows, and every canonical row has a name, valid coordinate pair, address, postcode, maximum-power value, provider attribution, licence text, and unique source identifier. The material issues are:

- a radial API query is not equivalent to the Cardiff administrative boundary;
- 62 records have strong address evidence of being in neighbouring areas;
- 68 records have no usable normalized operational status (34 null and 34 `unknown`);
- EVSE and connector counts are absent in 65 rows each;
- five close/name-similar pairs require physical-location review;
- 26 records have source-update timestamps more than five years old.

These findings are review flags. They are not evidence that records should automatically be deleted or merged.

## Review method

- Counts were independently recalculated from raw JSON and canonical CSV and compared with the generated quality report.
- Coordinate validity used WGS84 global ranges. Exact-coordinate comparison used coordinates as stored.
- Near duplicates in this review mean distinct coordinate pairs no more than 25 metres apart, calculated with the haversine formula.
- Similar-name candidates used case-folded alphanumeric names, `SequenceMatcher` similarity of at least 0.75, and separation no more than 50 metres.
- Recency is measured against the acquisition date, not the current system clock.
- “Likely outside Cardiff” uses explicit address/name evidence for neighbouring places. It is deliberately conservative and is not a substitute for a verified Cardiff boundary polygon.

## Completeness and validity

| Measure | Result |
|---|---:|
| Raw source records | 131 |
| Normalised locations | 131 |
| Missing station names | 0 |
| Missing coordinate pairs | 0 |
| Invalid latitude/longitude values | 0 |
| Duplicate source IDs | 0 |
| Identical coordinate groups | 0 |
| Near-coordinate pairs within 25 m | 3 |
| Similar-name pairs within 50 m | 5 |
| Missing postcodes | 0 |
| Missing addresses | 0 |
| Missing EVSE counts | 65 (49.6%) |
| Present EVSE counts | 66 (50.4%) |
| Missing connector counts | 65 (49.6%) |
| Present connector counts | 66 (50.4%) |
| Missing maximum-power values | 0 |
| Weak or missing attribution/licence | 0 |
| Rows reporting more than one EVSE or connector | 62 |

Zero must not be substituted for missing equipment counts. The 62 multi-equipment rows may correctly describe multi-EVSE locations; they should remain one canonical location unless provider evidence proves that a row is itself an accidental aggregate.

## Operational status

| Canonical status | Records | Share |
|---|---:|---:|
| `operational` | 63 | 48.1% |
| `unknown` | 34 | 26.0% |
| Missing | 34 | 26.0% |

The acquisition quality report reports 68 `unknown_operational_status` issues because it intentionally combines missing source status and unrecognised status mappings. This agrees with the canonical distribution above.

Missing-status source IDs:

`252108, 252105, 157867, 157868, 200352, 252001, 136139, 214123, 187690, 200334, 200416, 251500, 200454, 187747, 200520, 214029, 260847, 214011, 200652, 213993, 251106, 200709, 268050, 268046, 268047, 268048, 136569, 200715, 157910, 200729, 157804, 200637, 214501, 214500`

Unknown-status source IDs:

`285782, 285778, 285830, 285770, 285931, 9814, 285780, 285963, 285666, 285657, 286066, 285651, 16281, 286092, 285575, 285584, 285600, 285542, 285544, 285529, 285526, 286425, 285518, 285479, 285483, 286506, 285482, 286565, 285476, 92837, 285485, 286412, 286475, 173611`

## Operator distribution

| Operator | Locations |
|---|---:|
| Connected Kerb | 31 |
| POD Point (UK) | 17 |
| BP Pulse (UK) | 15 |
| Evolt Network (Swarco E.Connect) | 15 |
| Osprey Charging | 11 |
| The GeniePoint Network (EQUANS EV Solutions) | 6 |
| InstaVolt Ltd | 5 |
| Silverstone Green Energy | 5 |
| ChargePoint | 4 |
| Drax Energy Solutions Limited | 3 |
| Zero Carbon World | 3 |
| Electric Highway (UK) | 2 |
| Hubsta | 2 |
| Nissan UK Dealer Network | 2 |
| Tesla (Tesla-only charging) | 2 |
| Business Owner at Location | 1 |
| Charge & Drive (Fortum) | 1 |
| Dragon Charging | 1 |
| GridServe | 1 |
| Roam Charging (UK) | 1 |
| Tesla (including non-Tesla) | 1 |
| Vend Electric | 1 |
| VIRTA | 1 |

Operator labels are provider-controlled and have not been consolidated. For example, the two Tesla labels may reflect materially different access arrangements and should not be collapsed merely for reporting convenience.

## Source-update recency

| Age at acquisition | Records |
|---|---:|
| Up to 1 year | 1 |
| More than 1 and up to 3 years | 64 |
| More than 3 and up to 5 years | 40 |
| More than 5 years | 26 |
| Missing/invalid timestamp | 0 |

Earliest source update: `2015-05-27T11:43:00Z`  
Latest source update: `2025-10-14T08:54:00Z`

Records older than five years requiring recency review:

`60879, 88787, 47246, 117888, 132454, 132455, 115033, 47476, 132459, 132456, 132462, 132460, 132461, 9814, 127599, 132457, 132458, 16281, 13553, 127106, 101139, 167024, 47114, 127107, 31389, 173611`

## Duplicate and co-location candidates

There are no identical stored coordinate pairs and no duplicate source IDs.

| Source IDs | Names | Distance | Name similarity | Review reason |
|---|---|---:|---:|---|
| 60879 / 88787 | St. David's Shopping Centre Car Park / St David's Shopping Centre | 13.5 m | 0.852 | Same destination but different operators; likely legitimate co-location, not an automatic duplicate. |
| 252108 / 252105 | St Davids Shopping Centre Car Park / same | 4.2 m | 1.000 | Same operator and name; strongest duplicate or separate-equipment candidate. |
| 268046 / 268047 | MISKIN A3 / MISKIN A10 | 22.8 m | 0.842 | Named bays/assets at a common site; likely separate EVSEs represented as locations. |
| 157867 / 157868 | NCP Dumfries Place / same | 26.4 m | 1.000 | Outside the 25 m threshold but within 50 m; same operator/name requires review. |
| 268047 / 268048 | MISKIN A10 / MISKIN A19 | 29.5 m | 0.900 | Named bays/assets at a common site; likely separate EVSEs represented as locations. |

The St David's group actually contains four records in a small area (`60879`, `88787`, `252108`, `252105`) and should be reviewed as one physical-location cluster. Different operators at one car park must remain distinguishable even if a later location-level view groups them.

## Geographic scope

The acquisition used a 15 km radius around central Cardiff. A radius includes parts of the Vale of Glamorgan, Caerphilly, Rhondda Cynon Taf, Newport, and other neighbouring areas. The quality report correctly shows zero records outside the requested radius, but that does **not** mean all records are inside Cardiff.

Address/name evidence strongly indicates at least 62 records outside Cardiff. The groups requiring boundary review are:

| Locality evidence | Source IDs |
|---|---|
| Barry / Sully | `285657, 285651, 101139, 285575, 285584, 285600, 285542, 285544, 187633, 285529, 173041, 285526, 135576, 213993, 285518, 251106, 47114, 285479, 285483, 285482, 285476, 285485` |
| Penarth / Cosmeston | `285666, 214029, 260847` |
| Vale of Glamorgan / Dyffryn | `24153` |
| Caerphilly / Machen / Trethomas | `200652, 167024, 260057, 259892, 286506, 149810, 286565, 286425, 200709` |
| Pontyclun / Miskin / Talbot Green | `268050, 268046, 268047, 268048, 205043` |
| Pontypridd | `136569, 54514, 92837, 286412, 286475, 259992` |
| Newport / Rogerstone / Risca | `251500, 16281, 127107, 112843, 31389, 157910, 187801, 173047, 200637, 214500, 213043, 259470, 173611, 214501` |
| Abertridwr / Llanbradach | `200715, 200729` |

This list is evidence-based but not exhaustive. For example, Cardiff Airport and western-edge records may also fall outside the authority boundary despite ambiguous address labels. No row should be excluded solely from this locality heuristic.

## Cardiff Council cross-check

Cardiff Council's October 2022 publication named 12 installation locations. Strong name matches in the acquired data were found for eight: Star Hub (`285780`), College Road (`285963`), Tewkesbury Place (`285931`), Penlline Road (`286066`), North Road (`285830`), Castle Mews (`285782`), Sophia Gardens (`285778`), and Harvey Street (`285770`). No direct name match was found for Taffs Mead Embankment, Heath Park Car Park, Havannah Street Car Park, or Pontcanna/Llandaff Fields Car Park. Absence of a name match is not evidence that a charger is absent; names, operators, commissioning dates, and source coverage can differ. [Cardiff Council newsroom, 2022](https://www.cardiffnewsroom.co.uk/releases/e25/30010.html)

The current Council car-parks page corroborates EV charging bays at North Road, Sophia Gardens, Havannah Street, Pontcanna Fields, and Severn Road, while the acquired data strongly matches North Road, Sophia Gardens, and Severn Road. The page currently reports zero charging bays at Heath Park, illustrating why a 2022 planned-installation list should not be treated as a timeless ground truth. [Cardiff Council car parks](https://www.cardiff.gov.uk/article/2388/Car-parks)

Council reporting in October 2024 referred to around 200 publicly accessible charge points and anticipated continued commercial growth. That figure is not directly comparable with 131 canonical physical locations because a location may contain multiple EVSEs/connectors and the Council list is not presented as a complete location-level registry. [Cardiff Council newsroom, 2024](https://www.cardiffnewsroom.co.uk/releases/c25/34299.html)

## Attribution review

All rows contain:

- a `data_provider`;
- returned licence text;
- attribution naming Open Charge Map and the returned Data Provider;
- a record-level source URL.

No weak or missing attribution was detected structurally. This does not constitute a legal determination. Any published derivative must continue to retain the per-row provider licence and visible attribution requirements.

## Proposed deduplication rules

These rules are proposals for a future reviewed pipeline, not actions taken in this review:

1. Never deduplicate on coordinates alone.
2. Treat identical `data_provider + source_record_id` as a source duplicate; quarantine repeated rows and retain the first raw occurrence only in a derived dataset after review.
3. Form review clusters using a maximum 50 m separation, normalized name similarity of at least 0.75, shared postcode/address evidence, or an exact provider/operator identifier.
4. Prefer a single physical-location entity with child operator/EVSE records when evidence shows multiple chargers at one car park or destination.
5. Do not merge different operators automatically; co-located networks can be legitimate.
6. Do not merge records whose names encode distinct bays/assets (`A3`, `A10`, `A19`) without operator evidence that they form one physical location.
7. Preserve every source record and source ID in a lineage table even when a derived location entity groups several records.
8. Assign merge decisions, evidence, reviewer, and date explicitly; deterministic rules should only generate candidates.

## Proposed geographic filtering rules

1. Obtain and register an authoritative Cardiff Council administrative-boundary polygon with verified licence and publication metadata.
2. Transform all coordinates to WGS84 consistently and perform a point-in-polygon check using `covers`, so points exactly on the boundary are retained for review.
3. Classify results as `inside`, `boundary_review`, or `outside`; use a small documented boundary tolerance only for positional uncertainty, not to expand Cardiff arbitrarily.
4. Use locality/postcode evidence as a review aid, never as the sole spatial test.
5. Retain outside records in raw and canonical audit data. Exclude them only from a derived Cardiff dashboard-ready view, with `verification_status=excluded` and a reason.
6. Add tests using fixed inside, outside, and boundary examples before enabling filtering.

## Records requiring manual review

Priority order:

1. **Geographic scope:** the 62 strongly outside-Cardiff candidates listed above, plus ambiguous radius-edge records such as Cardiff Airport and Aubrey Arms.
2. **Possible duplicate/co-location:** the five pairs in the duplicate table, reviewed as destination clusters rather than isolated pairs.
3. **Operational status:** all 68 missing/unknown status records, prioritising Council-correlated sites and records intended for dashboard use.
4. **Recency:** the 26 records more than five years old.
5. **Equipment granularity:** the 62 rows reporting multiple EVSEs/connectors. These are not presumed erroneous; review is needed to confirm one-row-per-physical-location aggregation.
6. **Council correlation:** the eight strong Council-name matches should be checked against current Council/operator evidence and may later qualify for `council_correlated` or `operator_source_checked` status.

## Recommended next action

Do not connect this dataset to the dashboard yet. Next, acquire and register a licensed Cardiff administrative boundary, implement a tested candidate-only geographic classifier, and produce a manual-review workbook/report containing the geographic, status, recency, and co-location candidates above. After human decisions are recorded, create a separate processed Cardiff-only location dataset with lineage back to every Open Charge Map source record. Keep the current raw JSON and canonical CSV immutable.
