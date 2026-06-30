"""Folium map construction.

Day 1: detection points styled by Fire Radiative Power (FRP). Later days layer
perimeter polygons and wind arrows on top of this same base map.
"""
from __future__ import annotations

import folium
import geopandas as gpd

from fireperim.config import Region

# FRP -> color ramp (MW). Coarse but readable at a glance during a demo.
_FRP_BANDS = [
    (0, "#FFE08A", "0–5 MW"),
    (5, "#FFB24C", "5–20 MW"),
    (20, "#FF7A33", "20–50 MW"),
    (50, "#E8552B", "50–100 MW"),
    (100, "#B71C1C", "100+ MW"),
]

_BASE_TILES = {
    "Dark": ("CartoDB dark_matter", "CartoDB dark_matter"),
    "Satellite": (
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "Esri World Imagery",
    ),
    "Terrain": ("CartoDB positron", "CartoDB positron"),
}


def _frp_color(frp: float | None) -> str:
    if frp is None or frp != frp:  # NaN
        return _FRP_BANDS[0][1]
    color = _FRP_BANDS[0][1]
    for threshold, c, _label in _FRP_BANDS:
        if frp >= threshold:
            color = c
    return color


def _radius(frp: float | None) -> float:
    if frp is None or frp != frp:
        return 3.0
    # sqrt scaling keeps big fires from swamping the map
    return max(3.0, min(12.0, 2.5 + (float(frp) ** 0.5)))


def build_detection_map(
    detections: gpd.GeoDataFrame,
    region: Region,
    base: str = "Dark",
) -> folium.Map:
    """Render detection points on a Folium map centered on `region`."""
    tiles, attr = _BASE_TILES.get(base, _BASE_TILES["Dark"])
    fmap = folium.Map(
        location=list(region.center),
        zoom_start=region.zoom,
        tiles=tiles,
        attr=attr,
        control_scale=True,
    )

    # Add the other base layers as toggles for the live demo.
    for name, (t, a) in _BASE_TILES.items():
        if name != base:
            folium.TileLayer(t, attr=a, name=name).add_to(fmap)

    detect_layer = folium.FeatureGroup(name=f"Detections ({len(detections)})")
    for _, row in detections.iterrows():
        frp = row.get("frp_mw")
        popup = folium.Popup(_popup_html(row), max_width=260)
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=_radius(frp),
            color=_frp_color(frp),
            weight=0.5,
            fill=True,
            fill_color=_frp_color(frp),
            fill_opacity=0.8,
            popup=popup,
            tooltip=f"{row.get('sensor', '')} · FRP {_fmt(frp)} MW",
        ).add_to(detect_layer)
    detect_layer.add_to(fmap)

    _add_legend(fmap)
    folium.LayerControl(collapsed=True).add_to(fmap)
    return fmap


def _fmt(v) -> str:
    if v is None or v != v:
        return "—"
    return f"{float(v):.1f}"


def _popup_html(row) -> str:
    dt = row.get("acq_datetime")
    dt_str = dt.strftime("%Y-%m-%d %H:%M UTC") if dt is not None and dt == dt else "—"
    return f"""
    <div style="font-family: sans-serif; font-size: 12px; line-height: 1.4;">
      <b>{row.get('sensor', 'detection')}</b><br>
      <b>Time:</b> {dt_str}<br>
      <b>FRP:</b> {_fmt(row.get('frp_mw'))} MW<br>
      <b>Brightness:</b> {_fmt(row.get('brightness_k'))} K<br>
      <b>Confidence:</b> {row.get('confidence_class', '—')}
      ({_fmt(row.get('confidence'))})<br>
      <b>Day/Night:</b> {row.get('daynight', '—')}<br>
      <b>Lat/Lon:</b> {_fmt(row.get('latitude'))}, {_fmt(row.get('longitude'))}
    </div>
    """


def _add_legend(fmap: folium.Map) -> None:
    rows = "".join(
        f'<div style="margin:2px 0;"><span style="display:inline-block;width:12px;'
        f'height:12px;background:{c};border-radius:50%;margin-right:6px;"></span>'
        f"{label}</div>"
        for _t, c, label in _FRP_BANDS
    )
    html = f"""
    <div style="position: fixed; bottom: 24px; left: 24px; z-index: 9999;
        background: rgba(20,22,28,0.9); color: #fafafa; padding: 10px 12px;
        border-radius: 8px; font-family: sans-serif; font-size: 12px;
        border: 1px solid #333;">
      <b>Fire Radiative Power</b>{rows}
    </div>
    """
    fmap.get_root().html.add_child(folium.Element(html))
