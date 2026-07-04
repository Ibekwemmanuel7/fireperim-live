"""FirePerim Live REST API (FastAPI).

Wraps the existing Python pipeline and serves GeoJSON / KMZ for the React +
Mapbox front end. The processing modules in src/fireperim are unchanged; this
layer only orchestrates and serializes.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api import pipeline  # noqa: E402
from fireperim import __version__  # noqa: E402
from fireperim.config import REGIONS, SENSORS  # noqa: E402
from fireperim.export import events_to_geojson, events_to_kmz  # noqa: E402

app = FastAPI(
    title="FirePerim Live API",
    version=__version__,
    description="Satellite-derived fire events, perimeters, weather, and risk.",
)

# CORS: allow the React app (any origin by default; restrict via env in prod).
_origins = os.environ.get("CORS_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _origins == "*" else [o.strip() for o in _origins.split(",")],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _sensors_arg(sensors: str | None):
    if not sensors:
        return None
    return tuple(s.strip() for s in sensors.split(",") if s.strip() in SENSORS)


def _detections_geojson(detections) -> dict:
    """Serialize detection points to a GeoJSON dict (datetime-safe)."""
    if detections is None or len(detections) == 0:
        return {"type": "FeatureCollection", "features": []}
    gdf = detections.copy()
    for col in gdf.columns:
        if col != "geometry" and pd.api.types.is_datetime64_any_dtype(gdf[col]):
            gdf[col] = gdf[col].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    import json
    return json.loads(gdf.to_json(drop_id=True))


# ----------------------------------------------------------------- endpoints
@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "fireperim-live-api",
        "version": __version__,
        "live_data": bool(os.environ.get("FIRMS_MAP_KEY", "").strip()),
        "regions": list(REGIONS),
    }


@app.get("/api/events")
def events(
    region: str = Query("california"),
    days: int = Query(3, ge=1, le=5),
    sensors: str | None = Query(None),
    sample: bool = Query(False),
):
    """All active fire events as a GeoJSON FeatureCollection (perimeters + risk)."""
    r = pipeline.run(region_key=region, days=days, sensors=_sensors_arg(sensors), sample=sample)
    import json
    fc = json.loads(events_to_geojson(r.events))
    fc["metadata"] = {
        "mode": r.mode, "region": r.region_key,
        "event_count": len(r.events), "detection_count": len(r.detections),
    }
    return JSONResponse(fc)


@app.get("/api/detections")
def detections(
    region: str = Query("california"),
    days: int = Query(3, ge=1, le=5),
    sensors: str | None = Query(None),
    sample: bool = Query(False),
):
    """Raw VIIRS detection points as a GeoJSON FeatureCollection."""
    r = pipeline.run(region_key=region, days=days, sensors=_sensors_arg(sensors), sample=sample)
    fc = _detections_geojson(r.detections)
    fc["metadata"] = {"mode": r.mode, "region": r.region_key, "count": len(r.detections)}
    return JSONResponse(fc)


@app.get("/api/export/geojson")
def export_geojson(
    region: str = Query("california"),
    days: int = Query(3, ge=1, le=5),
    sample: bool = Query(False),
):
    """Download events as a GeoJSON file."""
    r = pipeline.run(region_key=region, days=days, sample=sample)
    return Response(
        content=events_to_geojson(r.events),
        media_type="application/geo+json",
        headers={"Content-Disposition": "attachment; filename=fireperim_events.geojson"},
    )


@app.get("/api/export/kmz")
def export_kmz(
    region: str = Query("california"),
    days: int = Query(3, ge=1, le=5),
    sample: bool = Query(False),
):
    """Download events as a KMZ file."""
    r = pipeline.run(region_key=region, days=days, sample=sample)
    return Response(
        content=events_to_kmz(r.events),
        media_type="application/vnd.google-earth.kmz",
        headers={"Content-Disposition": "attachment; filename=fireperim_events.kmz"},
    )


@app.get("/")
def root():
    return {"service": "FirePerim Live API", "docs": "/docs", "health": "/api/health"}
