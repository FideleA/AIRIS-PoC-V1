import streamlit as st
import folium
from streamlit_folium import st_folium
import geopandas as gpd
import pandas as pd
from datetime import datetime, timezone
from html import escape
import threading
import time
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
from portfolio_assessments import baseline_assessments_for_stations
from scoring import compute_scores
from weather_service import (
    FORECAST_DAYS,
    fetch_open_meteo,
    rounded_coordinates,
    WeatherServiceError,
)


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
ASSESSMENT_STATE_KEY = "airis_site_assessments"
SELECTED_STATION_KEY = "airis_selected_station"
LAST_WEATHER_REFRESH_KEY = "airis_last_weather_refresh"
PENDING_SELECTED_ASSESSMENT_KEY = "airis_pending_selected_assessment"
WEATHER_CACHE_TTL_SECONDS = 1800
WEATHER_CACHE_MAX_ENTRIES = 256
WEATHER_REFRESH_THROTTLE_SECONDS = 60
INTRODUCTORY_DESCRIPTION = (
    "This proof of concept calculates current and seven-day forecast risk "
    "scores for EV charging stations in Cardiff, based on only three factors: "
    "flood exposure, temperature and local deprivation."
)
HOW_TO_USE_ANCHOR = "how-to-use-this-dashboard"
SCORE_CALCULATION_NOTE = (
    "Score calculation: Overall risk score = 50% flood exposure + 30% "
    "temperature + 20% local deprivation. These weights are hypothetical and "
    "used for demonstration in this proof of concept."
)


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
        "weather_status": weather.get("weather_status", "live"),
        "weather_retrieved_at": weather.get("retrieved_at"),
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


@st.cache_resource
def weather_runtime_store() -> dict:
    return {
        "lock": threading.RLock(),
        "last_known": {},
    }


@st.cache_data(
    ttl=WEATHER_CACHE_TTL_SECONDS,
    max_entries=WEATHER_CACHE_MAX_ENTRIES,
    show_spinner=False,
)
def _cached_provider_weather(
    latitude: float,
    longitude: float,
    forecast_days: int = FORECAST_DAYS,
) -> dict:
    """Cache both successes and failures so reruns cannot create retry storms."""
    try:
        result = fetch_open_meteo(
            latitude,
            longitude,
            forecast_days=forecast_days,
        )
        return {**result, "weather_status": "live"}
    except WeatherServiceError as e:
        return {
            "error": str(e),
            "error_kind": e.kind,
            "status_code": e.status_code,
            "retry_after_seconds": e.retry_after_seconds,
            "weather_status": "unavailable",
        }


def _weather_age_seconds(weather: dict) -> float | None:
    try:
        retrieved = datetime.fromisoformat(
            str(weather["retrieved_at"]).replace("Z", "+00:00")
        )
        return max(0.0, (datetime.now(timezone.utc) - retrieved).total_seconds())
    except (KeyError, TypeError, ValueError):
        return None


def cached_weather(
    lat: float,
    lon: float,
    *,
    force_refresh: bool = False,
    forecast_days: int = FORECAST_DAYS,
) -> dict:
    latitude, longitude = rounded_coordinates(lat, lon)
    cache_key = (latitude, longitude, int(forecast_days))
    store = weather_runtime_store()

    with store["lock"]:
        last_known = store["last_known"].get(cache_key)
        last_known = dict(last_known) if last_known else None
    if (
        not force_refresh
        and last_known
        and (_weather_age_seconds(last_known) or 0) < WEATHER_CACHE_TTL_SECONDS
    ):
        return {**last_known, "weather_status": "cached"}

    if force_refresh:
        try:
            result = fetch_open_meteo(
                latitude,
                longitude,
                forecast_days=forecast_days,
            )
            result = {**result, "weather_status": "live"}
        except WeatherServiceError as error:
            result = {
                "error": str(error),
                "error_kind": error.kind,
                "status_code": error.status_code,
                "retry_after_seconds": error.retry_after_seconds,
                "weather_status": "unavailable",
            }
    else:
        result = _cached_provider_weather(latitude, longitude, int(forecast_days))

    if not result.get("error"):
        with store["lock"]:
            store["last_known"][cache_key] = dict(result)
        return result

    if last_known:
        return {
            **last_known,
            "weather_status": "last-known",
            "weather_warning": result["error"],
            "error_kind": result.get("error_kind"),
            "status_code": result.get("status_code"),
        }
    return result


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


def format_popup(
    station,
    current_res,
    forecast_res,
    weather_err=None,
    weather=None,
):
    lines = [f"<b>{station_selector_label(station)}</b>"]
    if weather_err:
        lines.append(f"<i>Weather error: {weather_err}</i>")
    if current_res:
        band_display = display_band(current_res['risk_band'])
        lines.append(f"Score: {float(current_res['overall_score']):.1f}")
        lines.append(f"Risk: {band_display}")
        calculated_at = current_res.get("calculated_at")
        if calculated_at:
            lines.append(
                f"Last calculated: {escape(format_london_timestamp(calculated_at))}"
            )
    else:
        lines.append("Score unavailable")
        lines.append("No stored assessment")
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
    fit_bounds_locations: list[tuple[float, float]] | None = None,
) -> folium.Map:
    """Build the shared charger and temporary-scenario map."""
    scenarios = scenarios or []
    map_object = folium.Map(
        location=CARDIFF_CENTER,
        zoom_start=CARDIFF_ZOOM,
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
                    result.get("weather"),
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


def render_airis_map(map_object: folium.Map):
    """Render a display-oriented map without returning Leaflet interactions."""
    return st_folium(
        map_object,
        height=500,
        key=MAP_COMPONENT_KEY,
        returned_objects=[],
        use_container_width=True,
    )


def station_result_by_id(results: list[dict], station_id: str) -> dict | None:
    """Resolve the dropdown-selected station; map clicks are not selection inputs."""
    return next(
        (
            result
            for result in results
            if str(result["station_id"]) == str(station_id)
        ),
        None,
    )


def compute_site_scores_safe(station, *, force_refresh: bool = False):
    lat = station["latitude"]
    lon = station["longitude"]
    weather = (
        cached_weather(lat, lon, force_refresh=True)
        if force_refresh
        else cached_weather(lat, lon)
    )
    if weather.get("error"):
        return None, None, weather.get("error"), weather
    try:
        cur = compute_scores(station["flood_score"], weather["current_temperature_c"], station["deprivation_score"])
        forecast_temp = weather["seven_day_max_temperature_c"]
        fcast = compute_scores(station["flood_score"], forecast_temp, station["deprivation_score"])
        return cur, fcast, None, weather
    except Exception as e:
        return None, None, str(e), weather


def retain_stored_assessment_on_failure(
    refreshed: tuple,
    stored: tuple | None,
) -> tuple:
    if refreshed[0] is not None or not stored or stored[0] is None:
        return refreshed
    _, _, error, failed_weather = refreshed
    current, forecast, _, stored_weather = stored
    fallback_weather = {
        **(stored_weather or {}),
        "weather_status": "stored",
        "weather_warning": error,
        "error_kind": (failed_weather or {}).get("error_kind"),
        "status_code": (failed_weather or {}).get("status_code"),
    }
    return current, forecast, None, fallback_weather


def queue_selected_site_assessment() -> None:
    st.session_state[PENDING_SELECTED_ASSESSMENT_KEY] = True


def site_result_record(station, assessment: tuple | None = None) -> dict:
    current, forecast, error, weather = assessment or (None, None, None, None)
    return {
        "station_id": station["station_id"],
        "current": current,
        "forecast": forecast,
        "error": error,
        "row": station,
        "weather": weather,
    }


def results_from_stored_assessments(
    stations: pd.DataFrame,
    assessments: dict[str, tuple],
) -> list[dict]:
    """Build portfolio/map inputs without making live provider requests."""
    return [
        site_result_record(
            row,
            assessments.get(str(row["station_id"])),
        )
        for _, row in stations.iterrows()
    ]


def weather_availability_message(weather: dict | None) -> str:
    kind = (weather or {}).get("error_kind")
    if kind == "rate_limit":
        return (
            "Live weather is temporarily rate-limited. AIRIS will use the most "
            "recent available weather data where possible."
        )
    if kind == "timeout":
        return "Live weather timed out. Please try again later."
    if kind == "provider_5xx":
        return "The live weather provider is temporarily unavailable."
    return "Live weather is temporarily unavailable for this location."


def weather_status_label(weather: dict) -> str:
    return {
        "live": "Live",
        "cached": "Cached",
        "last-known": "Last-known",
        "stored": "Stored",
    }.get(str(weather.get("weather_status")), "Unavailable")


def render_dashboard_intro():
    st.markdown(INTRODUCTORY_DESCRIPTION)
    st.markdown(
        f'<a href="#{HOW_TO_USE_ANCHOR}">How to use this site</a>',
        unsafe_allow_html=True,
    )


def render_dashboard_guide():
    st.markdown(
        f'<div id="{HOW_TO_USE_ANCHOR}"></div>',
        unsafe_allow_html=True,
    )
    with st.expander("How to use this dashboard", expanded=True):
        st.markdown(
            """
1. **Explore the map**

   Zoom, pan and hover over a charging station to view its name and latest
   stored risk score.

2. **Select a station**

   Choose an existing charging station from the list to see its current and
   seven-day forecast risk assessment.

3. **Review the results**

   Check the overall risk score, risk category and the contribution of flood
   exposure, temperature and local deprivation.

4. **Assess a proposed site**

   Enter the site’s latitude and longitude, then use the sliders to set its
   local deprivation and flood-exposure values. Temperature is retrieved
   automatically from the site coordinates using current and forecast weather
   data.
            """
        )
        st.caption(SCORE_CALCULATION_NOTE)


def main():
    st.title("AIRIS Cardiff PoC Dashboard")
    render_dashboard_intro()
    st.subheader("EV charging-site risk intelligence — research demonstrator")
    st.info(f"**Active data mode: {dataset_mode_label(DATA_MODE)}**")
    render_dashboard_guide()

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
    baseline_assessments = baseline_assessments_for_stations(stations, DATA_MODE)
    if ASSESSMENT_STATE_KEY not in st.session_state:
        st.session_state[ASSESSMENT_STATE_KEY] = dict(baseline_assessments)
    station_ids = stations["station_id"].astype(str).tolist()
    if st.session_state.get(SELECTED_STATION_KEY) not in station_ids:
        st.session_state[SELECTED_STATION_KEY] = station_ids[0]
    scenarios = st.session_state[PROPOSAL_STATE_KEY]
    assessments = st.session_state[ASSESSMENT_STATE_KEY]
    for station_id, assessment in baseline_assessments.items():
        assessments.setdefault(station_id, assessment)

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

    # Initial rendering uses the persistent baseline and makes no weather request.
    selected_station_id = str(st.session_state[SELECTED_STATION_KEY])
    selected_station = stations.loc[
        stations["station_id"].astype(str) == selected_station_id
    ].iloc[0]
    if st.session_state.pop(PENDING_SELECTED_ASSESSMENT_KEY, False):
        refreshed = compute_site_scores_safe(selected_station)
        assessments[selected_station_id] = retain_stored_assessment_on_failure(
            refreshed,
            assessments.get(selected_station_id),
        )

    # All other map and portfolio inputs use previously stored assessments.
    results = results_from_stored_assessments(stations, assessments)

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
            key=SELECTED_STATION_KEY,
            on_change=queue_selected_site_assessment,
        )
        sel = station_result_by_id(results, sid)
        if sel:
            if sel["error"]:
                st.warning(weather_availability_message(sel.get("weather")))
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
                    st.caption(
                        f"Weather result: {weather_status_label(weather)}"
                    )
                    if weather.get("weather_warning"):
                        st.warning(weather_availability_message(weather))
                # temperatures
                if weather and 'current_temperature_c' in weather:
                    st.write(f"Current temperature: {format_temperature(weather.get('current_temperature_c'))}")
                if weather and 'forecast_max_temperature_c' in weather:
                    st.write(f"Maximum seven-day forecast temperature: {format_temperature(weather.get('seven_day_max_temperature_c'))}")
                # contribution chart (weighted point contributions)
                render_contribution_chart(score_contributions(cur))
            else:
                st.info(
                    "A current assessment is temporarily unavailable because live "
                    "weather could not be retrieved and no earlier result is stored."
                )
            refresh_disabled = (
                time.monotonic()
                - float(st.session_state.get(LAST_WEATHER_REFRESH_KEY, 0.0))
                < WEATHER_REFRESH_THROTTLE_SECONDS
            )
            if st.button(
                "Refresh weather",
                key="refresh_selected_weather",
                disabled=refresh_disabled,
                help="Refresh is limited to once per minute.",
            ):
                st.session_state[LAST_WEATHER_REFRESH_KEY] = time.monotonic()
                refreshed = compute_site_scores_safe(
                    sel["row"],
                    force_refresh=True,
                )
                assessments[str(sid)] = retain_stored_assessment_on_failure(
                    refreshed,
                    assessments.get(str(sid)),
                )
                st.rerun()
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
                    st.warning(weather_availability_message(weather))
                    st.write(
                        "The scenario was not added. Previously added scenarios "
                        "remain available."
                    )
                else:
                    if weather.get("weather_warning"):
                        st.warning(weather_availability_message(weather))
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
                if selected_scenario.get("weather_retrieved_at"):
                    st.caption(
                        "Weather retrieved "
                        f"{format_london_timestamp(selected_scenario['weather_retrieved_at'])} "
                        f"({str(selected_scenario.get('weather_status', 'live')).title()})."
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
        st.caption(
            "Map colours use the latest stored assessment. Select a site for "
            "current and forecast detail."
        )
        st.button(
            "Reset map view",
            key="reset_airis_map_view",
            help="Restore the configured Cardiff centre and default zoom.",
        )
        render_airis_map(
            build_airis_map(
                results,
                selected_station_id=sid,
                scenarios=scenarios,
            )
        )

    # Footer disclaimer and attribution
    st.markdown("---")
    st.caption("This is an illustrative research PoC. It does not predict claims, calculate premiums or automate underwriting.")
    with st.expander("Data attribution and licences"):
        for statement in attribution_statements(DATA_MODE):
            st.caption(statement)

if __name__ == '__main__':
    main()
