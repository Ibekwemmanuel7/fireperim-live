"""FirePerim Live — Streamlit entrypoint.

A satellite-data analog of the ORBIT Data Engine. ORBIT ingests thermal imagery
from airborne IR scanners; this ingests satellite thermal detections (NASA
VIIRS/FIRMS). Same downstream architecture — swap the ingestion layer and you
have ORBIT.

Day 1: live FIRMS ingestion + interactive detection map.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

# Make the src/ layout importable both locally and on Streamlit Cloud.
sys.path.insert(0, str(Path(__file__).parent / "src"))

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from fireperim import __version__
from fireperim.config import (
    DEFAULT_REGION,
    DEFAULT_SENSORS,
    REGIONS,
    SENSORS,
)
from fireperim.ingest.firms import FirmsAuthError, FirmsSource
from fireperim.ingest.base import DetectionSource
from fireperim.viz.maps import build_detection_map

st.set_page_config(
    page_title="FirePerim Live",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded",
)

SAMPLE_PATH = Path(__file__).parent / "data" / "sample" / "viirs_california_sample.csv"


# --------------------------------------------------------------------- data
@st.cache_data(ttl=300, show_spinner=False)
def load_detections(
    map_key: str,
    region_key: str,
    sensors: tuple[str, ...],
    day_range: int,
    use_sample: bool,
):
    """Fetch + cache standardized detections (5-min TTL keeps the demo 'live')."""
    region = REGIONS[region_key]
    if use_sample:
        return _load_sample(region_key), "sample"

    source = FirmsSource(
        map_key=map_key,
        bbox=region.bbox,
        sensors=sensors,
        day_range=day_range,
    )
    gdf = source.fetch()
    return gdf, "live"


def _load_sample(region_key: str):
    """Offline fallback: a cached VIIRS snapshot, run through the same normalizer."""
    if not SAMPLE_PATH.exists():
        return DetectionSource.empty()
    raw = pd.read_csv(SAMPLE_PATH)
    norm = FirmsSource._normalize(raw, "VIIRS_SNPP_NRT (sample)")
    import geopandas as gpd

    return gpd.GeoDataFrame(
        norm,
        geometry=gpd.points_from_xy(norm["longitude"], norm["latitude"]),
        crs="EPSG:4326",
    )


def get_map_key() -> str:
    try:
        return st.secrets.get("FIRMS_MAP_KEY", "")
    except Exception:
        return ""


# --------------------------------------------------------------------- UI
def sidebar():
    st.sidebar.title("🔥 FirePerim Live")
    st.sidebar.caption(f"Satellite analog of the ORBIT Data Engine · v{__version__}")

    region_key = st.sidebar.selectbox(
        "Region",
        options=list(REGIONS),
        format_func=lambda k: REGIONS[k].label,
        index=list(REGIONS).index(DEFAULT_REGION),
    )

    sensors = st.sidebar.multiselect(
        "Sensors (ingestion sources)",
        options=list(SENSORS),
        default=list(DEFAULT_SENSORS),
        format_func=lambda s: SENSORS[s],
        help="VIIRS at 375 m is the closest free analog to an airborne IR scanner.",
    )

    day_range = st.sidebar.slider(
        "Look-back window (days)", min_value=1, max_value=5, value=1,
        help="FIRMS Area API returns the most recent N days (max 5).",
    )

    base = st.sidebar.radio(
        "Base map", options=["Dark", "Satellite", "Terrain"], horizontal=True
    )

    has_key = bool(get_map_key())
    use_sample = st.sidebar.toggle(
        "Use cached sample (offline)",
        value=not has_key,
        help="No live API calls — useful if your MAP_KEY is unset or rate-limited.",
    )
    if not has_key and not use_sample:
        st.sidebar.warning("No FIRMS_MAP_KEY in secrets — falling back to sample.")
        use_sample = True

    st.sidebar.divider()
    st.sidebar.markdown(
        "**Pipeline roadmap**\n\n"
        "1. ✅ Ingest (FIRMS / VIIRS)\n"
        "2. ⏳ Cluster (DBSCAN)\n"
        "3. ⏳ Perimeters (alpha shapes)\n"
        "4. ⏳ Fire weather (Open-Meteo)\n"
        "5. ⏳ Risk score\n"
        "6. ⏳ Export (GeoJSON / KMZ)"
    )
    return region_key, tuple(sensors), day_range, base, use_sample


def header(mode: str, region_label: str):
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("FirePerim Live")
        st.caption(
            "Live satellite thermal detections → fire events → agency-ready "
            "perimeters. The downstream architecture of ORBIT, fed by VIIRS "
            "instead of an airborne IR scanner."
        )
    with col2:
        badge = "🟢 LIVE" if mode == "live" else "🟡 SAMPLE"
        st.metric("Data source", badge, region_label)


def metrics(gdf):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Detections", f"{len(gdf):,}")
    if len(gdf):
        total_frp = gdf["frp_mw"].sum(skipna=True)
        c2.metric("Total FRP", f"{total_frp:,.0f} MW")
        c3.metric("Max FRP", f"{gdf['frp_mw'].max(skipna=True):,.0f} MW")
        latest = gdf["acq_datetime"].max()
        c4.metric(
            "Latest detection",
            latest.strftime("%m-%d %H:%M") + " UTC" if pd.notna(latest) else "—",
        )
    else:
        c2.metric("Total FRP", "—")
        c3.metric("Max FRP", "—")
        c4.metric("Latest detection", "—")


# --------------------------------------------------------------------- main
def main():
    region_key, sensors, day_range, base, use_sample = sidebar()
    region = REGIONS[region_key]

    if not sensors and not use_sample:
        st.warning("Select at least one sensor in the sidebar.")
        st.stop()

    map_key = get_map_key()
    try:
        gdf, mode = load_detections(
            map_key, region_key, sensors, day_range, use_sample
        )
    except FirmsAuthError as exc:
        st.error(f"FIRMS authentication problem: {exc}")
        st.info("Toggle **Use cached sample** in the sidebar to keep exploring.")
        st.stop()
    except Exception as exc:  # noqa: BLE001
        st.exception(exc)
        st.stop()

    header(mode, region.label)
    metrics(gdf)

    if len(gdf) == 0:
        st.info(
            "No active-fire detections in this region/window right now. "
            "Try a wider look-back, a larger region, or the cached sample."
        )
        return

    fmap = build_detection_map(gdf, region, base=base)
    st_folium(fmap, use_container_width=True, height=620, returned_objects=[])

    with st.expander("Raw detections (standardized schema)"):
        st.dataframe(
            gdf.drop(columns="geometry").sort_values("frp_mw", ascending=False),
            use_container_width=True,
            height=300,
        )


if __name__ == "__main__":
    main()
