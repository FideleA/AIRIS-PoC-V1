# Cardiff flood-enrichment quality review

Review date: 2026-07-20

## Scope and outcome

This review covers `cardiff_charging_sites_flood_enriched.csv`, `cardiff_charging_sites_flood_unresolved.csv`, and `cardiff_flood_enrichment_report.json`. It does not reclassify, remove, or otherwise change any charger record.

All 66 input chargers are present in the enriched output in their original order. All 66 have status `enriched`; the unresolved output contains its header only and no records. The JSON report reconciles with both CSV files.

The enrichment is suitable for commit as a reviewed pipeline milestone, provided it is committed with the preparation scripts, tests, `flood_data_notes.md`, and `data_source_register.csv`. Manual map checks listed below remain advisable before the flood result is exposed in the dashboard or used operationally.

## Classification summary

“No mapped match” means `No mapped Low, Medium or High classification matched.` It must not be described as no flood risk.

| Hazard source | No mapped match | Low | Medium | High | Total |
|---|---:|---:|---:|---:|---:|
| Rivers | 52 | 12 | 2 | 0 | 66 |
| Sea | 51 | 14 | 1 | 0 | 66 |
| Surface water and small watercourses | 62 | 3 | 0 | 1 | 66 |

Overall illustrative flood-score distribution:

| Flood score | Chargers |
|---:|---:|
| 0 | 45 |
| 35 | 18 |
| 65 | 2 |
| 90 | 1 |

These values are illustrative AIRIS transformations, not official Natural Resources Wales scores.

## Multiple-hazard matches

Twelve sites match classified polygons from more than one hazard source. No site matches more than one polygon within the same hazard source in this output.

| Station ID | Site | Postcode | River | Sea | Surface water | Score | Dominant source |
|---|---|---|---|---|---|---:|---|
| `airis_18512e9f2cb48402a38f` | Stallcourt Avenue - Cardiff | CF23 5AN | Medium | Medium | No mapped match | 65 | river and sea |
| `airis_5ea17c642133289def43` | Victoria Park Road - Cardiff | CF5 1EZ | Medium | Low | No mapped match | 65 | river |
| `airis_046f7aff802305a339e7` | NCP Dumfries Place | CF10 3FN | No mapped match | Low | Low | 35 | sea and surface water |
| `airis_2750ce20495a08e07ec8` | Rennie Street | CF11 6EG | Low | Low | No mapped match | 35 | river and sea |
| `airis_3729d40d75c6d2eecb5d` | Severn Road Car Park | CF11 9DX | Low | Low | No mapped match | 35 | river and sea |
| `airis_39b94fd4816ab150bff0` | MFG Texaco Ninian | CF11 8BN | Low | Low | No mapped match | 35 | river and sea |
| `airis_63004a6b9ce8784bad0f` | Butleigh Avenue - Cardiff | CF5 1AP | Low | No mapped match | Low | 35 | river and surface water |
| `airis_67b9d9f5c7480b12a7ed` | Mardy Street | CF11 6RD | Low | Low | No mapped match | 35 | river and sea |
| `airis_95801a2e85a43c20b2c7` | Redlaver Street | CF117YL | Low | Low | No mapped match | 35 | river and sea |
| `airis_aa4c211c5a940b4c1b62` | IKEA Cardiff | CF11 0JR | Low | Low | No mapped match | 35 | river and sea |
| `airis_d560a303a4821d0f562e` | Sophia Gardens | CF11 9HW | Low | Low | No mapped match | 35 | river and sea |
| `airis_fbe76f33818eb3334d19` | NCP Pellet Street | CF10 4FF | No mapped match | Low | Low | 35 | sea and surface water |

## Highest score

One site receives the highest observed score of 90:

| Station ID | Site | Postcode | Classification | Coordinates | Nearest relevant edge |
|---|---|---|---|---|---:|
| `airis_3c050a8dc19efac7c748` | Tesco Superstore - St Mellons | CF3 0EF | Surface-water High | 51.524697, -3.103711 | 0.92 m |

The point is very close to the surface-water polygon edge and therefore requires manual map verification. Its classification was not changed during this review.

## Score-zero sites

The following 45 sites receive score 0 because no published Low, Medium, or High polygon matched for any of the three hazards:

| Station ID | Site | Postcode | Coordinates |
|---|---|---|---|
| `airis_ddc3489e654f03c05faf` | ASDA Cardiff Coryton Supercentre | CF14 7EW | 51.524136, -3.242433 |
| `airis_b3f8c8a32ad90052f6c8` | Anglesey Street - Cardiff | CF5 1QZ | 51.483130, -3.207070 |
| `airis_d6e6a24b96376ba9af96` | Britannia Quay | CF10 4PB | 51.464363, -3.160242 |
| `airis_166a187eab7cb6059083` | Bute Crescent | CF10 5AN | 51.464247, -3.164985 |
| `airis_b226d245101e1c918414` | Cardiff & Vale University Health Board | CF14 4HH | 51.520046, -3.194338 |
| `airis_0175f0f6390e84ca0eb6` | Castle Mews, Cardiff | CF10 3EW | 51.485120, -3.182573 |
| `airis_f536b167fad74e6cf2f2` | College Road, Cardiff | CF14 2HJ | 51.502182, -3.220884 |
| `airis_3aae53b1edc64850567b` | DRAX00165 | CF10 4RT | 51.473010, -3.166070 |
| `airis_0866395be71fb88857e7` | DRAX00238 | CF10 4BE | 51.476720, -3.167550 |
| `airis_0328717e3cea0ac1806f` | EVC Holiday Inn Express Cardiff | CF10 4EE | 51.472444, -3.164669 |
| `airis_5bce80e842998aee7c52` | Harvey Street | CF5 1QW | 51.482240, -3.205278 |
| `airis_d508e2db52a6b7675cbb` | Howard Place | CF24 0DE | 51.483999, -3.166333 |
| `airis_0ece004f3926dd3d2f6a` | Ibis Budget Cardiff | CF10 4BE | 51.476021, -3.168791 |
| `airis_0235119709426a653f5d` | InstaVolt Bannatyne Health Club & Spa | CF14 5DU | 51.524217, -3.191804 |
| `airis_fc45ad043e668a3af5cd` | King Edward Vii Avenue | CF10 3NB | 51.488436, -3.183733 |
| `airis_9e9134ddd9469563ea57` | Llandaff High Street Car Park | CF5 2DX | 51.494256, -3.218335 |
| `airis_92d27599db462d7026d2` | Maindy Road | CF24 4HQ | 51.492650, -3.183810 |
| `airis_88cdc81bc33622080fcd` | Moto Cardiff West Services | CF72 8SA | 51.508914, -3.306853 |
| `airis_6f88afdff062e0a132fc` | NCP Dumfries Place | CF10 3FN | 51.484554, -3.172682 |
| `airis_9965ba6bb8a4717a281d` | NCP Dumfries Place | CF10 3FN | 51.484352, -3.172482 |
| `airis_0ed5376b3910e85bcdda` | NCP Greyfriars Road | CF10 3AD | 51.483101, -3.175770 |
| `airis_e087bdf6460b769e5d24` | North Road | CF10 3DY | 51.490523, -3.188036 |
| `airis_081d317754d82aaf4090` | Park Place | CF10 3RL | 51.485936, -3.176613 |
| `airis_9b167f8cea08206be6ba` | Penlline Road, Cardiff | CF14 2AA | 51.514429, -3.220649 |
| `airis_80b9188bc22f7f019c5e` | Q-Park Cardiff Bay | CF10 4PH | 51.465801, -3.162500 |
| `airis_741d2cdef1b829a900ac` | Spire Cardiff Hospital | CF23 8XL | 51.530775, -3.141247 |
| `airis_32723c6ba4bd541dbc1f` | St David's Dewi Sant Shopping Centre | CF10 2EQ | 51.478574, -3.174714 |
| `airis_0335f6a8946af5ec92c5` | St David's Shopping Centre | CF10 2EQ | 51.479103, -3.174819 |
| `airis_3937d5c1246b2b3ccff2` | St Davids Shopping Centre Car Park | CF10 2EQ | 51.479366, -3.173753 |
| `airis_3a9e8f8f09cb7adc2b8d` | St Davids Shopping Centre Car Park | CF10 2EQ | 51.479340, -3.173709 |
| `airis_ebc43ac93e04c395c139` | St. David's Shopping Centre Car Park | CF10 2EQ | 51.479220, -3.174768 |
| `airis_4d49c406033a4ff3973f` | Star Hub | CF24 2SJ | 51.484894, -3.143337 |
| `airis_eea2a83d1e9d0e395e8a` | Tesla Cardiff | CF23 8HE | 51.531497, -3.139771 |
| `airis_86396a3ef80877186baa` | Tewkesbury Place | CF24 4QF | 51.500260, -3.178055 |
| `airis_19a85544f2b3ea7fb9ce` | Three Arches | CF14 4HS | 51.519434, -3.180886 |
| `airis_dd426e6fa2b075eb051d` | Turning Head Car Park - Cardiff | CF11 9QJ | 51.489150, -3.203600 |
| `airis_1bba313e22632283295f` | Ty Glas Road | CF14 5EB | 51.525150, -3.202318 |
| `airis_b8ca386746aa48913e8f` | UK Steel Enterprise Cardiff | CF24 5BS | 51.476339, -3.154874 |
| `airis_f0782529b5ad354d2a05` | University of Wales Hospital | CF14 4XW | 51.505910, -3.187410 |
| `airis_d178685f83cabc1f02c7` | Voco St David's Hotel | cf10 5sd | 51.460517, -3.167412 |
| `airis_70f3cdfed60f400050fd` | Waterloo Road - Cardiff | CF23 5DX | 51.496550, -3.156630 |
| `airis_11034ffdcd8f35310fd9` | Welcome Break Cardiff Gate Services | CF23 8RA | 51.539266, -3.129829 |
| `airis_096a150517372b2a668d` | Wessex Garages Cardiff | CF11 8AQ | 51.468083, -3.206283 |
| `airis_775500559e0cad784837` | Wessex Garages Cardiff | CF11 8AQ | 51.466549, -3.201704 |
| `airis_33ebf06eb2009e555419` | Windsor Place | CF10 3BZ | 51.483881, -3.173242 |

## Unresolved and invalid records

There are no unresolved records, invalid coordinates, unknown risk bands, incomplete match results, or deleted input records. The unresolved CSV is intentionally empty but retains the full header schema.

## Polygon-edge sensitivity

For review only, charger points and polygon edges were compared in EPSG:27700. A site is listed as close when its point lies within 25 metres of the nearest High, Medium, or Low polygon boundary from any hazard source. This diagnostic does not change its classification. Thirty-three sites meet the threshold:

| Station ID | Site | Distance | Nearest hazard edge | Score |
|---|---|---:|---|---:|
| `airis_fc45ad043e668a3af5cd` | King Edward Vii Avenue | 0.58 m | surface water | 0 |
| `airis_1d4ddbd2f7e280d34542` | Penylan Library Car Park - Cardiff | 0.69 m | surface water | 35 |
| `airis_18512e9f2cb48402a38f` | Stallcourt Avenue - Cardiff | 0.73 m | sea | 65 |
| `airis_63004a6b9ce8784bad0f` | Butleigh Avenue - Cardiff | 0.90 m | surface water | 35 |
| `airis_3c050a8dc19efac7c748` | Tesco Superstore - St Mellons | 0.92 m | surface water | 90 |
| `airis_5ea17c642133289def43` | Victoria Park Road - Cardiff | 1.29 m | surface water | 65 |
| `airis_0175f0f6390e84ca0eb6` | Castle Mews, Cardiff | 1.92 m | surface water | 0 |
| `airis_d178685f83cabc1f02c7` | Voco St David's Hotel | 2.18 m | sea | 0 |
| `airis_dd426e6fa2b075eb051d` | Turning Head Car Park - Cardiff | 2.29 m | river | 0 |
| `airis_f886fc76be7c3a77022f` | Bettws Lane Car Park, Newport | 3.41 m | sea | 35 |
| `airis_166a187eab7cb6059083` | Bute Crescent | 3.43 m | sea | 0 |
| `airis_d560a303a4821d0f562e` | Sophia Gardens | 3.93 m | surface water | 35 |
| `airis_046f7aff802305a339e7` | NCP Dumfries Place | 5.67 m | surface water | 35 |
| `airis_3729d40d75c6d2eecb5d` | Severn Road Car Park | 6.21 m | sea | 35 |
| `airis_9965ba6bb8a4717a281d` | NCP Dumfries Place | 7.09 m | surface water | 0 |
| `airis_9f8cf84028bb4c8a1ace` | Pontcanna Street | 7.63 m | river | 35 |
| `airis_5bce80e842998aee7c52` | Harvey Street | 7.87 m | river | 0 |
| `airis_6f88afdff062e0a132fc` | NCP Dumfries Place | 8.00 m | surface water | 0 |
| `airis_84a7701983c186cbe3af` | Tesco Extra-Cardiff | 8.33 m | surface water | 35 |
| `airis_1bba313e22632283295f` | Ty Glas Road | 9.32 m | surface water | 0 |
| `airis_39b94fd4816ab150bff0` | MFG Texaco Ninian | 9.77 m | sea | 35 |
| `airis_fbe76f33818eb3334d19` | NCP Pellet Street | 9.80 m | surface water | 35 |
| `airis_0866395be71fb88857e7` | DRAX00238 | 12.66 m | sea | 0 |
| `airis_d6e6a24b96376ba9af96` | Britannia Quay | 12.93 m | sea | 0 |
| `airis_0328717e3cea0ac1806f` | EVC Holiday Inn Express Cardiff | 13.44 m | surface water | 0 |
| `airis_8de65bb0720d6c78e1fb` | Kyveilog Street | 14.46 m | surface water | 35 |
| `airis_3aae53b1edc64850567b` | DRAX00165 | 15.83 m | surface water | 0 |
| `airis_f536b167fad74e6cf2f2` | College Road, Cardiff | 17.78 m | river | 0 |
| `airis_11034ffdcd8f35310fd9` | Welcome Break Cardiff Gate Services | 20.78 m | surface water | 0 |
| `airis_92d27599db462d7026d2` | Maindy Road | 21.08 m | surface water | 0 |
| `airis_b3f8c8a32ad90052f6c8` | Anglesey Street - Cardiff | 22.52 m | surface water | 0 |
| `airis_0ece004f3926dd3d2f6a` | Ibis Budget Cardiff | 23.35 m | surface water | 0 |
| `airis_67b9d9f5c7480b12a7ed` | Mardy Street | 24.75 m | surface water | 35 |

## Unusual or potentially implausible records

No flood match is demonstrably impossible from the supplied data, but the following deserve manual inspection:

- `airis_f886fc76be7c3a77022f` is named **Bettws Lane Car Park, Newport**, despite a Cardiff postcode and coordinates inside the Cardiff boundary. Its Low sea match is only 3.41 m from the polygon edge. This appears to be a charging-source naming/location issue, not an enrichment calculation error.
- Three records are named **NCP Dumfries Place**. One (`airis_046f7aff802305a339e7`) is several hundred metres from the other two and receives Low sea and surface-water matches, while the other two score 0. Their distinct coordinates may be legitimate source records, but the common name warrants map verification.
- Several St David's Shopping Centre records have closely related names and nearby coordinates. They all score 0; this is primarily a charging-location deduplication question and does not invalidate the flood match.
- The sole High site and both Medium-score sites are within 1.29 m of at least one polygon edge. Small source-coordinate or map-resolution differences could affect their point-in-polygon result.
- `airis_d178685f83cabc1f02c7` (Voco St David's Hotel) scores 0 but is only 2.18 m from a sea polygon edge. This is valid under the current point geometry but sensitive enough for visual confirmation.

No automatic correction or reclassification has been applied.

## Provenance review

Provenance is complete for the reviewed workflow:

- all 66 rows contain the same non-empty `flood_data_version`;
- the version records FRAW catalogue date `2026-05-21`;
- it retains river and sea layer dates `2026-05-21` and surface-water layer date `2022-11-28`;
- it includes the SHA-256 checksum of every prepared source layer;
- all rows share one enrichment timestamp;
- original charger identifiers and provider provenance remain present;
- the NRW licence and full attribution are retained in `flood_data_notes.md`, `data_source_register.csv`, and the prepared flood layers.

The enriched CSV and JSON report do not duplicate the complete licence and attribution text. They should therefore be distributed and committed together with the companion metadata rather than as standalone files.

## Manual map-verification sample

Selection intentionally overlaps categories where a site satisfies more than one rule.

### All High-band sites

- `airis_3c050a8dc19efac7c748` — Tesco Superstore - St Mellons — surface-water High — score 90.

### All multi-hazard sites

- `airis_18512e9f2cb48402a38f` — Stallcourt Avenue - Cardiff.
- `airis_5ea17c642133289def43` — Victoria Park Road - Cardiff.
- `airis_046f7aff802305a339e7` — NCP Dumfries Place.
- `airis_2750ce20495a08e07ec8` — Rennie Street.
- `airis_3729d40d75c6d2eecb5d` — Severn Road Car Park.
- `airis_39b94fd4816ab150bff0` — MFG Texaco Ninian.
- `airis_63004a6b9ce8784bad0f` — Butleigh Avenue - Cardiff.
- `airis_67b9d9f5c7480b12a7ed` — Mardy Street.
- `airis_95801a2e85a43c20b2c7` — Redlaver Street.
- `airis_aa4c211c5a940b4c1b62` — IKEA Cardiff.
- `airis_d560a303a4821d0f562e` — Sophia Gardens.
- `airis_fbe76f33818eb3334d19` — NCP Pellet Street.

### Medium-band sites

Only two Medium-score sites exist, so five cannot be selected without inventing or duplicating records. Both available sites are selected:

- `airis_18512e9f2cb48402a38f` — Stallcourt Avenue - Cardiff — river Medium and sea Medium.
- `airis_5ea17c642133289def43` — Victoria Park Road - Cardiff — river Medium and sea Low.

### Five Low-band sites

Selected by proximity to a polygon edge:

- `airis_1d4ddbd2f7e280d34542` — Penylan Library Car Park - Cardiff — river Low.
- `airis_63004a6b9ce8784bad0f` — Butleigh Avenue - Cardiff — river and surface-water Low.
- `airis_f886fc76be7c3a77022f` — Bettws Lane Car Park, Newport — sea Low.
- `airis_d560a303a4821d0f562e` — Sophia Gardens — river and sea Low.
- `airis_046f7aff802305a339e7` — NCP Dumfries Place — sea and surface-water Low.

### Five score-zero sites

Selected as the five score-zero points nearest a mapped polygon edge:

- `airis_fc45ad043e668a3af5cd` — King Edward Vii Avenue — 0.58 m from a surface-water edge.
- `airis_0175f0f6390e84ca0eb6` — Castle Mews, Cardiff — 1.92 m from a surface-water edge.
- `airis_d178685f83cabc1f02c7` — Voco St David's Hotel — 2.18 m from a sea edge.
- `airis_dd426e6fa2b075eb051d` — Turning Head Car Park - Cardiff — 2.29 m from a river edge.
- `airis_166a187eab7cb6059083` — Bute Crescent — 3.43 m from a sea edge.

### Unresolved sites

None.

## Recommendation

The enrichment is **ready to commit as a quality-reviewed, non-dashboard pipeline milestone**. The counts reconcile, no record is unresolved or missing, classifications use only confirmed bands, tied hazards are retained, and provenance is traceable. Commit readiness does not imply operational validation: complete the selected manual map checks before connecting these results to Streamlit or using them for decisions.
