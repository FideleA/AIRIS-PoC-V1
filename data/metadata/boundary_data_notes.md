# Cardiff boundary data notes

## Source

- Dataset: Local Authorities - High Water mark
- Provider: Welsh Government / DataMapWales
- Source product: derived from Ordnance Survey OpenData Boundary-Line
- Publication date: 2025-11-26
- Downloaded file: `data/raw/boundaries/wales_local_authorities.gpkg`
- Source layer: `local_authorities_wales_hwm`
- Source CRS: EPSG:27700 (OSGB 1936 / British National Grid)
- Licence: Open Government Licence for Public Sector Information
- Attribution: Welsh Government / DataMapWales; derived from Ordnance Survey OpenData Boundary-Line

The dataset contains 22 Welsh principal local authorities. It follows the high-water-mark coastline convention. The catalogue does not state a generalisation tolerance; the detailed source is retained without simplification and must not be described as a formally verified “full-resolution” edition unless additional source metadata confirms that classification.

## Reproducing the raw download

1. Open the DataMapWales catalogue record at <https://datamap.gov.wales/layers/geonode%3Alocalauthorities_hwm>.
2. Choose **Download** and select the **OGC GeoPackage** format without applying a spatial subset or transforming the source data.
3. Save the downloaded file as `data/raw/boundaries/wales_local_authorities.gpkg`.
4. Confirm that it contains the layer `local_authorities_wales_hwm` in EPSG:27700.
5. Verify the file with `Get-FileHash -Algorithm SHA256 data/raw/boundaries/wales_local_authorities.gpkg`.

Expected SHA-256 for the acquisition made on 2026-07-20:

```text
1FB003C30487C11620A2C16EA9F51A6E3C1A672C2BE3241393C504F95B571F00
```

The checksum identifies the exact source used for the current processed boundary. A later publisher revision may legitimately differ and must be reviewed and recorded before replacement.

## Exact Cardiff selection

The preparation script selects the official authority code exactly:

```python
boundaries["census_cod"].astype("string").eq("W06000015")
```

The selected record must also have the exact English name `Cardiff`. The verified Welsh name is `Caerdydd`. If the official code field is unavailable in a compatible future source, the only permitted fallback is exact equality on `name_en == "Cardiff"`; substring and fuzzy matching are prohibited. Zero or multiple matches cause preparation to fail.

## Geometry handling

The selected Cardiff source geometry is a valid two-part `MultiPolygon`. It required no repair. The preparation code checks validity before output and does not simplify, buffer, clip, dissolve with another feature, or otherwise adjust the administrative boundary.

For a future invalid source geometry only, the documented repair is Shapely `make_valid`, followed by extraction and union of polygonal parts. Preparation fails if repair yields no polygonal geometry or remains invalid. The output records whether repair occurred in `geometry_repaired`; the current value is `false`.

## Processed output

`data/processed/cardiff_boundary.gpkg` contains:

- `cardiff_boundary`: authoritative prepared geometry in EPSG:27700;
- `cardiff_boundary_wgs84`: coordinate-transformed copy in EPSG:4326 for web-map display.

Both layers contain exactly one feature and preserve authority code, English name, Welsh name, source dataset, source publication date, licence, attribution, coastline convention, and repair status. Coordinate transformation does not change the intended administrative boundary. The projected layer remains the reference geometry for spatial analysis; the WGS84 layer is provided for display interoperability.
