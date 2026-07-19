import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
from typing import Optional

import altair as alt

from config import CARDIFF_CENTER, CARDIFF_ZOOM, MODEL_VERSION, WEIGHTS, RISK_BANDS, TEMPERATURE_THRESHOLDS
from data_loader import load_stations
from scoring import compute_scores
from weather_service import fetch_open_meteo, WeatherServiceError


st.set_page_config(page_title="AIRIS Cardiff PoC Dashboard", layout="wide")


@st.cache_data
def get_stations() -> pd.DataFrame:
    return load_stations()


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


def format_popup(station, current_res, forecast_res, weather_err=None):
    lines = [f"<b>{station['station_name']} — {station['station_id']}</b>"]
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


def compute_site_scores_safe(station):
    lat = station["latitude"]
    lon = station["longitude"]
    weather = cached_weather(lat, lon)
    if weather.get("error"):
        return None, None, weather.get("error"), weather
    try:
        cur = compute_scores(station["flood_score"], weather["current_temperature_c"], station["deprivation_score"])
        # use first forecast day's max
        forecast_temp = weather["forecast_max_temperature_c"][0]
        fcast = compute_scores(station["flood_score"], forecast_temp, station["deprivation_score"])
        return cur, fcast, None, weather
    except Exception as e:
        return None, None, str(e), weather


def main():
    st.title("AIRIS Cardiff PoC Dashboard")
    st.subheader("EV charging-site risk intelligence — research demonstrator")

    try:
        stations = get_stations()
    except ValueError as err:
        st.error(f"Failed to load station data: {err}")
        return

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
            st.write('Station sample data: demonstrative only')
            st.write('Weather: Open-Meteo; Map tiles: OpenStreetMap contributors')

    # Compute scores for all stations (with graceful handling)
    results = []
    errors = []
    for _, row in stations.iterrows():
        cur, fcast, err, weather = compute_site_scores_safe(row)
        results.append({"station_id": row["station_id"], "current": cur, "forecast": fcast, "error": err, "row": row, "weather": weather})
        if err:
            errors.append((row["station_id"], err))

    # Portfolio metrics (exclude stations with missing current score)
    valid_currents = [r for r in results if r["current"] is not None]
    sites_mapped = len(results)
    avg_current = round(sum(r["current"]["overall_score"] for r in valid_currents) / len(valid_currents), 2) if valid_currents else None
    high_risk_count = sum(1 for r in valid_currents if r["current"]["risk_band"] in ("high", "very_high"))
    # forecast alerts: forecast score > current score by more than 5 points
    forecast_alerts = sum(1 for r in valid_currents if r["forecast"] and (r["forecast"]["overall_score"] - r["current"]["overall_score"] > 5))

    # Top metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sites mapped", sites_mapped)
    c2.metric(
        "Average current risk score",
        format_score(avg_current) if avg_current is not None else "N/A",
    )
    c3.metric(
        "High-risk sites",
        high_risk_count,
        help=f"High-risk threshold: {RISK_BANDS['high'][0]}+",
    )
    c4.metric(
        "Forecast alerts",
        forecast_alerts,
        help="Forecast alert rule: forecast overall score exceeds current overall score by more than 5 points",
    )

    # Map
    # default map center/zoom
    m_center = CARDIFF_CENTER
    m_zoom = CARDIFF_ZOOM
    m = folium.Map(location=m_center, zoom_start=m_zoom)
    for r in results:
        row = r["row"]
        cur = r["current"]
        fcast = r["forecast"]
        err = r["error"]
        band = cur["risk_band"] if cur else None
        color = risk_color(band)
        popup = format_popup(row, cur, fcast, err)
        folium.CircleMarker(location=(row["latitude"], row["longitude"]), radius=6, color=color, fill=True, fill_color=color, popup=folium.Popup(popup, max_width=300)).add_to(m)
    # simple legend (HTML overlay)
    legend_html = '''
     <div style="position: fixed; bottom: 50px; left: 50px; width:160px; z-index:9999; font-size:14px;">
     <b>Risk legend</b><br>
     <i style="background:green;color:white;padding:2px 6px;border-radius:3px;">&nbsp;</i> Very low<br>
     <i style="background:lightgreen;color:black;padding:2px 6px;border-radius:3px;">&nbsp;</i> Low<br>
     <i style="background:orange;color:black;padding:2px 6px;border-radius:3px;">&nbsp;</i> Moderate<br>
     <i style="background:red;color:white;padding:2px 6px;border-radius:3px;">&nbsp;</i> High<br>
     <i style="background:darkred;color:white;padding:2px 6px;border-radius:3px;">&nbsp;</i> Very high
     </div>
     '''
    m.get_root().html.add_child(folium.Element(legend_html))

    st_data = st_folium(m, width=700, height=500)

    # Right-hand panels: selected site and proposed site
    sel_col, prop_col = st.columns(2)

    with sel_col:
        st.header("Selected site")
        # selector shows "station name — station ID"
        id_to_name = {r['station_id']: r['row']['station_name'] for r in results}
        sid = st.selectbox("Select station", options=stations["station_id"].tolist(), format_func=lambda s: f"{id_to_name.get(s, s)} — {s}")
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
                    delta = round(fcast['overall_score'] - cur['overall_score'], 1)
                    # show numeric delta as arrow only when non-zero
                    if abs(delta) < 1e-9:
                        mfcast.metric("Forecast score", format_score(fcast['overall_score']))
                        mfcast.write("No change")
                    else:
                        mfcast.metric("Forecast score", format_score(fcast['overall_score']), delta=delta)
                        if delta > 0:
                            mfcast.write(f"Increase: +{delta:.1f} points")
                        else:
                            mfcast.write(f"Decrease: {delta:.1f} points")
                else:
                    mfcast.metric("Forecast score", "N/A")
                # traceability cue
                if weather and weather.get('retrieved_at'):
                    st.write(f"Calculated using model {MODEL_VERSION} and weather retrieved at {weather['retrieved_at']}.")
                # temperatures
                if weather and 'current_temperature_c' in weather:
                    st.write(f"Current temperature: {format_temperature(weather.get('current_temperature_c'))}")
                if weather and 'forecast_max_temperature_c' in weather:
                    st.write(f"Maximum seven-day forecast temperature: {format_temperature(weather.get('forecast_max_temperature_c')[0])}")
                # contribution chart (weighted point contributions)
                contrib = {
                    'Flood exposure': cur['flood_contribution'],
                    'Temperature': cur['temperature_contribution'],
                    'Income deprivation': cur['deprivation_contribution']
                }
                contrib_df = pd.DataFrame({'factor': list(contrib.keys()), 'contribution': list(contrib.values())})
                contrib_df = contrib_df.sort_values('contribution', ascending=False)
                chart = build_contribution_chart(contrib_df)
                labels = chart.mark_text(
                    align='left',
                    baseline='middle',
                    dx=5,
                ).encode(
                    text=alt.Text('contribution:Q', format='.1f')
                )
                st.altair_chart((chart + labels), use_container_width=True)
                st.caption('Weighted contributions sum to the overall score.')
            else:
                st.write("Current score: N/A")
            # assessment details
            with st.expander('Assessment details', expanded=False):
                st.write("Data source: Station sample PoC data (data/stations.csv)")
                st.write("Weather provider: Open-Meteo")
                if cur:
                    st.write(f"Model version: {cur['model_version']}")
                    st.write(f"Calculated at: {cur['calculated_at']}")
                st.write("Forecast horizon: 7 days")

    with prop_col:
        st.header("Proposed site")
        lat = st.number_input("Latitude", value=float(CARDIFF_CENTER[0]))
        lon = st.number_input("Longitude", value=float(CARDIFF_CENTER[1]))
        st.caption("For this demonstrator, flood and deprivation scores are entered manually. Automated geospatial matching is planned for a later iteration.")
        pflood = st.slider("Flood exposure score", 0, 100, 50, help="Illustrative standardised score (0–100)")
        pdep = st.slider("Income deprivation score", 0, 100, 50, help="Illustrative standardised score (0–100)")
        if st.button("Assess proposed site"):
            weather = cached_weather(lat, lon)
            if weather.get('error'):
                st.warning(f"Weather error: {weather['error']}")
                st.write("Cannot calculate forecast score without weather data.")
            else:
                cur = compute_scores(pflood, weather['current_temperature_c'], pdep)
                fcast = compute_scores(pflood, weather['forecast_max_temperature_c'][0], pdep)
                # display same visual format as selected site
                pc1, pc2 = st.columns(2)
                pc1.metric('Current score', format_score(cur['overall_score']))
                pc1.write(display_band(cur['risk_band']))
                delta = round(fcast['overall_score'] - cur['overall_score'], 1)
                if abs(delta) < 1e-9:
                    pc2.metric('Forecast score', format_score(fcast['overall_score']))
                    pc2.write('No change')
                else:
                    pc2.metric('Forecast score', format_score(fcast['overall_score']), delta=delta)
                    if delta > 0:
                        pc2.write(f"Increase: +{delta:.1f} points")
                    else:
                        pc2.write(f"Decrease: {delta:.1f} points")
                if weather and weather.get('retrieved_at'):
                    st.write(f"Calculated using model {MODEL_VERSION} and weather retrieved at {weather['retrieved_at']}.")
                st.write(f"Current temperature: {format_temperature(weather.get('current_temperature_c'))}")
                st.write(f"Maximum seven-day forecast temperature: {format_temperature(weather.get('forecast_max_temperature_c')[0])}")
                contrib = {
                    'Flood exposure': cur['flood_contribution'],
                    'Temperature': cur['temperature_contribution'],
                    'Income deprivation': cur['deprivation_contribution']
                }
                contrib_df = pd.DataFrame({'factor': list(contrib.keys()), 'contribution': list(contrib.values())})
                contrib_df = contrib_df.sort_values('contribution', ascending=False)
                chart = build_contribution_chart(contrib_df)
                labels = chart.mark_text(
                    align='left',
                    baseline='middle',
                    dx=5,
                ).encode(
                    text=alt.Text('contribution:Q', format='.1f')
                )
                st.altair_chart((chart + labels), use_container_width=True)
                st.caption('Weighted contributions sum to the overall score.')

    # Footer disclaimer and attribution
    st.markdown("---")
    st.caption("This is an illustrative research PoC. It does not predict claims, calculate premiums or automate underwriting.")
    st.caption("Weather data: Open-Meteo. Map tiles: OpenStreetMap contributors.")


if __name__ == '__main__':
    main()
