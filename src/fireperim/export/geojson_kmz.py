"""Agency-ready export: GeoJSON + KMZ.

The output side of the pipeline - the analog of ORBIT "publishing georeferenced
outputs to agency GIS systems". Fire perimeters plus their stats, weather, and
risk are written as:

  * GeoJSON  - the lingua franca for web GIS / ArcGIS / QGIS / ICS dashboards.
  * KMZ      - zipped KML for Google Earth and many field situational-awareness
               tools; polygons are styled by spread-risk color.

Both are produced in-memory (bytes/str) so Streamlit can serve them as direct
downloads with no temp files.
"""
from __future__ import annotations

import io
import zipfile
from datetime import datetime, timezone

import pandas as pd

# Risk -> KML color (KML uses aabbggrr hex). ~55% alpha fill.
_RISK_KML = {
    "Low": "8c5b9e2e",       # green
    "Moderate": "8c3ab4e0",  # amber
    "High": "8c2b55e8",      # orange
    "Extreme": "8c1c1cb7",   # red
    "Unknown": "8c888888",
}
_RISK_RGB = {  # for KML line color (solid)
    "Low": "ff5b9e2e", "Moderate": "ff3ab4e0", "High": "ff2b55e8",
    "Extreme": "ff1c1cb7", "Unknown": "ff888888",
}

_EMPTY_FC = '{"type": "FeatureCollection", "features": []}'


def events_to_geojson(events) -> str:
    """Serialize events (perimeters + properties) to a GeoJSON string."""
    if events is None or len(events) == 0:
        return _EMPTY_FC
    gdf = events.copy()
    # Make datetimes JSON-safe (ISO 8601 UTC).
    for col in gdf.columns:
        if col == "geometry":
            continue
        if pd.api.types.is_datetime64_any_dtype(gdf[col]):
            gdf[col] = gdf[col].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return gdf.to_json(drop_id=True)


def events_to_kmz(events) -> bytes:
    """Serialize events to KMZ (zipped KML) with risk-styled polygons."""
    kml_str = _build_kml(events)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("doc.kml", kml_str)
    return buf.getvalue()


# ----------------------------------------------------------------- internals
def _build_kml(events) -> str:
    import simplekml

    kml = simplekml.Kml()
    kml.document.name = "FirePerim Live - Fire Events"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    kml.document.description = f"Satellite-derived fire perimeters. Generated {stamp}."

    if events is not None:
        for _, ev in events.iterrows():
            geom = ev.geometry
            if geom is None or geom.is_empty:
                continue
            polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
            risk = ev.get("risk_class", "Unknown")
            for poly in polys:
                pol = kml.newpolygon(name=str(ev.get("label", "Fire event")))
                pol.outerboundaryis = list(poly.exterior.coords)
                if list(poly.interiors):
                    pol.innerboundaryis = [list(r.coords) for r in poly.interiors]
                pol.style.polystyle.color = _RISK_KML.get(risk, _RISK_KML["Unknown"])
                pol.style.polystyle.fill = 1
                pol.style.linestyle.color = _RISK_RGB.get(risk, _RISK_RGB["Unknown"])
                pol.style.linestyle.width = 2
                pol.description = _kml_description(ev)
    return kml.kml()


def _kml_description(ev) -> str:
    def g(k):
        v = ev.get(k)
        return "-" if v is None or (isinstance(v, float) and v != v) else v

    def num(k):
        v = ev.get(k)
        try:
            return f"{float(v):.1f}"
        except (TypeError, ValueError):
            return "-"

    return (
        f"Detections: {g('n_detections')}\n"
        f"Area: {num('area_ha')} ha\n"
        f"Perimeter: {num('perimeter_km')} km\n"
        f"Total FRP: {num('total_frp_mw')} MW\n"
        f"Spread risk: {g('risk_class')} ({num('risk_score')})\n"
        f"Wind: {num('wind_speed_ms')} m/s @ {num('wind_dir_deg')} deg\n"
        f"RH: {num('rh_pct')} %   Temp: {num('temp_c')} C\n"
        f"Sensors: {g('sensors')}"
    )
