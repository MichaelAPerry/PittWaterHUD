"""
Pittsburgh Water HUD v2
Comprehensive river conditions dashboard for boaters, anglers, and paddlers.

Data sources (all free, no API keys required):
  - USGS NWIS          : River flow, gauge height, water temp (5-min)
  - Open-Meteo         : Wind, UV, air quality, precip, sunrise/sunset
  - NWS api.weather.gov: Active flood/weather alerts
  - NWPS water.noaa.gov: 48-hour predicted river stage
  - Solunar.org        : Moon phase, major/minor fish feeding periods
  - WPRDC CKAN         : Allegheny County water quality lab samples
  - ALCOSAN SOAK       : Seasonal sewage overflow status (Apr–Oct)
"""

import math
import requests
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone, date
import pytz

# ─── CONFIG ──────────────────────────────────────────────────────────────────
EASTERN = pytz.timezone("America/New_York")
LAT, LON = 40.4406, -79.9959  # Point State Park / Pittsburgh

RIVERS = {
    "Monongahela": {
        "site_id": "03085000",       # Monongahela at Braddock (better coverage than 03085152)
        "location": "Braddock",
        "color": "#4FC3F7",
        "action_stage": 17.0,        # NWS Action Stage (ft)
        "flood_stage": 25.0,
        "icon": "🌊",
        "nwps_id": "BRKP1",          # NWS gauge ID for NWPS forecasts
        "upstream_site": "03075070", # Youghiogheny at Connellsville (~6hr lead time)
        "upstream_name": "Youghiogheny at Connellsville",
    },
    "Allegheny": {
        "site_id": "03049640",
        "location": "Acmetonia",
        "color": "#81C784",
        "action_stage": 18.0,
        "flood_stage": 25.0,
        "icon": "🏔️",
        "nwps_id": "PTBP1",
        "upstream_site": "03049500", # Allegheny at Natrona (~2hr lead time)
        "upstream_name": "Allegheny at Natrona",
    },
    "Ohio": {
        "site_id": "03086000",
        "location": "Sewickley",
        "color": "#FFB74D",
        "action_stage": 16.0,
        "flood_stage": 24.0,
        "icon": "⚡",
        "nwps_id": "SEWP1",
        "upstream_site": None,       # Ohio is downstream — no upstream site
        "upstream_name": None,
    },
}

WPRDC_RESOURCE_ID = "1c59b26a-1684-4bfb-92f7-205b947530cf"

# NWS weather codes → human readable
WMO_CODES = {
    0:"Clear",1:"Mainly Clear",2:"Partly Cloudy",3:"Overcast",
    45:"Fog",48:"Freezing Fog",51:"Light Drizzle",53:"Drizzle",55:"Heavy Drizzle",
    61:"Light Rain",63:"Rain",65:"Heavy Rain",71:"Light Snow",73:"Snow",75:"Heavy Snow",
    77:"Snow Grains",80:"Light Showers",81:"Showers",82:"Heavy Showers",
    85:"Light Snow Showers",86:"Snow Showers",95:"Thunderstorm",96:"Thunderstorm+Hail",99:"Heavy T-Storm+Hail",
}

# ─── PAGE CONFIG ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Pittsburgh Water HUD",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Barlow+Condensed:wght@300;600;700&display=swap');

  html, body, [class*="css"] {
    font-family: 'Barlow Condensed', sans-serif;
    background-color: #0a0e1a;
    color: #c8d8e8;
  }
  .main { background-color: #0a0e1a; }
  .main::before {
    content: '';
    position: fixed; top:0; left:0; right:0; bottom:0;
    background: repeating-linear-gradient(0deg,rgba(0,0,0,0.03) 0px,rgba(0,0,0,0.03) 1px,transparent 1px,transparent 2px);
    pointer-events: none;
    z-index: 999;
  }
  h1,h2,h3 { font-family: 'Share Tech Mono', monospace; }
  .hud-title {
    font-family: 'Share Tech Mono', monospace;
    font-size: 2.6rem; color: #4FC3F7;
    letter-spacing: 4px; text-shadow: 0 0 20px #4FC3F780; margin:0;
  }
  .hud-sub { font-size:0.75rem; color:#37474f; letter-spacing:6px; text-transform:uppercase; margin-top:-2px; }
  .section-label {
    font-family:'Share Tech Mono',monospace; font-size:0.62rem; color:#37474f;
    letter-spacing:5px; text-transform:uppercase; margin-bottom:8px;
  }
  /* Score banners */
  .score-go {
    background:linear-gradient(90deg,#0a1f0a,#0d2b0d); border:1px solid #2e7d32;
    border-radius:4px; padding:12px 20px; color:#66bb6a;
    font-family:'Share Tech Mono',monospace; letter-spacing:3px; font-size:1rem;
    text-shadow:0 0 8px #66bb6a60;
  }
  .score-caution {
    background:linear-gradient(90deg,#1f1500,#2b1e00); border:1px solid #f57f17;
    border-radius:4px; padding:12px 20px; color:#ffa726;
    font-family:'Share Tech Mono',monospace; letter-spacing:3px; font-size:1rem;
    text-shadow:0 0 8px #ffa72660;
  }
  .score-danger {
    background:linear-gradient(90deg,#1f0000,#2b0000); border:1px solid #c62828;
    border-radius:4px; padding:12px 20px; color:#ef5350;
    font-family:'Share Tech Mono',monospace; letter-spacing:3px; font-size:1rem;
    text-shadow:0 0 10px #ef535080;
    animation: pulse-border 2s infinite;
  }
  @keyframes pulse-border {
    0%,100%{border-color:#c62828} 50%{border-color:#ef5350;box-shadow:0 0 15px #ef535040}
  }
  .alcosan-ok { background:linear-gradient(90deg,#0a1f0a,#0d2b0d); border:1px solid #2e7d32; border-radius:3px; padding:8px 14px; color:#66bb6a; font-family:'Share Tech Mono',monospace; font-size:0.78rem; letter-spacing:2px; }
  .alcosan-warn { background:linear-gradient(90deg,#1f1500,#2b1e00); border:1px solid #f57f17; border-radius:3px; padding:8px 14px; color:#ffa726; font-family:'Share Tech Mono',monospace; font-size:0.78rem; letter-spacing:2px; }
  .alcosan-off { background:linear-gradient(90deg,#111120,#1a1a30); border:1px solid #2a2a4a; border-radius:3px; padding:8px 14px; color:#3a4a6a; font-family:'Share Tech Mono',monospace; font-size:0.78rem; letter-spacing:2px; }
  /* Metric cards */
  .metric-card {
    background:linear-gradient(135deg,#0d1b2a,#111f30);
    border:1px solid #1a2c3a; border-radius:4px; padding:18px 20px;
    position:relative; overflow:hidden; height:100%;
  }
  .metric-card::before {
    content:''; position:absolute; top:0; left:0; right:0; height:2px;
    background:var(--c); box-shadow:0 0 10px var(--c);
  }
  .river-name { font-family:'Share Tech Mono',monospace; font-size:1.2rem; letter-spacing:3px; color:var(--c); text-shadow:0 0 8px var(--c); }
  .river-loc { font-size:0.68rem; color:#37474f; letter-spacing:3px; text-transform:uppercase; }
  .flow-value { font-family:'Share Tech Mono',monospace; font-size:2.4rem; color:#e0f0ff; margin-top:8px; line-height:1; }
  .flow-unit { font-size:0.7rem; color:#546e7a; letter-spacing:2px; }
  .card-sub { font-family:'Share Tech Mono',monospace; font-size:0.9rem; color:#78909c; margin-top:5px; }
  .card-stage { font-family:'Share Tech Mono',monospace; font-size:0.72rem; letter-spacing:2px; margin-top:8px; }
  .card-speed { font-family:'Share Tech Mono',monospace; font-size:0.72rem; color:#546e7a; letter-spacing:2px; margin-top:4px; }
  .card-thresh { font-size:0.6rem; color:#1e2e3a; letter-spacing:1px; margin-top:4px; }
  .sparkbars { display:flex; align-items:flex-end; gap:2px; height:26px; margin-top:8px; opacity:0.5; }
  .sparkbars span { flex:1; background:var(--c); border-radius:1px; }
  /* Info panels */
  .info-panel {
    background:#0d1520; border:1px solid #1a2a3a; border-radius:4px; padding:14px 16px; height:100%;
  }
  .info-title { font-family:'Share Tech Mono',monospace; font-size:0.8rem; color:#546e7a; letter-spacing:3px; }
  .info-value { font-family:'Share Tech Mono',monospace; font-size:1.6rem; color:#e0f0ff; line-height:1.1; }
  .info-sub { font-family:'Share Tech Mono',monospace; font-size:0.7rem; color:#546e7a; letter-spacing:2px; }
  /* Alert box */
  .nws-alert {
    background:linear-gradient(90deg,#1f0000,#2b0000); border:1px solid #c62828;
    border-radius:4px; padding:12px 18px; margin-bottom:12px;
    font-family:'Share Tech Mono',monospace; font-size:0.85rem; color:#ef5350;
    letter-spacing:2px; line-height:1.8;
  }
  /* Solunar */
  .solunar-period {
    background:#0d1520; border:1px solid #1a2a3a; border-radius:3px; padding:8px 12px;
    font-family:'Share Tech Mono',monospace; font-size:0.78rem;
    color:#FFB74D; letter-spacing:2px; text-align:center; margin-bottom:6px;
  }
  .solunar-minor {
    background:#0d1520; border:1px solid #1a2a3a; border-radius:3px; padding:6px 12px;
    font-family:'Share Tech Mono',monospace; font-size:0.72rem;
    color:#546e7a; letter-spacing:2px; text-align:center; margin-bottom:4px;
  }
  /* Upstream warning */
  .upstream-card {
    background:#0d1520; border:1px solid #1a2a3a; border-radius:4px; padding:12px 14px;
  }
  .upstream-label { font-family:'Share Tech Mono',monospace; font-size:0.62rem; color:#37474f; letter-spacing:3px; }
  .upstream-val { font-family:'Share Tech Mono',monospace; font-size:1.3rem; color:#e0f0ff; }
  .upstream-trend { font-family:'Share Tech Mono',monospace; font-size:0.72rem; letter-spacing:2px; }
  /* WQ table */
  .stDataFrame { background:#0d1520 !important; }
  /* Misc */
  .timestamp { font-family:'Share Tech Mono',monospace; font-size:0.72rem; color:#37474f; letter-spacing:2px; line-height:1.8; }
  hr.hud-hr { border:none; border-top:1px solid #1a2a3a; margin:14px 0; }
  .live-dot { display:inline-block; width:6px; height:6px; background:#66bb6a; border-radius:50%; box-shadow:0 0 6px #66bb6a; animation:pulse 2s infinite; vertical-align:middle; margin-right:6px; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }
  /* Hide streamlit chrome */
  #MainMenu, footer, header { visibility:hidden; }
  .block-container { padding-top:1.5rem; padding-bottom:1rem; }
</style>
""", unsafe_allow_html=True)


# ─── HELPER FUNCTIONS ─────────────────────────────────────────────────────────

def wind_compass(deg):
    dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]
    return dirs[round(deg / 22.5) % 16]


def flow_to_speed_mph(flow_cfs):
    """Rough estimate: 10,000 cfs ≈ 0.36 mph (per USACE Pittsburgh sailing data)."""
    if flow_cfs is None:
        return None
    return flow_cfs * 0.000036


def stage_status(gauge, action, flood):
    if gauge is None:
        return "unknown", "—", "#546e7a"
    if gauge >= flood:
        return "flood", f"⚠ FLOOD STAGE ({gauge:.2f} ft)", "#ef5350"
    if gauge >= action:
        return "action", f"▲ ACTION STAGE ({gauge:.2f} ft)", "#ffa726"
    if gauge >= action - 3:
        return "elevated", f"↑ ELEVATED ({gauge:.2f} ft)", "#ffcc80"
    return "normal", f"● NORMAL ({gauge:.2f} ft)", "#66bb6a"


def aqi_label(aqi):
    if aqi is None: return "—", "#546e7a"
    if aqi <= 50:   return f"GOOD ({aqi})", "#66bb6a"
    if aqi <= 100:  return f"MODERATE ({aqi})", "#ffd54f"
    if aqi <= 150:  return f"UNHEALTHY SENSITIVE ({aqi})", "#ffa726"
    if aqi <= 200:  return f"UNHEALTHY ({aqi})", "#ef5350"
    return f"VERY UNHEALTHY ({aqi})", "#ab47bc"


def moon_phase(dt):
    """Calculate moon phase (0=new, 0.5=full) and name."""
    reference = datetime(2024, 1, 11)  # Known new moon
    days_since = (dt.date() - reference.date()).days
    phase = (days_since % 29.53059) / 29.53059
    emojis = ["🌑","🌒","🌒","🌓","🌔","🌔","🌕","🌖","🌖","🌗","🌘","🌘","🌑"]
    names = [
        "New Moon","Waxing Crescent","Waxing Crescent","First Quarter",
        "Waxing Gibbous","Waxing Gibbous","Full Moon",
        "Waning Gibbous","Waning Gibbous","Last Quarter",
        "Waning Crescent","Waning Crescent","New Moon"
    ]
    idx = min(int(phase * 12), 12)
    return phase, emojis[idx], names[idx]


def is_soak_season(dt):
    return 4 <= dt.month <= 10


def cso_risk_from_precip(precip_24h_in, precip_prob_pct):
    """Estimate CSO/sewage overflow risk from precipitation data."""
    if precip_24h_in >= 0.5 or precip_prob_pct >= 70:
        return "HIGH OVERFLOW RISK", "alcosan-warn", "▲"
    if precip_24h_in >= 0.2 or precip_prob_pct >= 40:
        return "MODERATE RISK", "alcosan-warn", "◈"
    return "LOW RISK", "alcosan-ok", "●"


def hex_to_rgba(hex_color, alpha=0.06):
    """Convert #RRGGBB to rgba(r,g,b,a) — Plotly requires this for fillcolor."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def sparkbars_html(trend, color):
    if not trend:
        return ""
    mn, mx = min(trend), max(trend)
    rng = mx - mn or 1
    bars = "".join(
        f'<span style="height:{max(8, (v-mn)/rng*100):.0f}%"></span>'
        for v in trend
    )
    return f'<div class="sparkbars" style="--c:{color}">{bars}</div>'


def fmt_flow(cfs):
    if cfs is None: return "—"
    return f"{cfs:,.0f}"


def fmt_temp_f(c):
    if c is None: return "—"
    return f"{c*9/5+32:.1f}°F"


# ─── DATA FETCHERS ────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def fetch_usgs_current():
    site_ids = ",".join(r["site_id"] for r in RIVERS.values())
    url = (f"https://waterservices.usgs.gov/nwis/iv/"
           f"?format=json&sites={site_ids}&parameterCd=00060,00065,00010")
    try:
        data = requests.get(url, timeout=10).json()
        results = {}
        for series in data["value"]["timeSeries"]:
            site = series["sourceInfo"]["siteCode"][0]["value"]
            param = series["variable"]["variableCode"][0]["value"]
            vals = series["values"][0]["value"]
            if not vals: continue
            latest = vals[-1]
            if latest["value"] == "-999999": continue
            key = next((k for k, v in RIVERS.items() if v["site_id"] == site), None)
            if not key: continue
            results.setdefault(key, {})["timestamp"] = latest["dateTime"]
            if param == "00060": results[key]["flow_cfs"] = float(latest["value"])
            elif param == "00065": results[key]["gauge_ft"] = float(latest["value"])
            elif param == "00010": results[key]["temp_c"] = float(latest["value"])
        return results, None
    except Exception as e:
        return {}, str(e)


@st.cache_data(ttl=300)
def fetch_usgs_upstream():
    """Fetch upstream headwater gauges for early flood warning."""
    upstream_sites = [v["upstream_site"] for v in RIVERS.values() if v["upstream_site"]]
    if not upstream_sites:
        return {}, None
    url = (f"https://waterservices.usgs.gov/nwis/iv/"
           f"?format=json&sites={','.join(upstream_sites)}&parameterCd=00060,00065")
    try:
        data = requests.get(url, timeout=10).json()
        results = {}
        for series in data["value"]["timeSeries"]:
            site = series["sourceInfo"]["siteCode"][0]["value"]
            site_name = series["sourceInfo"]["siteName"]
            param = series["variable"]["variableCode"][0]["value"]
            vals = series["values"][0]["value"]
            if not vals: continue
            latest = vals[-1]
            if latest["value"] == "-999999": continue
            results.setdefault(site, {"name": site_name})
            if param == "00060": results[site]["flow_cfs"] = float(latest["value"])
            elif param == "00065": results[site]["gauge_ft"] = float(latest["value"])
            # Compute 1-hour trend
            recent = [float(v["value"]) for v in vals[-12:] if v["value"] != "-999999"]
            if len(recent) >= 2:
                results[site]["trend"] = recent[-1] - recent[0]
        return results, None
    except Exception as e:
        return {}, str(e)


@st.cache_data(ttl=900)
def fetch_usgs_24h():
    site_ids = ",".join(r["site_id"] for r in RIVERS.values())
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=24)
    url = (f"https://waterservices.usgs.gov/nwis/iv/?format=json&sites={site_ids}"
           f"&parameterCd=00065&startDT={start.strftime('%Y-%m-%dT%H:%M:%SZ')}"
           f"&endDT={end.strftime('%Y-%m-%dT%H:%M:%SZ')}")
    try:
        data = requests.get(url, timeout=15).json()
        out = {}
        for series in data["value"]["timeSeries"]:
            site = series["sourceInfo"]["siteCode"][0]["value"]
            key = next((k for k, v in RIVERS.items() if v["site_id"] == site), None)
            if not key: continue
            records = [
                {"time": pd.to_datetime(v["dateTime"]).tz_convert(EASTERN),
                 "gauge_ft": float(v["value"])}
                for v in series["values"][0]["value"]
                if v["value"] != "-999999"
            ]
            out[key] = pd.DataFrame(records) if records else pd.DataFrame()
        return out, None
    except Exception as e:
        return {}, str(e)


@st.cache_data(ttl=600)
def fetch_open_meteo():
    """Fetch weather, air quality, and daily astronomy from Open-Meteo (no key needed)."""
    weather_url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}"
        f"&current=temperature_2m,apparent_temperature,wind_speed_10m,wind_direction_10m,"
        f"wind_gusts_10m,precipitation,weather_code,cloud_cover,visibility"
        f"&daily=sunrise,sunset,uv_index_max,precipitation_probability_max,"
        f"wind_speed_10m_max,wind_direction_10m_dominant,precipitation_sum,weather_code"
        f"&hourly=precipitation_probability,precipitation"
        f"&timezone=America%2FNew_York&forecast_days=3"
        f"&wind_speed_unit=mph&temperature_unit=fahrenheit&precipitation_unit=inch"
    )
    aq_url = (
        f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={LAT}&longitude={LON}"
        f"&current=us_aqi,pm2_5,pm10&timezone=America%2FNew_York"
    )
    try:
        wx = requests.get(weather_url, timeout=10).json()
        aq = requests.get(aq_url, timeout=10).json()
        return {"weather": wx, "air_quality": aq}, None
    except Exception as e:
        return {}, str(e)


@st.cache_data(ttl=600)
def fetch_nws_alerts():
    """Fetch active NWS alerts for the Pittsburgh area."""
    url = f"https://api.weather.gov/alerts/active?point={LAT},{LON}"
    try:
        r = requests.get(url, timeout=8, headers={"User-Agent": "PittsburghWaterHUD/2.0"}).json()
        alerts = []
        for feat in r.get("features", []):
            p = feat.get("properties", {})
            alerts.append({
                "event": p.get("event",""),
                "headline": p.get("headline",""),
                "severity": p.get("severity",""),
                "expires": p.get("expires",""),
            })
        return alerts, None
    except Exception as e:
        return [], str(e)


@st.cache_data(ttl=900)
def fetch_nwps_forecast(nwps_id):
    """Fetch 48-hour predicted river stage from NWPS (NWS Water Prediction Service)."""
    url = f"https://api.water.noaa.gov/nwps/v1/gauges/{nwps_id}/stageflow"
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "PittsburghWaterHUD/2.0"}).json()
        forecast = r.get("forecast", {}).get("data", [])
        if not forecast:
            return None, "No forecast data"
        records = [
            {"time": pd.to_datetime(f["validTime"]).tz_convert(EASTERN),
             "stage": f.get("primary")}
            for f in forecast if f.get("primary") is not None
        ]
        return pd.DataFrame(records), None
    except Exception as e:
        return None, str(e)


@st.cache_data(ttl=3600)
def fetch_solunar():
    """Fetch solunar fishing table from solunar.org (free, no key)."""
    now_et = datetime.now(EASTERN)
    date_str = now_et.strftime("%Y%m%d")
    # UTC offset for Eastern: -5 (EST) or -4 (EDT)
    tz_offset = -5 if now_et.dst() == timedelta(0) else -4
    url = f"https://api.solunar.org/solunar/{LAT},{LON},{date_str},{tz_offset}"
    try:
        data = requests.get(url, timeout=8).json()
        return data, None
    except Exception as e:
        return {}, str(e)


@st.cache_data(ttl=1800)
def fetch_wprdc():
    url = (f"https://data.wprdc.org/api/action/datastore_search"
           f"?resource_id={WPRDC_RESOURCE_ID}&limit=6&sort=date desc")
    try:
        r = requests.get(url, timeout=10).json()
        return r["result"]["records"], None
    except Exception as e:
        return [], str(e)


@st.cache_data(ttl=600)
def fetch_alcosan_soak():
    """Scrape ALCOSAN SOAK status. Falls back gracefully."""
    if not is_soak_season(datetime.now(EASTERN)):
        return "INACTIVE", "off", "Season: Apr 1 – Oct 31"
    try:
        r = requests.get(
            "https://www.alcosan.org/services/sewage-overflow-alerts",
            timeout=8,
            headers={"User-Agent": "PittsburghWaterHUD/2.0 Educational Project"}
        )
        text = r.text.lower()
        if "no overflow" in text or "no active" in text:
            return "NO OVERFLOW", "ok", "SOAK monitoring active"
        if "overflow" in text or "active" in text:
            return "OVERFLOW ACTIVE", "warn", "Check alcosan.org for details"
        return "CHECK SITE", "warn", "Status unclear — visit alcosan.org"
    except Exception:
        return "UNAVAILABLE", "off", "alcosan.org unreachable"


# ─── LOAD ALL DATA ────────────────────────────────────────────────────────────

now_et = datetime.now(EASTERN)

with st.spinner("Loading river data…"):
    current_data, current_err = fetch_usgs_current()
    history_data, history_err = fetch_usgs_24h()
    upstream_data, upstream_err = fetch_usgs_upstream()
    meteo_data, meteo_err = fetch_open_meteo()
    nws_alerts, alerts_err = fetch_nws_alerts()
    solunar_data, solunar_err = fetch_solunar()
    wq_records, wq_err = fetch_wprdc()
    alcosan_status, alcosan_level, alcosan_detail = fetch_alcosan_soak()

# Parse Open-Meteo
wx = meteo_data.get("weather", {})
aq = meteo_data.get("air_quality", {})
wx_current = wx.get("current", {})
wx_daily = wx.get("daily", {})
aq_current = aq.get("current", {})

wind_speed = wx_current.get("wind_speed_10m")
wind_dir = wx_current.get("wind_direction_10m")
wind_gust = wx_current.get("wind_gusts_10m")
temp_f_now = wx_current.get("temperature_2m")
feels_like = wx_current.get("apparent_temperature")
precip_now = wx_current.get("precipitation", 0)
weather_code = wx_current.get("weather_code")
visibility_m = wx_current.get("visibility")
cloud_pct = wx_current.get("cloud_cover", 0)

# Daily: today (index 0) and tomorrow (index 1)
uv_today = (wx_daily.get("uv_index_max") or [None])[0]
precip_prob_today = (wx_daily.get("precipitation_probability_max") or [None])[0]
precip_sum_today = (wx_daily.get("precipitation_sum") or [None])[0]
wind_max_today = (wx_daily.get("wind_speed_10m_max") or [None])[0]
sunrise_today = (wx_daily.get("sunrise") or [None])[0]
sunset_today = (wx_daily.get("sunset") or [None])[0]

# Tomorrow forecast
uv_tomorrow = (wx_daily.get("uv_index_max") or [None, None])[1] if len(wx_daily.get("uv_index_max") or []) > 1 else None
precip_prob_tomorrow = (wx_daily.get("precipitation_probability_max") or [None, None])[1] if len(wx_daily.get("precipitation_probability_max") or []) > 1 else None
wind_max_tomorrow = (wx_daily.get("wind_speed_10m_max") or [None, None])[1] if len(wx_daily.get("wind_speed_10m_max") or []) > 1 else None

aqi_val = aq_current.get("us_aqi")
pm25 = aq_current.get("pm2_5")
aqi_text, aqi_color = aqi_label(aqi_val)

visibility_mi = round(visibility_m / 1609.34, 1) if visibility_m else None

moon_phase_val, moon_emoji, moon_name = moon_phase(now_et)

# CSO Risk (precip-based, replaces ALCOSAN scrape as primary signal)
cso_label, cso_css, cso_icon = cso_risk_from_precip(
    precip_sum_today or 0,
    precip_prob_today or 0
)

# ─── COMPUTE COMPOSITE CONDITIONS SCORE ──────────────────────────────────────

def composite_score():
    issues = []
    warnings = []

    # Check flood/action stages
    for river, cfg in RIVERS.items():
        rd = current_data.get(river, {})
        g = rd.get("gauge_ft")
        if g and g >= cfg["flood_stage"]:
            issues.append(f"{river} at FLOOD STAGE")
        elif g and g >= cfg["action_stage"]:
            issues.append(f"{river} at ACTION STAGE")

    # NWS flood alerts
    flood_alerts = [a for a in nws_alerts if "flood" in a["event"].lower() or "flash" in a["event"].lower()]
    if flood_alerts:
        issues.append("NWS FLOOD ALERT ACTIVE")

    # Wind
    if wind_speed and wind_speed > 25:
        issues.append(f"DANGEROUS WIND ({wind_speed:.0f} mph)")
    elif wind_speed and wind_speed > 15:
        warnings.append(f"HIGH WIND ({wind_speed:.0f} mph)")

    # Precip / CSO
    if (precip_prob_today or 0) > 70 or (precip_sum_today or 0) > 0.5:
        warnings.append("RAIN / CSO RISK")

    # Air quality
    if aqi_val and aqi_val > 150:
        issues.append(f"POOR AIR QUALITY (AQI {aqi_val})")
    elif aqi_val and aqi_val > 100:
        warnings.append(f"MODERATE AIR QUALITY (AQI {aqi_val})")

    # Visibility / fog
    if visibility_mi and visibility_mi < 0.5:
        issues.append("DENSE FOG — LIMITED VISIBILITY")
    elif visibility_mi and visibility_mi < 2:
        warnings.append("REDUCED VISIBILITY / FOG")

    # Thunderstorm
    if weather_code and weather_code >= 95:
        issues.append("THUNDERSTORM ACTIVE")

    if issues:
        return "STAY OFF WATER", "score-danger", "✕", issues, warnings
    if warnings:
        return "USE CAUTION", "score-caution", "⚠", issues, warnings
    return "CONDITIONS FAVORABLE", "score-go", "✓", issues, warnings

score_label, score_css, score_icon, score_issues, score_warnings = composite_score()


# ─── RENDER: HEADER ───────────────────────────────────────────────────────────

col_title, col_score, col_alcosan, col_time = st.columns([3, 2, 2, 1])

with col_title:
    st.markdown('<div class="hud-title">⬡ PITTSBURGH WATER HUD</div>', unsafe_allow_html=True)
    st.markdown('<div class="hud-sub">Three Rivers Recreational Conditions</div>', unsafe_allow_html=True)

with col_score:
    st.markdown('<div class="section-label">RIVER CONDITIONS SCORE</div>', unsafe_allow_html=True)
    all_factors = score_issues + score_warnings
    detail = " · ".join(all_factors[:2]) if all_factors else "All systems normal"
    st.markdown(f'<div class="{score_css}">{score_icon} {score_label}<br><span style="font-size:0.65rem;opacity:0.7">{detail}</span></div>', unsafe_allow_html=True)

with col_alcosan:
    st.markdown('<div class="section-label">ALCOSAN SOAK / CSO RISK</div>', unsafe_allow_html=True)
    if alcosan_level == "off":
        # Use precip-based CSO risk as primary signal
        st.markdown(f'<div class="{cso_css}">{cso_icon} {cso_label}<br><span style="font-size:0.62rem;opacity:0.7">SOAK INACTIVE · {alcosan_detail}</span></div>', unsafe_allow_html=True)
    elif alcosan_level == "ok":
        st.markdown(f'<div class="alcosan-ok"><span class="live-dot"></span>{alcosan_status}<br><span style="font-size:0.62rem;opacity:0.7">{cso_label} · {alcosan_detail}</span></div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="alcosan-warn">▲ {alcosan_status}<br><span style="font-size:0.62rem;opacity:0.7">{alcosan_detail}</span></div>', unsafe_allow_html=True)

with col_time:
    st.markdown('<div class="section-label">UPDATED</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="timestamp">{now_et.strftime("%H:%M:%S ET")}<br>{now_et.strftime("%Y-%m-%d")}</div>', unsafe_allow_html=True)

st.markdown('<hr class="hud-hr">', unsafe_allow_html=True)


# ─── NWS ALERTS BANNER ────────────────────────────────────────────────────────

if nws_alerts:
    flood_alerts = [a for a in nws_alerts if any(w in a["event"].lower() for w in ["flood","storm","tornado","thunder"])]
    for alert in flood_alerts[:3]:
        st.markdown(f'<div class="nws-alert">⚠ NWS ALERT — {alert["event"].upper()}<br><span style="font-size:0.72rem;color:#90a4ae;">{alert["headline"]}</span></div>', unsafe_allow_html=True)


# ─── RENDER: RIVER CARDS ──────────────────────────────────────────────────────

st.markdown('<div class="section-label">RIVER CONDITIONS — CURRENT READINGS</div>', unsafe_allow_html=True)

cols = st.columns(3, gap="small")

for idx, (river, cfg) in enumerate(RIVERS.items()):
    rd = current_data.get(river, {})
    gauge = rd.get("gauge_ft")
    flow = rd.get("flow_cfs")
    temp_c = rd.get("temp_c")
    status, stage_label, stage_color = stage_status(gauge, cfg["action_stage"], cfg["flood_stage"])
    speed = flow_to_speed_mph(flow)

    # Get 24h trend for sparkbars
    hist_df = history_data.get(river, pd.DataFrame())
    trend_vals = []
    if not hist_df.empty and "gauge_ft" in hist_df.columns:
        step = max(1, len(hist_df) // 20)
        trend_vals = hist_df["gauge_ft"].iloc[::step].tolist()[-20:]

    with cols[idx]:
        st.markdown(f"""
        <div class="metric-card" style="--c:{cfg['color']}">
          <div class="river-name">{cfg['icon']} {river.upper()}</div>
          <div class="river-loc">◎ {cfg['location']} · {cfg['site_id']}</div>
          <div class="flow-value">{fmt_flow(flow)}</div>
          <div class="flow-unit">CFS (CUBIC FEET / SEC)</div>
          <div class="card-sub">⬦ {f"{gauge:.2f} ft" if gauge else "—"} gauge &nbsp;|&nbsp; {fmt_temp_f(temp_c)}</div>
          <div class="card-stage" style="color:{stage_color};text-shadow:0 0 5px {stage_color}60">{stage_label}</div>
          <div class="card-speed">≈ {f"{speed:.3f} mph current" if speed else "—"} &nbsp;(est.)</div>
          <div class="card-thresh">ACTION @ {cfg['action_stage']} ft &nbsp;|&nbsp; FLOOD @ {cfg['flood_stage']} ft</div>
          {sparkbars_html(trend_vals, cfg['color'])}
        </div>""", unsafe_allow_html=True)


st.markdown('<hr class="hud-hr">', unsafe_allow_html=True)


# ─── RENDER: WEATHER AT THE WATER ─────────────────────────────────────────────

st.markdown('<div class="section-label">WEATHER AT THE WATER</div>', unsafe_allow_html=True)

w1, w2, w3, w4, w5, w6 = st.columns(6, gap="small")

def info_panel(title, value, sub, color="#e0f0ff"):
    return f"""<div class="info-panel">
      <div class="info-title">{title}</div>
      <div class="info-value" style="color:{color}">{value}</div>
      <div class="info-sub">{sub}</div>
    </div>"""

wind_compass_str = wind_compass(wind_dir) if wind_dir is not None else "—"
wind_str = f"{wind_speed:.0f}" if wind_speed else "—"
gust_str = f"GUSTS {wind_gust:.0f} mph" if wind_gust else "—"

wx_desc = WMO_CODES.get(weather_code, "—") if weather_code is not None else "—"
vis_str = f"{visibility_mi} mi" if visibility_mi else "—"
fog_risk = "HIGH" if (visibility_mi and visibility_mi < 1) else ("MODERATE" if (visibility_mi and visibility_mi < 3) else "LOW")
fog_color = "#ef5350" if fog_risk == "HIGH" else ("#ffa726" if fog_risk == "MODERATE" else "#66bb6a")

uv_str = f"{uv_today:.0f}" if uv_today else "—"
uv_label = ("LOW" if (uv_today or 0) <= 2 else "MODERATE" if (uv_today or 0) <= 5 else "HIGH" if (uv_today or 0) <= 7 else "VERY HIGH")
uv_color = "#66bb6a" if uv_label == "LOW" else "#ffd54f" if uv_label == "MODERATE" else "#ffa726" if uv_label == "HIGH" else "#ef5350"

with w1:
    wind_color = "#ef5350" if (wind_speed or 0) > 25 else "#ffa726" if (wind_speed or 0) > 15 else "#e0f0ff"
    st.markdown(info_panel("WIND SPEED", f"{wind_str} mph", f"{wind_compass_str} · {gust_str}", wind_color), unsafe_allow_html=True)

with w2:
    st.markdown(info_panel("TEMPERATURE", f"{temp_f_now:.0f}°F" if temp_f_now else "—", f"FEELS {feels_like:.0f}°F" if feels_like else "—"), unsafe_allow_html=True)

with w3:
    st.markdown(info_panel("CONDITIONS", wx_desc, f"CLOUD COVER {cloud_pct:.0f}%"), unsafe_allow_html=True)

with w4:
    st.markdown(info_panel("VISIBILITY", vis_str, f"FOG RISK: {fog_risk}", fog_color), unsafe_allow_html=True)

with w5:
    st.markdown(info_panel("UV INDEX", uv_str, uv_label, uv_color), unsafe_allow_html=True)

with w6:
    st.markdown(info_panel("AIR QUALITY", f"AQI {aqi_val}" if aqi_val else "—", aqi_text, aqi_color), unsafe_allow_html=True)


# Precip + tomorrow row
st.markdown("")
p1, p2, p3, p4 = st.columns(4, gap="small")

precip_color = "#ef5350" if (precip_prob_today or 0) > 70 else "#ffa726" if (precip_prob_today or 0) > 40 else "#66bb6a"
pm_str = f"PM2.5: {pm25:.1f} µg/m³" if pm25 else "—"

with p1:
    st.markdown(info_panel("PRECIP PROB TODAY", f"{precip_prob_today:.0f}%" if precip_prob_today else "—",
                f"SUM {precip_sum_today:.2f} in" if precip_sum_today else "—", precip_color), unsafe_allow_html=True)

with p2:
    p_tomorrow_color = "#ef5350" if (precip_prob_tomorrow or 0) > 70 else "#ffa726" if (precip_prob_tomorrow or 0) > 40 else "#66bb6a"
    st.markdown(info_panel("PRECIP PROB TOMORROW", f"{precip_prob_tomorrow:.0f}%" if precip_prob_tomorrow else "—",
                f"WIND MAX {wind_max_tomorrow:.0f} mph" if wind_max_tomorrow else "—", p_tomorrow_color), unsafe_allow_html=True)

with p3:
    st.markdown(info_panel("PM2.5 PARTICULATES", pm_str if pm25 else "—",
                "FINE PARTICLE EXPOSURE"), unsafe_allow_html=True)

with p4:
    sunrise_str = pd.to_datetime(sunrise_today).strftime("%-I:%M %p") if sunrise_today else "—"
    sunset_str = pd.to_datetime(sunset_today).strftime("%-I:%M %p") if sunset_today else "—"
    st.markdown(info_panel("DAYLIGHT WINDOW", sunrise_str, f"SUNSET {sunset_str}"), unsafe_allow_html=True)


st.markdown('<hr class="hud-hr">', unsafe_allow_html=True)


# ─── RENDER: 24H TREND CHART ──────────────────────────────────────────────────

st.markdown('<div class="section-label">24-HOUR GAUGE HEIGHT TREND (FT)</div>', unsafe_allow_html=True)

fig = go.Figure()

for river, cfg in RIVERS.items():
    df = history_data.get(river, pd.DataFrame())
    if df.empty:
        continue
    fig.add_trace(go.Scatter(
        x=df["time"], y=df["gauge_ft"],
        name=river, mode="lines",
        line=dict(color=cfg["color"], width=2),
        fill="tozeroy", fillcolor=hex_to_rgba(cfg["color"], 0.06),
        hovertemplate=f"<b>{river}</b><br>%{{y:.2f}} ft<br>%{{x|%H:%M ET}}<extra></extra>",
    ))
    # Action stage reference line
    fig.add_hline(y=cfg["action_stage"], line=dict(color=cfg["color"], width=1, dash="dot"), opacity=0.3)

fig.update_layout(
    paper_bgcolor="#0a0e1a", plot_bgcolor="#0d1520",
    font=dict(family="Share Tech Mono", color="#546e7a", size=11),
    legend=dict(bgcolor="#0d1520", bordercolor="#1e3a4a", borderwidth=1),
    margin=dict(l=20, r=20, t=10, b=20), height=260,
    xaxis=dict(gridcolor="#111e2a", tickformat="%H:%M", tickfont=dict(size=10)),
    yaxis=dict(gridcolor="#111e2a", ticksuffix=" ft", tickfont=dict(size=10)),
    hovermode="x unified",
)
st.plotly_chart(fig, use_container_width=True)


# ─── RENDER: 48H FORECAST ─────────────────────────────────────────────────────

st.markdown('<div class="section-label">48-HOUR PREDICTED STAGE — NWS WATER PREDICTION SERVICE</div>', unsafe_allow_html=True)

forecast_cols = st.columns(3, gap="small")
forecast_fig_data = {}

for idx, (river, cfg) in enumerate(RIVERS.items()):
    nwps_id = cfg.get("nwps_id")
    if nwps_id:
        fc_df, fc_err = fetch_nwps_forecast(nwps_id)
        if fc_df is not None and not fc_df.empty:
            forecast_fig_data[river] = fc_df

if forecast_fig_data:
    fc_fig = go.Figure()
    for river, df in forecast_fig_data.items():
        cfg = RIVERS[river]
        fc_fig.add_trace(go.Scatter(
            x=df["time"], y=df["stage"],
            name=f"{river} (forecast)",
            mode="lines",
            line=dict(color=cfg["color"], width=2, dash="dash"),
            hovertemplate=f"<b>{river} (fcst)</b><br>%{{y:.2f}} ft<br>%{{x|%a %H:%M}}<extra></extra>",
        ))
    fc_fig.update_layout(
        paper_bgcolor="#0a0e1a", plot_bgcolor="#0d1520",
        font=dict(family="Share Tech Mono", color="#546e7a", size=11),
        legend=dict(bgcolor="#0d1520", bordercolor="#1e3a4a", borderwidth=1),
        margin=dict(l=20, r=20, t=10, b=20), height=220,
        xaxis=dict(gridcolor="#111e2a", tickformat="%a %H:%M", tickfont=dict(size=10)),
        yaxis=dict(gridcolor="#111e2a", ticksuffix=" ft", tickfont=dict(size=10)),
        hovermode="x unified",
    )
    st.plotly_chart(fc_fig, use_container_width=True)
else:
    st.markdown('<div class="info-panel" style="text-align:center;padding:20px;"><span style="font-family:Share Tech Mono;color:#37474f;letter-spacing:3px;font-size:0.8rem;">NWPS FORECAST UNAVAILABLE — CHECK water.noaa.gov</span></div>', unsafe_allow_html=True)


st.markdown('<hr class="hud-hr">', unsafe_allow_html=True)


# ─── RENDER: ANGLERS & PADDLERS ───────────────────────────────────────────────

st.markdown('<div class="section-label">ANGLERS & PADDLERS INTEL</div>', unsafe_allow_html=True)

sol_col, moon_col, species_col = st.columns([2, 1, 2], gap="medium")

with sol_col:
    st.markdown('<div class="section-label">SOLUNAR FEEDING PERIODS</div>', unsafe_allow_html=True)
    if solunar_data:
        rating = solunar_data.get("dayRating", 0)
        stars = "★" * int(rating * 5) + "☆" * (5 - int(rating * 5)) if rating else "—"
        moon_pct = solunar_data.get("moonPhase", 0)
        st.markdown(f'<div style="font-family:Share Tech Mono;font-size:0.8rem;color:#FFB74D;letter-spacing:3px;margin-bottom:8px;">DAY RATING: {stars} ({rating:.0%} activity)</div>', unsafe_allow_html=True)
        for key, label, is_major in [
            ("major1","MAJOR 1",True),("major2","MAJOR 2",True),
            ("minor1","MINOR 1",False),("minor2","MINOR 2",False)
        ]:
            period = solunar_data.get(key, "—")
            if period and period != "—":
                css = "solunar-period" if is_major else "solunar-minor"
                dur = "▶ 2h window" if is_major else "▶ 45min window"
                st.markdown(f'<div class="{css}">{label}: {period} &nbsp;{dur}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="info-panel"><span style="font-family:Share Tech Mono;color:#37474f;font-size:0.8rem;letter-spacing:2px;">SOLUNAR DATA UNAVAILABLE</span></div>', unsafe_allow_html=True)

with moon_col:
    st.markdown('<div class="section-label">MOON PHASE</div>', unsafe_allow_html=True)
    moon_pct_display = (moon_phase_val * 100) if moon_phase_val <= 0.5 else ((1 - moon_phase_val) * 100)
    fishing_moon = "GOOD" if 0.1 < moon_phase_val < 0.4 or 0.6 < moon_phase_val < 0.9 else "MODERATE"
    moon_color = "#66bb6a" if fishing_moon == "GOOD" else "#ffa726"
    st.markdown(f"""<div class="info-panel" style="text-align:center">
      <div style="font-size:3rem;margin:8px 0">{moon_emoji}</div>
      <div style="font-family:'Share Tech Mono',monospace;font-size:0.9rem;color:#e0f0ff;letter-spacing:2px">{moon_name}</div>
      <div style="font-family:'Share Tech Mono',monospace;font-size:0.7rem;color:#546e7a;margin-top:6px">{moon_pct_display:.0f}% ILLUMINATED</div>
      <div style="font-family:'Share Tech Mono',monospace;font-size:0.72rem;color:{moon_color};margin-top:8px;letter-spacing:2px">FISHING: {fishing_moon}</div>
    </div>""", unsafe_allow_html=True)

with species_col:
    st.markdown('<div class="section-label">TARGET SPECIES — THREE RIVERS</div>', unsafe_allow_html=True)

    # Dynamic species recommendations based on temp and season
    mon_temp = current_data.get("Monongahela", {}).get("temp_c")
    alg_temp = current_data.get("Allegheny", {}).get("temp_c")
    avg_temp_c = (mon_temp or 0 + alg_temp or 0) / (2 if (mon_temp and alg_temp) else 1) if (mon_temp or alg_temp) else None
    avg_temp_f = avg_temp_c * 9/5 + 32 if avg_temp_c else None

    if avg_temp_f:
        if avg_temp_f < 45:
            species_advice = [
                ("Walleye & Sauger","🎣","Active in cold water; fish deep holes near dams"),
                ("Channel Catfish","🐟","Still feeding; try deep channel structure"),
                ("Muskie","🎣","Slow but big fish possible near Lock & Dam pools"),
            ]
        elif avg_temp_f < 60:
            species_advice = [
                ("Smallmouth Bass","🎣","Pre-spawn; warming up near bridge piers & boulders"),
                ("Walleye","🎣","Excellent — check Allegheny islands & creek mouths"),
                ("White Bass","🐟","Schools forming near dam tailwaters"),
            ]
        else:
            species_advice = [
                ("Smallmouth Bass","🎣","Prime time — bridge piers & rocky banks throughout city"),
                ("Flathead Catfish","🐟","60+ lb fish in city limits; fish after dark"),
                ("Muskellunge","🎣","Back channels of Allegheny islands"),
            ]
    else:
        species_advice = [
            ("Smallmouth Bass","🎣","Bridge piers, mooring structures, rocky banks"),
            ("Walleye & Sauger","🎣","Allegheny islands, creek mouths, dam tailwaters"),
            ("Channel & Flathead Catfish","🐟","Deep holes, confluence areas — some 60+ lbs"),
        ]

    species_html = ""
    for name, icon, tip in species_advice:
        species_html += f"""
        <div style="background:#0d1520;border:1px solid #1a2a3a;border-radius:3px;padding:10px 14px;margin-bottom:6px">
          <div style="font-family:'Share Tech Mono',monospace;font-size:0.82rem;color:#81C784;letter-spacing:2px">{icon} {name}</div>
          <div style="font-family:'Barlow Condensed',sans-serif;font-size:0.85rem;color:#546e7a;margin-top:2px">{tip}</div>
        </div>"""
    st.markdown(species_html, unsafe_allow_html=True)


st.markdown('<hr class="hud-hr">', unsafe_allow_html=True)


# ─── RENDER: UPSTREAM EARLY WARNING ───────────────────────────────────────────

st.markdown('<div class="section-label">UPSTREAM EARLY WARNING — HEADWATER GAUGES</div>', unsafe_allow_html=True)
st.markdown('<div style="font-family:Share Tech Mono;font-size:0.62rem;color:#263238;letter-spacing:3px;margin-bottom:10px;">Rising water here arrives at Pittsburgh in 2–6 hours depending on river</div>', unsafe_allow_html=True)

up_cols = st.columns(3, gap="small")

upstream_pairs = [
    ("Monongahela", RIVERS["Monongahela"]["upstream_site"], RIVERS["Monongahela"]["upstream_name"], "#4FC3F7"),
    ("Allegheny", RIVERS["Allegheny"]["upstream_site"], RIVERS["Allegheny"]["upstream_name"], "#81C784"),
    ("Ohio", None, "No upstream gauge (downstream river)", "#FFB74D"),
]

for idx, (river, site, name, color) in enumerate(upstream_pairs):
    with up_cols[idx]:
        if site and site in upstream_data:
            ud = upstream_data[site]
            flow = ud.get("flow_cfs")
            gauge = ud.get("gauge_ft")
            trend = ud.get("trend", 0)
            trend_str = f"▲ {trend:+.2f} ft/hr" if trend > 0.05 else f"▼ {trend:+.2f} ft/hr" if trend < -0.05 else "► STABLE"
            trend_color = "#ef5350" if trend > 0.1 else "#ffa726" if trend > 0.02 else "#66bb6a"
            st.markdown(f"""<div class="upstream-card">
              <div class="upstream-label" style="color:{color}">▲ UPSTREAM {river.upper()}</div>
              <div style="font-family:'Share Tech Mono',monospace;font-size:0.65rem;color:#263238;letter-spacing:2px;margin:2px 0">{name}</div>
              <div class="upstream-val">{f"{gauge:.2f} ft" if gauge else "—"}</div>
              <div style="font-family:'Share Tech Mono',monospace;font-size:0.7rem;color:#546e7a;letter-spacing:1px">{fmt_flow(flow)} cfs</div>
              <div class="upstream-trend" style="color:{trend_color};margin-top:6px">{trend_str}</div>
            </div>""", unsafe_allow_html=True)
        else:
            msg = "No upstream monitor" if not site else "Gauge data unavailable"
            st.markdown(f"""<div class="upstream-card">
              <div class="upstream-label" style="color:{color}">▲ UPSTREAM {river.upper()}</div>
              <div style="font-family:'Share Tech Mono',monospace;font-size:0.65rem;color:#263238;letter-spacing:2px;margin:4px 0">{name or "—"}</div>
              <div style="font-family:'Share Tech Mono',monospace;font-size:0.78rem;color:#263238;letter-spacing:2px;margin-top:8px">{msg}</div>
            </div>""", unsafe_allow_html=True)


st.markdown('<hr class="hud-hr">', unsafe_allow_html=True)


# ─── RENDER: LOCK & DAM INFO ──────────────────────────────────────────────────

st.markdown('<div class="section-label">USACE LOCKS & DAMS — NAVIGATION NOTES</div>', unsafe_allow_html=True)

lock_info = {
    "Allegheny": "8 fixed-crest dams · 72 miles navigable · Lock by calling VHF Ch. 13 or ringing bell at storm wall · Locking recommended for experienced paddlers only",
    "Monongahela": "5 gated dams · Recent: Mon Dam 3 near Elizabeth replaced by open channel (Aug 2024) · 30-mile continuous pool Braddock→Charleroi · Check lrp.usace.army.mil for closures",
    "Ohio": "1 fixed-crest + 2 gated dams · Watch for 'DANGER DAM' signs · Stay alert: dams difficult to see downriver · Hug correct shoreline ≥1 mile before lock",
}

lk1, lk2, lk3 = st.columns(3, gap="small")
for col, (river, info) in zip([lk1, lk2, lk3], lock_info.items()):
    cfg = RIVERS[river]
    with col:
        st.markdown(f"""<div class="info-panel">
          <div style="font-family:'Share Tech Mono',monospace;font-size:0.78rem;color:{cfg['color']};letter-spacing:3px">{cfg['icon']} {river.upper()}</div>
          <div style="font-family:'Barlow Condensed',sans-serif;font-size:0.88rem;color:#78909c;margin-top:6px;line-height:1.5">{info}</div>
        </div>""", unsafe_allow_html=True)


st.markdown('<hr class="hud-hr">', unsafe_allow_html=True)


# ─── RENDER: WATER QUALITY + SOURCES ─────────────────────────────────────────

wq_col, src_col = st.columns([2, 1], gap="medium")

with wq_col:
    st.markdown('<div class="section-label">WPRDC — ALLEGHENY COUNTY WATER QUALITY (RECENT LAB SAMPLES)</div>', unsafe_allow_html=True)
    if wq_records:
        df_wq = pd.DataFrame(wq_records)
        display_cols = [c for c in df_wq.columns if c not in ("_id", "_full_text")]
        st.dataframe(df_wq[display_cols].head(6), use_container_width=True, hide_index=True)
    else:
        st.markdown('<div class="info-panel"><span style="font-family:Share Tech Mono;color:#37474f;letter-spacing:3px;font-size:0.78rem;">WPRDC DATA UNAVAILABLE</span></div>', unsafe_allow_html=True)

with src_col:
    st.markdown('<div class="section-label">DATA SOURCES & REFRESH RATES</div>', unsafe_allow_html=True)
    st.markdown("""<div class="info-panel">
      <div style="font-family:'Share Tech Mono',monospace;font-size:0.72rem;color:#4FC3F7;letter-spacing:2px;line-height:2.4;">
        ● USGS NWIS — 5 min<br>
        ● Open-Meteo — 10 min<br>
        ● NWS Alerts — 10 min<br>
        ● NWPS Forecast — 15 min<br>
        ● Solunar.org — Daily<br>
        ● WPRDC CKAN — 30 min<br>
        ● ALCOSAN SOAK — 10 min
      </div>
      <div style="font-family:'Share Tech Mono',monospace;font-size:0.62rem;color:#263238;letter-spacing:2px;margin-top:10px;line-height:2.2">
        MON ◎ 03085000 · BRKP1<br>
        ALG ◎ 03049640 · PTBP1<br>
        OHI ◎ 03086000 · SEWP1<br>
        UPSTREAM ALG ◎ 03049500<br>
        UPSTREAM MON ◎ 03075070
      </div>
    </div>""", unsafe_allow_html=True)

# Auto-refresh every 5 minutes
st.markdown('<meta http-equiv="refresh" content="300">', unsafe_allow_html=True)
