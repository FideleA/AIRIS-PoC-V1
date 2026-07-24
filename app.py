import streamlit as st
import folium
from streamlit_folium import st_folium
import geopandas as gpd
import pandas as pd
from datetime import datetime, timezone
from html import escape
from typing import Optional
from uuid import uuid4
from zoneinfo import ZoneInfo
from shapely.geometry import Point

import altair as alt

from config import (
    BASE_DIR, CARDIFF_CENTER, CARDIFF_ZOOM, MODEL_VERSION, WEIGHTS, RISK_BANDS,
    TEMPERATURE_THRESHOLDS, DATA_MODE, DATA_MODE_LABELS,
    OPEN_CHARGE_MAP_ATTRIBUTION, NRW_ATTRIBUTION, WIMD_ATTRIBUTION,
    ONS_OS_ATTRIBUTION, STATWALES_PROVIDER_STATEMENT, MAP_ATTRIBUTION,
    WEATHER_ATTRIBUTION,
)
from data_loader import load_stations
from scoring import compute_scores
from weather_service import fetch_open_meteo, WeatherServiceError


st.set_page_config(page_title="AIRIS Cardiff PoC Dashboard", layout="wide")

FORECAST_INCREASE_THRESHOLD = 5.0
VERIFIED_DATASET_NAME = "AIRIS verified Cardiff charging locations"
CARDIFF_SCENARIO_BOUNDS = {
    "latitude": (51.3, 51.7),
    "longitude": (-3.5, -2.9),
}
PROPOSAL_STATE_KEY = "airis_proposed_scenarios"
PROCESSED_SUBMISSIONS_KEY = "airis_processed_proposal_submissions"
NEXT_SCENARIO_NUMBER_KEY = "airis_next_proposal_number"
CARDIFF_BOUNDARY_PATH = BASE_DIR / "data" / "processed" / "cardiff_boundary.gpkg"
MAP_COMPONENT_KEY = "airis_shared_map"
MAP_CENTER_LAT_KEY = "map_center_lat"
MAP_CENTER_LON_KEY = "map_center_lon"
MAP_ZOOM_KEY = "map_zoom"
MAP_INITIALISED_KEY = "map_initialised"
MAP_VIEW_TOLERANCE = 1e-6


@st.cache_data
def get_stations(data_mode: str) -> pd.DataFrame:
    return load_stations(mode=data_mode)


def dataset_mode_label(data_mode: str) -> str:
    return DATA_MODE_LABELS[data_mode]


def attribution_statements(data_mode: str) -> list[str]:
    statements = [WEATHER_ATTRIBUTION, MAP_ATTRIBUTION]
    if data_mode == "verified":
        statements = [
            OPEN_CHARGE_MAP_ATTRIBUTION,
            NRW_ATTRIBUTION,
            STATWALES_PROVIDER_STATEMENT,
            WIMD_ATTRIBUTION,
            ONS_OS_ATTRIBUTION,
            *statements,
        ]
    return statements


def verified_site_details(station) -> list[tuple[str, object]]:
    fields = [
        ("Technical station ID", "station_id"),
        ("Operator", "operator_name"),
        ("Operational status", "operational_status"),
        ("Source provider", "data_provider"),
        ("Source last updated", "source_last_updated"),
        ("River flood band", "flood_river_band"),
        ("Sea flood band", "flood_sea_band"),
        ("Surface-water flood band", "flood_surface_water_band"),
        ("Dominant flood source", "flood_dominant_source"),
        ("LSOA", "lsoa_name"),
        ("Income-deprivation percentage", "income_deprivation_percentage"),
        ("Enrichment timestamp", "enrichment_timestamp"),
        ("Dataset version", "dataset_version"),
    ]
    details = []
    for label, field in fields:
        value = station.get(field)
        if value is not None and not pd.isna(value) and str(value).strip():
            if field in {"source_last_updated", "enrichment_timestamp"}:
                value = format_london_timestamp(value)
            details.append((label, value))
    return details


def format_london_timestamp(value: object) -> str:
    """Format an ISO timestamp for concise display in Europe/London."""
    try:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("UTC")
        local = timestamp.tz_convert(ZoneInfo("Europe/London"))
    except (TypeError, ValueError, OverflowError):
        return str(value)
    return f"{local.day} {local.strftime('%B %Y, %H:%M %Z')}"


def station_selector_label(station) -> str:
    """Return a readable station label without exposing its technical ID."""
    name = str(station.get("station_name", "Station")).strip() or "Station"
    operator = station.get("operator_name")
    postcode = station.get("postcode")
    if operator is not None and not pd.isna(operator) and str(operator).strip():
        qualifier = str(operator).strip()
    elif postcode is not None and not pd.isna(postcode) and str(postcode).strip():
        qualifier = str(postcode).strip()
    else:
        qualifier = ""
    return f"{name} — {qualifier}" if qualifier else name


def score_contributions(score_result: dict) -> dict[str, float]:
    """Return the exact weighted values shared by charts and overall scoring."""
    return {
        "Flood exposure": score_result["flood_contribution"],
        "Temperature": score_result["temperature_contribution"],
        "Income deprivation": score_result["deprivation_contribution"],
    }


def forecast_score_increase(current: dict, forecast: dict) -> float:
    return round(
        float(forecast["overall_score"]) - float(current["overall_score"]), 1
    )


def valid_global_coordinates(latitude: object, longitude: object) -> bool:
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError):
        return False
    return pd.notna(lat) and pd.notna(lon) and -90 <= lat <= 90 and -180 <= lon <= 180


@st.cache_resource
def cardiff_boundary_geometry():
    """Load the prepared official boundary for scenario warnings."""
    try:
        boundary = gpd.read_file(CARDIFF_BOUNDARY_PATH, layer="cardiff_boundary")
        if boundary.empty or boundary.crs is None:
            return None
        return boundary.to_crs("EPSG:4326").geometry.union_all()
    except Exception:
        return None


def coordinates_within_cardiff(
    latitude: object,
    longitude: object,
    boundary_geometry=None,
) -> bool:
    if not valid_global_coordinates(latitude, longitude):
        return False
    lat, lon = float(latitude), float(longitude)
    geometry = (
        boundary_geometry
        if boundary_geometry is not None
        else cardiff_boundary_geometry()
    )
    if geometry is not None:
        return bool(geometry.covers(Point(lon, lat)))
    return (
        CARDIFF_SCENARIO_BOUNDS["latitude"][0]
        <= lat
        <= CARDIFF_SCENARIO_BOUNDS["latitude"][1]
        and CARDIFF_SCENARIO_BOUNDS["longitude"][0]
        <= lon
        <= CARDIFF_SCENARIO_BOUNDS["longitude"][1]
    )


def next_scenario_number(scenarios: list[dict]) -> int:
    used = {
        int(scenario["scenario_id"])
        for scenario in scenarios
        if str(scenario.get("scenario_id", "")).isdigit()
    }
    return max(used, default=0) + 1


def build_scenario_record(
    scenarios: list[dict],
    latitude: object,
    longitude: object,
    flood_score: object,
    deprivation_score: object,
    weather: dict,
    name: str = "",
    created_at: str | None = None,
    scenario_number: int | None = None,
) -> dict:
    if not valid_global_coordinates(latitude, longitude):
        raise ValueError("Latitude must be between -90 and 90 and longitude between -180 and 180.")
    if weather.get("error"):
        raise ValueError(str(weather["error"]))
    number = scenario_number or next_scenario_number(scenarios)
    default_label = f"Proposed Site {number}"
    display_name = str(name).strip() or default_label
    current = compute_scores(flood_score, weather["current_temperature_c"], deprivation_score)
    forecast = compute_scores(
        flood_score, weather["seven_day_max_temperature_c"], deprivation_score
    )
    return {
        "scenario_id": str(number),
        "label": default_label,
        "name": display_name,
        "latitude": float(latitude),
        "longitude": float(longitude),
        "flood_score": float(flood_score),
        "temperature_risk_current": float(current["temperature_score"]),
        "temperature_risk_forecast": float(forecast["temperature_score"]),
        "deprivation_score": float(deprivation_score),
        "flood_contribution_current": float(current["flood_contribution"]),
        "temperature_contribution_current": float(
            current["temperature_contribution"]
        ),
        "deprivation_contribution_current": float(
            current["deprivation_contribution"]
        ),
        "current_overall_score": float(current["overall_score"]),
        "forecast_overall_score": float(forecast["overall_score"]),
        "current_temperature_c": float(weather["current_temperature_c"]),
        "forecast_temperature_c": float(weather["seven_day_max_temperature_c"]),
        "current_score": float(current["overall_score"]),
        "forecast_score": float(forecast["overall_score"]),
        "current_category": current["risk_band"],
        "forecast_category": forecast["risk_band"],
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
    }


def add_scenario_once(
    scenarios: list[dict],
    processed_submission_ids: set[str],
    scenario: dict,
    submission_id: str,
) -> bool:
    """Add one scenario once; a rerun with the same submission ID is ignored."""
    if submission_id in processed_submission_ids:
        return False
    scenarios.append(scenario)
    processed_submission_ids.add(submission_id)
    return True


def remove_scenario(scenarios: list[dict], scenario_id: str) -> bool:
    for index, scenario in enumerate(scenarios):
        if str(scenario.get("scenario_id")) == str(scenario_id):
            scenarios.pop(index)
            return True
    return False


def clear_scenarios(scenarios: list[dict]) -> None:
    scenarios.clear()


def scenario_comparison_table(scenarios: list[dict]) -> pd.DataFrame:
    rows = []
    for scenario in scenarios:
        rows.append(
            {
                "Site": scenario["name"],
                "Latitude": round(float(scenario["latitude"]), 6),
                "Longitude": round(float(scenario["longitude"]), 6),
                "Current score": round(float(scenario["current_score"]), 1),
                "Forecast score": round(float(scenario["forecast_score"]), 1),
                "Change": round(
                    float(scenario["forecast_score"])
                    - float(scenario["current_score"]),
                    1,
                ),
                "Current risk": display_band(scenario["current_category"]),
                "Forecast risk": display_band(scenario["forecast_category"]),
            }
        )
    return pd.DataFrame(rows)


def portfolio_metrics(results: list[dict]) -> dict[str, object]:
    """Calculate verified/sample portfolio metrics; scenarios are never inputs."""
    valid = [result for result in results if result["current"] is not None]
    average = (
        round(sum(item["current"]["overall_score"] for item in valid) / len(valid), 2)
        if valid
        else None
    )
    return {
        "sites_mapped": len(results),
        "average_current": average,
        "high_risk_count": sum(
            1 for item in valid if item["current"]["risk_band"] in ("high", "very_high")
        ),
        "forecast_increase_count": sum(
            1
            for item in valid
            if item["forecast"]
            and forecast_score_increase(item["current"], item["forecast"])
            > FORECAST_INCREASE_THRESHOLD
        ),
    }


def truncate_map_label(name: object, limit: int = 36) -> str:
    text = str(name).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def initialise_map_state(state) -> None:
    if state.get(MAP_INITIALISED_KEY):
        return
    state[MAP_CENTER_LAT_KEY] = float(CARDIFF_CENTER[0])
    state[MAP_CENTER_LON_KEY] = float(CARDIFF_CENTER[1])
    state[MAP_ZOOM_KEY] = int(CARDIFF_ZOOM)
    state[MAP_INITIALISED_KEY] = True


def reset_map_view(state) -> None:
    state[MAP_CENTER_LAT_KEY] = float(CARDIFF_CENTER[0])
    state[MAP_CENTER_LON_KEY] = float(CARDIFF_CENTER[1])
    state[MAP_ZOOM_KEY] = int(CARDIFF_ZOOM)
    state[MAP_INITIALISED_KEY] = True


def update_map_view(state, returned_map_state: dict | None) -> bool:
    """Persist a materially changed Leaflet view without causing another rerun."""
    if not returned_map_state:
        return False
    changed = False
    center = returned_map_state.get("center")
    if isinstance(center, dict) and {"lat", "lng"} <= center.keys():
        candidate = {"lat": float(center["lat"]), "lng": float(center["lng"])}
        if (
            -90 <= candidate["lat"] <= 90
            and -180 <= candidate["lng"] <= 180
            and (
                abs(candidate["lat"] - float(state[MAP_CENTER_LAT_KEY]))
                > MAP_VIEW_TOLERANCE
                or abs(candidate["lng"] - float(state[MAP_CENTER_LON_KEY]))
                > MAP_VIEW_TOLERANCE
            )
        ):
            state[MAP_CENTER_LAT_KEY] = candidate["lat"]
            state[MAP_CENTER_LON_KEY] = candidate["lng"]
            changed = True
    zoom = returned_map_state.get("zoom")
    try:
        candidate_zoom = float(zoom)
    except (TypeError, ValueError):
        candidate_zoom = None
    if (
        candidate_zoom is not None
        and 0 <= candidate_zoom <= 22
        and abs(candidate_zoom - float(state[MAP_ZOOM_KEY])) > MAP_VIEW_TOLERANCE
    ):
        state[MAP_ZOOM_KEY] = candidate_zoom
        changed = True
    return changed


@st.cache_data(ttl=1800)
def cached_weather(lat: float, lon: float) -> dict:
    try:
        return fetch_open_meteo(lat, lon)
    except WeatherServiceError as e:
        return {"error": str(e)}


def risk_color(band: Optional[str]) -> str:
    return {
        "very_low": "green",
        "low": "lightgreen",
        "medium": "orange",
        "Moderate": "orange",
        "high": "red",
        "very_high": "darkred",
    }.get(band, "gray")


def display_band(band: Optional[str]) -> str:
    if not band:
        return "Unknown"
    # Map internal band to friendly label
    if band == "very_low":
        label = "Very low"
    elif band == "low":
        label = "Low"
    elif band == "medium":
        label = "Moderate"
    elif band == "high":
        label = "High"
    elif band == "very_high":
        label = "Very high"
    else:
        label = band.replace("_", " ").title()
    return f"{label} risk"


def format_temperature(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.1f} °C"
    except Exception:
        return "N/A"


def format_score(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.1f} / 100"
    except Exception:
        return "N/A"


def describe_score_change(current_score: float, forecast_score: float) -> str:
    """Return the existing user-facing description for a forecast score change."""
    delta = round(float(forecast_score) - float(current_score), 1)
    if abs(delta) < 1e-9:
        return "No change"
    if delta > 0:
        return f"Increase: +{delta:.1f} points"
    return f"Decrease: {delta:.1f} points"


def build_contribution_chart(contrib_df: pd.DataFrame) -> alt.Chart:
    return alt.Chart(contrib_df).mark_bar().encode(
        x=alt.X('contribution:Q', axis=alt.Axis(title=None)),
        y=alt.Y(
            'factor:N',
            sort=alt.SortField('contribution', order='descending'),
            axis=alt.Axis(title=None, labelAngle=0),
        ),
        tooltip=[
            alt.Tooltip('factor:N', title='Factor'),
            alt.Tooltip('contribution:Q', title='Contribution', format='.1f'),
        ],
    ).properties(title='Contribution to current overall score')


def contribution_dataframe(contributions: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "factor": list(contributions.keys()),
            "contribution": [float(value) for value in contributions.values()],
        }
    ).sort_values("contribution", ascending=False, ignore_index=True)


def scenario_current_contributions(scenario: dict) -> dict[str, float]:
    return {
        "Flood exposure": float(scenario["flood_contribution_current"]),
        "Income deprivation": float(scenario["deprivation_contribution_current"]),
        "Temperature": float(scenario["temperature_contribution_current"]),
    }


def render_contribution_chart(contributions: dict[str, float]) -> None:
    contrib_df = contribution_dataframe(contributions)
    chart = build_contribution_chart(contrib_df)
    labels = chart.mark_text(
        align="left",
        baseline="middle",
        dx=5,
    ).encode(text=alt.Text("contribution:Q", format=".1f"))
    st.altair_chart((chart + labels), width="stretch")
    st.caption("Weighted contributions sum to the overall score.")


def format_popup(station, current_res, forecast_res, weather_err=None):
    lines = [f"<b>{station_selector_label(station)}</b>"]
    if weather_err:
        lines.append(f"<i>Weather error: {weather_err}</i>")
    if current_res:
        band_display = display_band(current_res['risk_band'])
        lines.append(f"Current score: {current_res['overall_score']} ({band_display})")
    else:
        lines.append("Current score: N/A")
    if forecast_res:
        band_display = display_band(forecast_res['risk_band'])
        lines.append(f"Forecast score: {forecast_res['overall_score']} ({band_display})")
    else:
        lines.append("Forecast score: N/A")
    return "<br>".join(lines)


def build_airis_map(
    results: list[dict],
    selected_station_id: str | None = None,
    scenarios: list[dict] | None = None,
    center: dict | None = None,
    zoom: float | None = None,
    fit_bounds_locations: list[tuple[float, float]] | None = None,
) -> folium.Map:
    """Build the shared charger and temporary-scenario map."""
    scenarios = scenarios or []
    center = center or {"lat": CARDIFF_CENTER[0], "lng": CARDIFF_CENTER[1]}
    map_object = folium.Map(
        location=(float(center["lat"]), float(center["lng"])),
        zoom_start=float(CARDIFF_ZOOM if zoom is None else zoom),
    )
    for result in results:
        row = result["row"]
        latitude, longitude = float(row["latitude"]), float(row["longitude"])
        current = result["current"]
        band = current["risk_band"] if current else None
        color = risk_color(band)
        full_name = str(row["station_name"])
        folium.CircleMarker(
            location=(latitude, longitude),
            radius=6,
            color=color,
            fill=True,
            fill_color=color,
            tooltip=folium.Tooltip(escape(full_name), sticky=True),
            popup=folium.Popup(
                format_popup(
                    row,
                    current,
                    result["forecast"],
                    result["error"],
                ),
                max_width=300,
            ),
        ).add_to(map_object)
        if str(row["station_id"]) == str(selected_station_id):
            folium.CircleMarker(
                location=(latitude, longitude),
                radius=10,
                color="#111827",
                weight=3,
                fill=False,
                tooltip=folium.Tooltip(
                    escape(truncate_map_label(full_name)),
                    permanent=True,
                    direction="top",
                    offset=(0, -8),
                ),
            ).add_to(map_object)

    for scenario in scenarios:
        latitude = float(scenario["latitude"])
        longitude = float(scenario["longitude"])
        popup_lines = [
            f"<b>{escape(scenario['label'])}</b>",
            f"Name: {escape(scenario['name'])}",
            f"Latitude: {latitude:.6f}",
            f"Longitude: {longitude:.6f}",
            f"Current score: {float(scenario['current_score']):.1f}",
            f"Forecast score: {float(scenario['forecast_score']):.1f}",
            f"Current risk category: {escape(display_band(scenario['current_category']))}",
            f"Forecast risk category: {escape(display_band(scenario['forecast_category']))}",
            f"Manual flood score: {float(scenario['flood_score']):.1f}",
            f"Manual deprivation score: {float(scenario['deprivation_score']):.1f}",
            "Flood and deprivation values are manually supplied scenario inputs.",
        ]
        folium.Marker(
            location=(latitude, longitude),
            tooltip=folium.Tooltip(escape(scenario["label"]), sticky=True),
            popup=folium.Popup("<br>".join(popup_lines), max_width=340),
            icon=folium.Icon(color="purple", icon="star", prefix="fa"),
        ).add_to(map_object)

    if fit_bounds_locations:
        map_object.fit_bounds(fit_bounds_locations, padding=(25, 25))

    legend_html = """
     <div style="position: fixed; bottom: 45px; left: 45px; width:190px;
                 background:white; border:1px solid #999; padding:7px;
                 z-index:9999; font-size:12px; line-height:1.45;">
       <b>Map legend</b><br>
       <span style="color:green;">●</span><span style="color:orange;">●</span><span style="color:red;">●</span>
       Verified charger (risk colour)<br>
       <span style="color:#111827;">◯</span> Selected verified charger<br>
       <span style="color:#7e22ce;">★</span> Proposed scenario site
     </div>
    """
    map_object.get_root().html.add_child(folium.Element(legend_html))
    return map_object


def compute_site_scores_safe(station):
    lat = station["latitude"]
    lon = station["longitude"]
    weather = cached_weather(lat, lon)
    if weather.get("error"):
        return None, None, weather.get("error"), weather
    try:
        cur = compute_scores(station["flood_score"], weather["current_temperature_c"], station["deprivation_score"])
        forecast_temp = weather["seven_day_max_temperature_c"]
        fcast = compute_scores(station["flood_score"], forecast_temp, station["deprivation_score"])
        return cur, fcast, None, weather
    except Exception as e:
        return None, None, str(e), weather


def main():
    st.title("AIRIS Cardiff PoC Dashboard")
    st.subheader("EV charging-site risk intelligence — research demonstrator")
    st.info(f"**Active data mode: {dataset_mode_label(DATA_MODE)}**")

    try:
        stations = get_stations(DATA_MODE)
    except ValueError as err:
        st.error(f"Failed to load station data: {err}")
        return

    if PROPOSAL_STATE_KEY not in st.session_state:
        st.session_state[PROPOSAL_STATE_KEY] = []
    if PROCESSED_SUBMISSIONS_KEY not in st.session_state:
        st.session_state[PROCESSED_SUBMISSIONS_KEY] = set()
    if NEXT_SCENARIO_NUMBER_KEY not in st.session_state:
        st.session_state[NEXT_SCENARIO_NUMBER_KEY] = 1
    initialise_map_state(st.session_state)
    scenarios = st.session_state[PROPOSAL_STATE_KEY]

    # Sidebar simplified
    with st.sidebar:
        st.markdown("**Factor weights**")
        st.write(f"Flood exposure: {int(WEIGHTS.get('flood',0)*100)}%")
        st.write(f"Temperature: {int(WEIGHTS.get('temperature',0)*100)}%")
        st.write(f"Income deprivation: {int(WEIGHTS.get('deprivation',0)*100)}%")
        st.markdown("**Limitations**")
        st.info("This is an illustrative research PoC. It does not predict claims, calculate premiums, or automate underwriting.")
        with st.expander('Model and scoring'):
            st.write(f"Model version: {MODEL_VERSION}")
            st.write("Scoring method: weighted additive model")
            st.write("Score range: 0–100")
            st.write("Forecast horizon: 7 days")
        with st.expander('Data sources'):
            st.write(f"Active station dataset: {dataset_mode_label(DATA_MODE)}")
            if DATA_MODE == "verified":
                st.caption(
                    "Public-source and geospatially enriched does not mean guaranteed, "
                    "certified, complete, or fully authoritative."
                )
                st.write("Open Charge Map")
                st.write("Natural Resources Wales — Flood Risk Assessment Wales")
                st.write("Welsh Government / StatsWales — WIMD 2025")
                st.write("Office for National Statistics and Ordnance Survey")
            st.write("OpenStreetMap")
            st.write("Open-Meteo")

    # Compute scores for all stations (with graceful handling)
    results = []
    errors = []
    for _, row in stations.iterrows():
        cur, fcast, err, weather = compute_site_scores_safe(row)
        results.append({"station_id": row["station_id"], "current": cur, "forecast": fcast, "error": err, "row": row, "weather": weather})
        if err:
            errors.append((row["station_id"], err))

    metrics = portfolio_metrics(results)

    # Top metrics
    metric_columns = st.columns(5 if scenarios else 4)
    c1, c2, c3, c4 = metric_columns[:4]
    c1.metric("Sites mapped", metrics["sites_mapped"])
    c2.metric(
        "Average current risk score",
        format_score(metrics["average_current"])
        if metrics["average_current"] is not None
        else "N/A",
    )
    c3.metric(
        "High-risk sites",
        metrics["high_risk_count"],
        help=f"High-risk threshold: {RISK_BANDS['high'][0]}+",
    )
    c4.metric(
        "Sites with forecast score increase >5",
        metrics["forecast_increase_count"],
        help=(
            "Count of sites where forecast overall score exceeds current overall "
            "score by more than 5 points. Forecast scoring uses the maximum "
            "temperature in the seven-day horizon as a conservative scenario."
        ),
    )
    if scenarios:
        metric_columns[4].metric("Proposed scenarios", len(scenarios))

    map_placeholder = st.empty()

    # Right-hand panels: selected site and proposed site
    sel_col, prop_col = st.columns(2)

    with sel_col:
        st.header("Selected site")
        station_by_id = {r['station_id']: r['row'] for r in results}
        sid = st.selectbox(
            "Select station",
            options=stations["station_id"].tolist(),
            format_func=lambda station_id: station_selector_label(
                station_by_id[station_id]
            ),
        )
        sel = next((r for r in results if r["station_id"] == sid), None)
        if sel:
            if sel["error"]:
                st.warning(f"Weather error for selected site: {sel['error']}")
            cur = sel["current"]
            fcast = sel["forecast"]
            weather = sel.get('weather')
            if cur:
                # show current and forecast as side-by-side metric cards
                mcur, mfcast = st.columns(2)
                mcur.metric("Current score", format_score(cur['overall_score']))
                # display category beneath current score (no arrow)
                mcur.write(display_band(cur['risk_band']))
                if fcast:
                    delta = forecast_score_increase(cur, fcast)
                    if abs(delta) < 1e-9:
                        mfcast.metric("Forecast score", format_score(fcast['overall_score']))
                        mfcast.write(describe_score_change(cur['overall_score'], fcast['overall_score']))
                    else:
                        mfcast.metric("Forecast score", format_score(fcast['overall_score']), delta=delta)
                else:
                    mfcast.metric("Forecast score", "N/A")
                # traceability cue
                if weather and weather.get('retrieved_at'):
                    st.write(
                        f"Calculated using model {MODEL_VERSION} and weather retrieved "
                        f"at {format_london_timestamp(weather['retrieved_at'])}."
                    )
                # temperatures
                if weather and 'current_temperature_c' in weather:
                    st.write(f"Current temperature: {format_temperature(weather.get('current_temperature_c'))}")
                if weather and 'forecast_max_temperature_c' in weather:
                    st.write(f"Maximum seven-day forecast temperature: {format_temperature(weather.get('seven_day_max_temperature_c'))}")
                # contribution chart (weighted point contributions)
                render_contribution_chart(score_contributions(cur))
            else:
                st.write("Current score: N/A")
            # assessment details
            with st.expander('Assessment details', expanded=False):
                st.write(f"Data mode: {dataset_mode_label(DATA_MODE)}")
                if DATA_MODE == "sample":
                    st.write("Dataset: AIRIS demonstrative PoC station data")
                else:
                    st.write(f"Dataset: {VERIFIED_DATASET_NAME}")
                    st.write(f"Dataset version: {sel['row'].get('dataset_version', 'N/A')}")
                    st.write(
                        "Enrichment date: "
                        f"{format_london_timestamp(sel['row'].get('enrichment_timestamp'))}"
                    )
                    st.caption(
                        "Public-source data are enriched for this research PoC and are "
                        "not guaranteed, certified, or fully authoritative."
                    )
                    for label, value in verified_site_details(sel["row"]):
                        if label == "Income-deprivation percentage":
                            try:
                                value = f"{float(value):.1f}%"
                            except (TypeError, ValueError):
                                pass
                        st.write(f"{label}: {value}")
                st.write("Weather provider: Open-Meteo")
                if cur:
                    st.write(f"Model version: {cur['model_version']}")
                    st.write(f"Calculated at: {cur['calculated_at']}")
                st.write("Forecast horizon: 7 days")

    with prop_col:
        st.header("Proposed site")
        proposal_number = st.session_state[NEXT_SCENARIO_NUMBER_KEY]
        proposal_label = f"Proposed Site {proposal_number}"
        proposal_name = st.text_input(
            "Optional proposed-site name",
            value=proposal_label,
            key=f"proposal_name_{proposal_number}",
        )
        lat = st.number_input("Latitude", value=float(CARDIFF_CENTER[0]))
        lon = st.number_input("Longitude", value=float(CARDIFF_CENTER[1]))
        st.caption("For proposed sites, flood and deprivation scores are manually entered. Arbitrary coordinates are not geospatially matched by this dashboard.")
        pflood = st.slider("Manually entered flood exposure score", 0, 100, 50, help="Illustrative standardised score (0–100)")
        pdep = st.slider("Manually entered income deprivation score", 0, 100, 50, help="Illustrative standardised score (0–100)")
        if valid_global_coordinates(lat, lon) and not coordinates_within_cardiff(lat, lon):
            st.warning(
                "These coordinates are outside the Cardiff scenario bounds. "
                "They may still be assessed and displayed as a temporary scenario."
            )
        if st.button("Assess and add to map", type="primary"):
            if not valid_global_coordinates(lat, lon):
                st.error(
                    "Latitude must be between -90 and 90 and longitude between "
                    "-180 and 180."
                )
            else:
                weather = cached_weather(lat, lon)
                if weather.get("error"):
                    st.warning(f"Weather error: {weather['error']}")
                    st.write(
                        "The scenario was not added. Previously added scenarios "
                        "remain available."
                    )
                else:
                    scenario = build_scenario_record(
                        scenarios,
                        lat,
                        lon,
                        pflood,
                        pdep,
                        weather,
                        name=proposal_name,
                        scenario_number=proposal_number,
                    )
                    added = add_scenario_once(
                        scenarios,
                        st.session_state[PROCESSED_SUBMISSIONS_KEY],
                        scenario,
                        submission_id=str(uuid4()),
                    )
                    if added:
                        st.session_state[NEXT_SCENARIO_NUMBER_KEY] += 1

        if scenarios:
            st.markdown("**Scenario management**")
            scenario_by_id = {
                str(scenario["scenario_id"]): scenario for scenario in scenarios
            }
            selected_scenario_id = st.selectbox(
                "Select proposed scenario",
                options=list(scenario_by_id),
                format_func=lambda scenario_id: (
                    f"{scenario_by_id[scenario_id]['label']} — "
                    f"{scenario_by_id[scenario_id]['name']}"
                ),
            )
            remove_col, clear_col = st.columns(2)
            if remove_col.button("Remove selected proposed site"):
                remove_scenario(scenarios, selected_scenario_id)
            confirm_clear = clear_col.checkbox("Confirm clear all")
            if clear_col.button("Clear all proposed sites", disabled=not confirm_clear):
                clear_scenarios(scenarios)

            if scenarios:
                st.dataframe(
                    scenario_comparison_table(scenarios),
                    hide_index=True,
                    width="stretch",
                )
            selected_scenario = next(
                (
                    scenario
                    for scenario in scenarios
                    if str(scenario["scenario_id"]) == selected_scenario_id
                ),
                None,
            )
            if selected_scenario is None:
                selected_scenario = scenarios[0] if scenarios else None
            if selected_scenario is not None:
                st.markdown(f"**{selected_scenario['name']} assessment**")
                pc1, pc2 = st.columns(2)
                pc1.metric(
                    "Current score",
                    format_score(selected_scenario["current_score"]),
                )
                pc1.write(display_band(selected_scenario["current_category"]))
                scenario_delta = round(
                    selected_scenario["forecast_score"]
                    - selected_scenario["current_score"],
                    1,
                )
                if abs(scenario_delta) < 1e-9:
                    pc2.metric(
                        "Forecast score",
                        format_score(selected_scenario["forecast_score"]),
                    )
                    pc2.write("No change")
                else:
                    pc2.metric(
                        "Forecast score",
                        format_score(selected_scenario["forecast_score"]),
                        delta=scenario_delta,
                    )
                st.write(
                    "Current temperature: "
                    f"{format_temperature(selected_scenario['current_temperature_c'])}"
                )
                st.write(
                    "Maximum seven-day forecast temperature: "
                    f"{format_temperature(selected_scenario['forecast_temperature_c'])}"
                )
                render_contribution_chart(
                    scenario_current_contributions(selected_scenario)
                )
                st.caption(
                    "Flood and income-deprivation scores are manually supplied "
                    "scenario inputs. This temporary scenario is not a verified "
                    "charging location."
                )

    with map_placeholder.container():
        if st.button("Reset map view", key="reset_airis_map_view"):
            reset_map_view(st.session_state)
        returned_map_state = st_folium(
            build_airis_map(
                results,
                selected_station_id=sid,
                scenarios=scenarios,
                center={
                    "lat": st.session_state[MAP_CENTER_LAT_KEY],
                    "lng": st.session_state[MAP_CENTER_LON_KEY],
                },
                zoom=st.session_state[MAP_ZOOM_KEY],
            ),
            width="100%",
            height=500,
            key=MAP_COMPONENT_KEY,
            returned_objects=("center", "zoom"),
        )
        update_map_view(st.session_state, returned_map_state)

    # Footer disclaimer and attribution
    st.markdown("---")
    st.caption("This is an illustrative research PoC. It does not predict claims, calculate premiums or automate underwriting.")
    with st.expander("Data attribution and licences"):
        for statement in attribution_statements(DATA_MODE):
            st.caption(statement)


if __name__ == '__main__':
    main()
