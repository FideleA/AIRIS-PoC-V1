"""Structured provenance declarations for external AIRIS data and services."""

from dataclasses import dataclass
from html import escape
from typing import Iterable


ACCESS_DATE = "20 July 2026"
UNKNOWN = "Not recorded in the current repository"

FIELD_LABELS = (
    "Dataset or service name",
    "Dataset identifier",
    "Publisher",
    "Provider or data owner",
    "Source landing page",
    "Access method",
    "Specific variables used",
    "Geographic and temporal coverage",
    "Date accessed or retrieved",
    "Licence and required attribution",
    "Update frequency or dataset status",
    "Transformation performed by AIRIS",
    "Role in the PoC",
    "Known limitations",
    "Local file/version or API query reference",
)


@dataclass(frozen=True)
class ExternalLink:
    label: str
    url: str


@dataclass(frozen=True)
class SourceValue:
    text: str
    links: tuple[ExternalLink, ...] = ()


def value(text: str, *links: tuple[str, str]) -> SourceValue:
    return SourceValue(text, tuple(ExternalLink(*link) for link in links))


def _record(**fields: SourceValue) -> dict[str, SourceValue]:
    if tuple(fields) != FIELD_LABELS:
        raise ValueError("Data-source fields must use the required order")
    return fields


DATA_SOURCES = (
    _record(
        **{
            "Dataset or service name": value("Open Charge Map Cardiff-area charging locations"),
            "Dataset identifier": value("Open Charge Map API v3, /v3/poi/"),
            "Publisher": value("Open Charge Map"),
            "Provider or data owner": value(
                "Open Charge Map and the Data Provider returned for each record. The 20 July 2026 acquisition included Open Charge Map Contributors and UK National Charge Point Registry provider records."
            ),
            "Source landing page": value(
                "Open Charge Map website and API endpoint.",
                ("Open Charge Map", "https://openchargemap.org/"),
                ("API endpoint", "https://api.openchargemap.io/v3/poi/"),
            ),
            "Access method": value(
                "Authenticated HTTP GET returning JSON; Cardiff centre 51.4816, -3.1791, 15 km radius, GB, maximum 500 results."
            ),
            "Specific variables used": value(
                "Source record ID, station name and address, latitude, longitude, operator, operational status, EVSE and connector counts, maximum power, access type, usage cost, provider, source URL, source update time, licence and attribution."
            ),
            "Geographic and temporal coverage": value(
                "131 records within 15 km of central Cardiff retrieved on 20 July 2026; 66 records remained after exact Cardiff-boundary filtering. Source update dates vary by record."
            ),
            "Date accessed or retrieved": value(ACCESS_DATE),
            "Licence and required attribution": value(
                "Provider-specific. Returned records included CC BY 4.0 and Open Government Licence v2.0 terms. Credit Open Charge Map and the applicable returned Data Provider; AIRIS retains provider, licence and attribution per record.",
                ("CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/"),
                ("Open Government Licence v2.0", "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/2/"),
            ),
            "Update frequency or dataset status": value(
                "On-demand acquisition. Open Charge Map is a changing aggregated dataset; some returned records identify the historic UK National Charge Point Registry as their underlying provider. AIRIS does not describe the complete portfolio as NCR data."
            ),
            "Transformation performed by AIRIS": value(
                "Preserved raw JSON; normalised records to the AIRIS canonical schema; generated deterministic stable IDs; retained record-level provenance; flagged malformed, nearby and unknown-status records; filtered coordinates against authority W06000015; then enriched retained sites with flood and deprivation data."
            ),
            "Role in the PoC": value("Locations and descriptive attributes for the verified Cardiff charging-site portfolio."),
            "Known limitations": value(
                "Crowdsourced and imported public-charger records may be incomplete, duplicated, outdated or affected by operator and provider reporting practices. The acquisition reported five near-duplicate coordinate pairs and 68 unknown status mappings."
            ),
            "Local file/version or API query reference": value(
                "data/raw/charging/open_charge_map_cardiff_raw.json; data/raw/charging/open_charge_map_cardiff_normalised.csv; data/raw/charging/open_charge_map_quality_report.json; data/processed/cardiff_stations_verified.csv; scripts/fetch_charging_sites.py; scripts/charging_sources/open_charge_map.py."
            ),
        }
    ),
    _record(
        **{
            "Dataset or service name": value("Local Authorities - High Water mark"),
            "Dataset identifier": value("DataMapWales layer geonode:localauthorities_hwm; Cardiff authority W06000015"),
            "Publisher": value("Welsh Government / DataMapWales"),
            "Provider or data owner": value("Welsh Government / DataMapWales; derived from Ordnance Survey OpenData Boundary-Line"),
            "Source landing page": value(
                "DataMapWales catalogue and metadata record.",
                ("Catalogue", "https://datamap.gov.wales/layers/geonode%3Alocalauthorities_hwm"),
                ("Metadata", "https://datamap.gov.wales/layers/geonode%3Alocalauthorities_hwm/metadata_detail"),
            ),
            "Access method": value("Full OGC GeoPackage download from DataMapWales; source layer local_authorities_wales_hwm."),
            "Specific variables used": value("Official authority code census_cod, English and Welsh authority names, high-water-mark polygon geometry."),
            "Geographic and temporal coverage": value("22 Welsh principal local authorities; publication date 26 November 2025; Cardiff selected in EPSG:27700."),
            "Date accessed or retrieved": value(ACCESS_DATE),
            "Licence and required attribution": value(
                "Open Government Licence for Public Sector Information. Credit Welsh Government / DataMapWales and state that the product is derived from Ordnance Survey OpenData Boundary-Line.",
                ("Open Government Licence v3.0", "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"),
            ),
            "Update frequency or dataset status": value("No update frequency is recorded; source publication date 26 November 2025."),
            "Transformation performed by AIRIS": value("Selected exactly W06000015/Cardiff, validated the unsimplified two-part geometry, retained EPSG:27700 for analysis and added an EPSG:4326 display layer."),
            "Role in the PoC": value("Filters acquired charger records to Cardiff and supports Cardiff-boundary checks and geospatial preparation."),
            "Known limitations": value("High-water-mark coastline convention; the catalogue does not record a generalisation tolerance."),
            "Local file/version or API query reference": value("data/raw/boundaries/wales_local_authorities.gpkg, layer local_authorities_wales_hwm; data/processed/cardiff_boundary.gpkg, layers cardiff_boundary and cardiff_boundary_wgs84; scripts/prepare_cardiff_boundary.py; SHA-256 1FB003C30487C11620A2C16EA9F51A6E3C1A672C2BE3241393C504F95B571F00."),
        }
    ),
    _record(
        **{
            "Dataset or service name": value("Lower Layer Super Output Areas (December 2021) Boundaries EW BGC"),
            "Dataset identifier": value("DataMapWales layer geonode:lsoa_2021_w_hwm; source layer lsoa_2021_w_hwm"),
            "Publisher": value("Office for National Statistics / DataMapWales"),
            "Provider or data owner": value("Office for National Statistics; boundary geometry contains Ordnance Survey data; distributed through DataMapWales"),
            "Source landing page": value(
                "DataMapWales source plus ONS geography and licensing documentation.",
                ("DataMapWales", "https://datamap.gov.wales/layers/geonode%3Alsoa_2021_w_hwm"),
                ("ONS Open Geography", "https://www.ons.gov.uk/methodology/geography/geographicalproducts/opengeography"),
                ("ONS digital boundaries", "https://www.ons.gov.uk/methodology/geography/geographicalproducts/digitalboundaries"),
                ("ONS licensing", "https://www.ons.gov.uk/methodology/geography/licences"),
            ),
            "Access method": value("Full OGC GeoPackage download from DataMapWales."),
            "Specific variables used": value("2021 LSOA code lsoa21cd, English and Welsh names, alternative names and polygon geometry."),
            "Geographic and temporal coverage": value("Wales, December 2021 LSOAs; 2,173 polygon-part rows representing 1,917 LSOAs; EPSG:27700; source publication date 25 November 2025."),
            "Date accessed or retrieved": value(ACCESS_DATE),
            "Licence and required attribution": value(
                "Open Government Licence v3.0. Source: Office for National Statistics licensed under the Open Government Licence v.3.0. Contains OS data © Crown copyright and database right 2025.",
                ("Open Government Licence v3.0", "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"),
            ),
            "Update frequency or dataset status": value("As published; a fixed December 2021 statistical geography edition."),
            "Transformation performed by AIRIS": value("Dissolved polygon parts by official LSOA code, joined WIMD percentage data one-to-one, and selected 218 Cardiff LSOAs by more than 50% area overlap without clipping their geometry."),
            "Role in the PoC": value("Spatially matches charging-site coordinates to the LSOA used for the income-deprivation factor."),
            "Known limitations": value("The source has polygon-part rows and no local-authority code; Cardiff membership therefore uses a documented majority-area spatial rule."),
            "Local file/version or API query reference": value("data/raw/boundaries/wales_lsoa_2021.gpkg, layer lsoa_2021_w_hwm; data/processed/cardiff_lsoa_income_deprivation.gpkg; scripts/prepare_deprivation_data.py; SHA-256 CC5266EFE14D51A12E514433E92510A718D5344B29F5689493A0777EB0ED667E."),
        }
    ),
    _record(
        **{
            "Dataset or service name": value("Welsh Index of Multiple Deprivation 2025 indicator data by Lower Layer Super Output Area and local authority: income and employment domains"),
            "Dataset identifier": value("bb732e4f-689b-4f95-8d0c-12ec8c0dcfe5"),
            "Publisher": value("Welsh Government"),
            "Provider or data owner": value("Welsh Government through StatsWales; underlying income-domain inputs include DWP, HMRC, Home Office and ONS data as documented in the metadata"),
            "Source landing page": value(
                "StatsWales dataset and stable metadata record.",
                ("Dataset", "https://stats.gov.wales/en-GB/bb732e4f-689b-4f95-8d0c-12ec8c0dcfe5"),
                ("Metadata", "https://stats.gov.wales/en-GB/bb732e4f-689b-4f95-8d0c-12ec8c0dcfe5/download/metadata"),
            ),
            "Access method": value("Downloaded StatsWales CSV extract."),
            "Specific variables used": value("Indicator ‘People in income deprivation’, Data description ‘Percentage’, Area code, Area name and Data values."),
            "Geographic and temporal coverage": value("All 1,917 Welsh 2021 LSOAs; principally income-related administrative data at March 2024 and mid-2022 population estimates, as documented by StatsWales."),
            "Date accessed or retrieved": value(ACCESS_DATE),
            "Licence and required attribution": value(
                "Open Government Licence v3.0, subject to publisher-identified third-party rights. Acknowledge Welsh Government/StatsWales. © Crown copyright 2025.",
                ("Welsh Government copyright", "https://www.gov.wales/copyright-statement"),
                ("Open Government Licence v3.0", "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"),
            ),
            "Update frequency or dataset status": value("First published 27 November 2025; minor formatting update 6 February 2026; not expected to be updated or replaced."),
            "Transformation performed by AIRIS": value("Filtered exact indicator/percentage rows and valid LSOA codes; retained the published percentage unchanged as deprivation_score; joined to LSOA geography and spatially matched charger points."),
            "Role in the PoC": value("Local-deprivation factor contributing 20% of the hypothetical overall risk score."),
            "Known limitations": value("Area-level relative-deprivation measure; it does not describe an individual resident or a direct characteristic of charging equipment."),
            "Local file/version or API query reference": value("data/raw/deprivation/wimd_2025_income_employment_indicators.csv; data/processed/cardiff_lsoa_income_deprivation.gpkg; scripts/prepare_deprivation_data.py; scripts/enrich_chargers_with_deprivation.py; SHA-256 098890A8209FF0E9D5DB2F035A8AA117950C7B70DF3D7C0C22F297BF94918D26."),
        }
    ),
    _record(
        **{
            "Dataset or service name": value("Flood Risk Assessment Wales"),
            "Dataset identifier": value("DataMapWales layer group inspire-nrw:FloodRiskAssessmentWales; layer-group resource 889"),
            "Publisher": value("Natural Resources Wales"),
            "Provider or data owner": value("Natural Resources Wales, with third-party spatial-data rights identified in the official attribution statement"),
            "Source landing page": value(
                "FRAW catalogue, group metadata, applicable layer metadata and OGC services.",
                ("Catalogue", "https://datamap.gov.wales/layergroups/inspire-nrw%3AFloodRiskAssessmentWales"),
                ("Group metadata", "https://datamap.gov.wales/layergroups/inspire-nrw%3AFloodRiskAssessmentWales/metadata_detail"),
                ("River metadata", "https://datamap.gov.wales/layers/inspire-nrw%3ANRW_FLOOD_RISK_FROM_RIVERS/metadata_detail"),
                ("Sea metadata", "https://datamap.gov.wales/layers/inspire-nrw%3ANRW_FLOOD_RISK_FROM_SEA/metadata_detail"),
                ("Surface-water metadata", "https://datamap.gov.wales/layers/inspire-nrw%3ANRW_FLOOD_RISK_FROM_SURFACE_WATER_SMALL_WATERCOURSES/metadata_detail"),
                ("WFS", "https://datamap.gov.wales/capabilities/layergroup/889/?ows_service=wfs"),
                ("WMS", "https://datamap.gov.wales/capabilities/layergroup/889/?ows_service=wms"),
            ),
            "Access method": value("Downloaded national GeoPackages; indexed bounding-box reads followed by exact Cardiff-boundary intersection."),
            "Specific variables used": value("risk/Risk category, pub_date, source feature identifier where supplied, and polygon geometry for river, sea, and surface-water/small-watercourse layers."),
            "Geographic and temporal coverage": value("Wales, restricted by AIRIS to Cardiff. Catalogue release 21 May 2026; river and sea layer pub_date 21 May 2026; surface-water layer pub_date 28 November 2022."),
            "Date accessed or retrieved": value(ACCESS_DATE),
            "Licence and required attribution": value(
                "Open Government Licence v3.0. Contains Natural Resources Wales information © Natural Resources Wales and database right. All rights reserved. Some features of this information are based on digital spatial data licensed from the UK Centre for Ecology & Hydrology © UKCEH. Defra, Met Office and DARD Rivers Agency © Crown copyright. © Cranfield University. © James Hutton Institute. Contains OS data © Crown copyright and database right.",
                ("Open Government Licence v3.0", "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"),
            ),
            "Update frequency or dataset status": value("Catalogue updates. AIRIS preserves each layer’s own publication date separately from the 21 May 2026 catalogue release."),
            "Transformation performed by AIRIS": value("Prepared Cardiff subsets in EPSG:27700; spatially intersected charger points; retained High/Medium/Low source bands; assigned Very Low only where no published polygon matched; mapped bands to illustrative AIRIS values 90/65/35/10 and selected the maximum across the three sources."),
            "Role in the PoC": value("Flood-exposure factor contributing 50% of the hypothetical overall risk score."),
            "Known limitations": value("Categorised national/local model outputs rather than site-specific predictions. Resolution, assumptions and unmapped local conditions affect interpretation; Very Low does not mean no risk."),
            "Local file/version or API query reference": value("data/raw/flood/fraw_rivers.gpkg, fraw_sea.gpkg and fraw_surface_water.gpkg; data/processed/flood_rivers.gpkg, flood_sea.gpkg and flood_surface_water.gpkg; scripts/prepare_flood_layers.py; scripts/enrich_chargers_with_flood.py. Raw checksums are recorded in data/metadata/flood_data_notes.md."),
        }
    ),
    _record(
        **{
            "Dataset or service name": value("Open-Meteo Weather Forecast API"),
            "Dataset identifier": value("Open-Meteo Forecast API, endpoint /v1/forecast"),
            "Publisher": value("Open-Meteo"),
            "Provider or data owner": value("Open-Meteo, integrating model data from multiple national meteorological services; model selection may be automatic for the coordinates"),
            "Source landing page": value(
                "Provider, documentation, endpoint, licence, terms and pricing.",
                ("Open-Meteo", "https://open-meteo.com/"),
                ("API documentation", "https://open-meteo.com/en/docs"),
                ("API endpoint", "https://api.open-meteo.com/v1/forecast"),
                ("Licence", "https://open-meteo.com/en/licence"),
                ("Terms", "https://open-meteo.com/en/terms"),
                ("Pricing", "https://open-meteo.com/en/pricing"),
            ),
            "Access method": value("HTTP GET API returning JSON."),
            "Specific variables used": value("current_weather.temperature and daily.temperature_2m_max; AIRIS uses the current temperature and maximum of the first seven daily maxima."),
            "Geographic and temporal coverage": value("Coordinate-based current conditions and seven-day forecasts for existing and proposed Cardiff locations."),
            "Date accessed or retrieved": value(ACCESS_DATE),
            "Licence and required attribution": value(
                "API data under CC BY 4.0. Weather data by Open-Meteo.com; AIRIS transforms temperatures into a hypothetical risk score.",
                ("Open-Meteo", "https://open-meteo.com/"),
                ("CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/"),
            ),
            "Update frequency or dataset status": value("Continuously refreshed forecast service based on available model runs; not guaranteed real-time data."),
            "Transformation performed by AIRIS": value("Rounds coordinates to four decimals; requests current weather and seven daily maxima; converts Celsius temperatures through PoC thresholds; caches successful results for 30 minutes and retains last-known data."),
            "Role in the PoC": value("Temperature factor contributing 30% of the hypothetical overall risk score."),
            "Known limitations": value("Model-based forecasts change between runs; accuracy, availability and uninterrupted delivery are not guaranteed. The free API is rate-limited and intended for non-commercial evaluation and prototyping."),
            "Local file/version or API query reference": value("weather_service.py; endpoint https://api.open-meteo.com/v1/forecast; latitude/longitude rounded to 4 decimals; current_weather=true; daily=temperature_2m_max; forecast_days=7; timezone=Europe/London; timeout from config.py; application cache TTL 1,800 seconds."),
        }
    ),
    _record(
        **{
            "Dataset or service name": value("OpenStreetMap map tiles"),
            "Dataset identifier": value("OpenStreetMap standard tile layer used by Folium; exact tile endpoint is not recorded in the current repository"),
            "Publisher": value("OpenStreetMap contributors"),
            "Provider or data owner": value("OpenStreetMap contributors"),
            "Source landing page": value(
                "OpenStreetMap and copyright/licensing information.",
                ("OpenStreetMap", "https://www.openstreetmap.org/"),
                ("Copyright and licence", "https://www.openstreetmap.org/copyright"),
            ),
            "Access method": value("Client-side web-map tiles through Folium’s default OpenStreetMap tile configuration."),
            "Specific variables used": value("Rendered base-map image tiles and their embedded geographic context; no OpenStreetMap feature attributes enter AIRIS scoring."),
            "Geographic and temporal coverage": value("Interactive map context around Cardiff; tile content reflects the provider’s available map state."),
            "Date accessed or retrieved": value(ACCESS_DATE),
            "Licence and required attribution": value("© OpenStreetMap contributors; OpenStreetMap data are available under the Open Data Commons Open Database License."),
            "Update frequency or dataset status": value("Continuously maintained collaborative map; tile freshness is provider-dependent."),
            "Transformation performed by AIRIS": value("Folium displays the tiles beneath AIRIS charger and proposed-site overlays; tile content is not transformed into a risk input."),
            "Role in the PoC": value("Geographic display context only."),
            "Known limitations": value("Map completeness and currency vary; availability is external to AIRIS. The exact tile endpoint selected by the installed Folium version is not recorded in the repository."),
            "Local file/version or API query reference": value("app.py build_airis_map(); folium.Map default tiles; config.py MAP_ATTRIBUTION. Exact tile endpoint: Not recorded in the current repository."),
        }
    ),
)


NRW_ATTRIBUTION_TEXT = (
    "Contains Natural Resources Wales information © Natural Resources Wales and "
    "database right. All rights reserved. Some features of this information are "
    "based on digital spatial data licensed from the UK Centre for Ecology & "
    "Hydrology © UKCEH. Defra, Met Office and DARD Rivers Agency © Crown "
    "copyright. © Cranfield University. © James Hutton Institute. Contains OS "
    "data © Crown copyright and database right."
)

ATTRIBUTIONS = (
    value(
        "Charging locations: Open Charge Map and the applicable record-level Data Provider; retain the provider-specific licence and attribution. The acquisition included CC BY 4.0 and Open Government Licence v2.0 records.",
        ("Open Charge Map", "https://openchargemap.org/"),
        ("CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/"),
        ("Open Government Licence v2.0", "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/2/"),
    ),
    value(
        "Cardiff administrative boundary: Welsh Government / DataMapWales; derived from Ordnance Survey OpenData Boundary-Line.",
        ("DataMapWales catalogue", "https://datamap.gov.wales/layers/geonode%3Alocalauthorities_hwm"),
    ),
    value(NRW_ATTRIBUTION_TEXT, ("Open Government Licence v3.0", "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/")),
    value("Source: Welsh Government, Welsh Index of Multiple Deprivation 2025 indicator data, licensed under the Open Government Licence v3.0. © Crown copyright 2025.", ("StatsWales dataset", "https://stats.gov.wales/en-GB/bb732e4f-689b-4f95-8d0c-12ec8c0dcfe5")),
    value("Source: Office for National Statistics licensed under the Open Government Licence v.3.0. Contains OS data © Crown copyright and database right 2025.", ("ONS licensing", "https://www.ons.gov.uk/methodology/geography/licences")),
    value("Weather data by Open-Meteo.com, licensed under CC BY 4.0.", ("Open-Meteo", "https://open-meteo.com/"), ("CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/")),
    value("Map tiles: © OpenStreetMap contributors.", ("OpenStreetMap copyright", "https://www.openstreetmap.org/copyright")),
)


def render_value_html(source_value: SourceValue) -> str:
    rendered = escape(source_value.text).replace("\n", "<br>")
    if source_value.links:
        links = " · ".join(
            f'<a href="{escape(link.url, quote=True)}" target="_blank" '
            f'rel="noopener noreferrer">{escape(link.label)}</a>'
            for link in source_value.links
        )
        rendered = f"{rendered}<br>{links}"
    return rendered


def external_urls(records: Iterable[dict[str, SourceValue]] = DATA_SOURCES) -> tuple[str, ...]:
    return tuple(
        link.url
        for record in records
        for source_value in record.values()
        for link in source_value.links
    )
