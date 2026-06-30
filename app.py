"""FirePerim Live - Streamlit entrypoint.

A satellite-data analog of the ORBIT Data Engine. ORBIT ingests thermal imagery
from airborne IR scanners; this ingests satellite thermal detections (NASA
VIIRS/FIRMS). Same downstream architecture - swap the ingestion layer and you
have ORBIT.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from fireperim import __version__
from fireperim.config import DEFAULT_REGION, DEFAULT_SENSORS, REGIONS, SENSORS
from fireperim.ingest.firms import FirmsAuthError, FirmsSource
from fireperim.ingest.base import DetectionSource
from fireperim.processing import build_events, cluster_detections
from fireperim.processing.risk import enrich_events
from fireperim.weather import fetch_weather
from fireperim.viz.maps import build_detection_map

st.set_page_config(page_title="FirePerim Live", page_icon="🔥", layout="wide",
                   initial_sidebar_state="expanded")

SAMPLE_PATH = Path(__file__).parent / "data" / "sample" / "viirs_california_sample.csv"


@st.cache_data(ttl=300, show_spinner=False)
def load_detections(map_key, region_key, sensors, day_range, use_sample):
    """Fetch + cache standardized detections (5-min TTL keeps the demo 'live')."""
    region = REGIONS[region_key]
    if use_sample:
        return _load_sample(region_key), "sample"
    source = FirmsSource(map_key=map_key, bbox=region.bbox, sensors=sensors,
                         day_range=day_range)
    return source.fetch(), "live"


def _load_sample(region_key):
    """Offline fallback: a cached VIIRS snapshot, via the same normalizer."""
    if not SAMPLE_PATH.exists():
        return DetectionSource.empty()
    raw = pd.read_csv(SAMPLE_PATH)
    norm = FirmsSource._normalize(raw, "VIIRS_SNPP_NRT (sample)")
    import geopandas as gpd
    return gpd.GeoDataFrame(
        norm, geometry=gpd.points_from_xy(norm["longitude"], norm["latitude"]),
        crs="EPSG:4326")


@st.cache_data(ttl=900, show_spinner=False)
def load_weather(points):
    """Current weather per event centroid (15-min cache). Key-less Open-Meteo."""
    return fetch_weather(list(points))


def get_map_key():
    try:
        return st.secrets.get("FIRMS_MAP_KEY", "")
    except Exception:
        return ""


def sidebar():
    st.sidebar.title("🔥 FirePerim Live")
    st.sidebar.caption(f"Satellite analog of the ORBIT Data Engine - v{__version__}")
    region_key = st.sidebar.selectbox("Region", options=list(REGIONS),
        format_func=lambda k: REGIONS[k].label,
        index=list(REGIONS).index(DEFAULT_REGION))
    sensors = st.sidebar.multiselect("Sensors (ingestion sources)",
        options=list(SENSORS), default=list(DEFAULT_SENSORS),
        format_func=lambda s: SENSORS[s],
        help="VIIRS at 375 m is the closest free analog to an airborne IR scanner.")
    day_range = st.sidebar.slider("Look-back window (days)", 1, 5, 3,
        help="FIRMS Area API returns the most recent N days (max 5).")
    base = st.sidebar.radio("Base map", options=["Dark", "Satellite", "Terrain"],
        horizontal=True)
    with st.sidebar.expander("Clustering & perimeters", expanded=False):
        eps_km = st.slider("DBSCAN radius (km)", 0.5, 5.0, 1.5, 0.5,
            help="Max distance between detections in the same fire event.")
        min_samples = st.slider("Min detections per event", 2, 10, 5, 1,
            help="Fewer than this within the radius = noise, not a fire.")
        alpha = st.slider("Alpha (perimeter tightness)", 0.0, 0.002, 0.0005, 0.0001,
            format="%.4f", help="0 = convex hull; higher = tighter perimeter.")
    cluster_params = {"eps_m": eps_km * 1000.0, "min_samples": min_samples, "alpha": alpha}
    has_key = bool(get_map_key())
    use_sample = st.sidebar.toggle("Use cached sample (offline)", value=not has_key,
        help="No live API calls - useful if your MAP_KEY is unset or rate-limited.")
    if not has_key and not use_sample:
        st.sidebar.warning("No FIRMS_MAP_KEY in secrets - falling back to sample.")
        use_sample = True
    st.sidebar.divider()
    st.sidebar.markdown(
        "**Pipeline roadmap**\n\n1. ✅ Ingest (FIRMS / VIIRS)\n2. ✅ Cluster (DBSCAN)\n"
        "3. ✅ Perimeters (alpha shapes)\n4. ✅ Fire weather (Open-Meteo)\n"
        "5. ✅ Risk score\n6. ⏳ Export (GeoJSON / KMZ)")
    return region_key, tuple(sensors), day_range, base, use_sample, cluster_params


def header(mode, region_label):
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("FirePerim Live")
        st.caption("Live satellite thermal detections -> fire events -> agency-ready "
                   "perimeters. The downstream architecture of ORBIT, fed by VIIRS "
                   "instead of an airborne IR scanner.")
    with col2:
        badge = "🟢 LIVE" if mode == "live" else "🟡 SAMPLE"
        st.metric("Data source", badge, region_label)


def metrics(gdf, events):
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Detections", f"{len(gdf):,}")
    c2.metric("Fire events", f"{len(events):,}")
    total_area = events["area_ha"].sum() if len(events) else 0.0
    c3.metric("Total area", f"{total_area:,.0f} ha")
    c4.metric("Total FRP", f"{gdf['frp_mw'].sum(skipna=True):,.0f} MW" if len(gdf) else "-")
    if len(events) and "risk_score" in events.columns and events["risk_score"].notna().any():
        top = events.loc[events["risk_score"].idxmax()]
        elevated = int((events["risk_class"].isin(["High", "Extreme"])).sum())
        c5.metric("Top spread risk", f"{top['risk_class']} ({top['risk_score']:.0f})",
                  f"{elevated} elevated" if elevated else None)
    else:
        c5.metric("Top spread risk", "-")


def main():
    region_key, sensors, day_range, base, use_sample, cparams = sidebar()
    region = REGIONS[region_key]
    if not sensors and not use_sample:
        st.warning("Select at least one sensor in the sidebar.")
        st.stop()
    map_key = get_map_key()
    try:
        gdf, mode = load_detections(map_key, region_key, sensors, day_range, use_sample)
    except FirmsAuthError as exc:
        st.error(f"FIRMS authentication problem: {exc}")
        st.info("Toggle **Use cached sample** in the sidebar to keep exploring.")
        st.stop()
    except Exception as exc:
        st.exception(exc)
        st.stop()
    clustered = cluster_detections(gdf, eps_m=cparams["eps_m"],
                                   min_samples=cparams["min_samples"])
    events = build_events(clustered, alpha_per_m=cparams["alpha"])
    if len(events):
        pts = tuple((float(r.centroid_lat), float(r.centroid_lon))
                    for r in events.itertuples())
        events = enrich_events(events, load_weather(pts))
    header(mode, region.label)
    metrics(gdf, events)
    if len(gdf) == 0:
        st.info("No active-fire detections in this region/window right now. "
                "Try a wider look-back, a larger region, or the cached sample.")
        return
    fmap = build_detection_map(gdf, region, base=base, events=events)
    st_folium(fmap, use_container_width=True, height=620, returned_objects=[])
    if len(events):
        st.subheader(f"🔥 {len(events)} fire events")
        st.caption("DBSCAN groups detections into events; alpha shapes trace each "
                   "perimeter. Agency-ready GeoJSON/KMZ export lands on Day 4.")
        show = events.drop(columns="geometry").copy()
        round_cols = ["total_frp_mw", "max_frp_mw", "mean_frp_mw", "area_ha",
                      "perimeter_km", "risk_score", "wind_speed_ms", "wind_dir_deg",
                      "rh_pct", "temp_c", "wind_gust_ms"]
        for col in round_cols:
            if col in show.columns:
                show[col] = show[col].round(1)
        order = ["label", "risk_class", "risk_score", "wind_speed_ms", "wind_dir_deg",
                 "rh_pct", "temp_c", "n_detections", "area_ha", "perimeter_km",
                 "total_frp_mw", "max_frp_mw", "first_seen", "last_seen", "sensors"]
        order = [c for c in order if c in show.columns]
        st.dataframe(show.set_index("event_id")[order[1:] if order and order[0] == "label" else order],
                     use_container_width=True)
    else:
        st.info("Detections found, but none dense enough to form a fire event at the "
                "current settings. Lower 'Min detections per event' or widen the radius.")
    with st.expander("Raw detections (standardized schema)"):
        st.dataframe(gdf.drop(columns="geometry").sort_values("frp_mw", ascending=False),
                     use_container_width=True, height=300)


if __name__ == "__main__":
    main()
