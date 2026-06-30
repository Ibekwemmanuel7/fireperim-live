"""Open-Meteo fire-weather client.

Pulls current wind (speed/direction/gusts), relative humidity, and temperature
for each fire event's centroid. Open-Meteo is free and key-less, and accepts
comma-separated coordinates, so every event is enriched in a single request.

This is the same "fuse external context onto the incident" step ORBIT needs to
turn a bare perimeter into an operational picture.
"""
from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
_CURRENT_VARS = (
    "temperature_2m,relative_humidity_2m,"
    "wind_speed_10m,wind_direction_10m,wind_gusts_10m"
)

# Standardized weather fields attached to each event.
WEATHER_COLUMNS = ["temp_c", "rh_pct", "wind_speed_ms", "wind_dir_deg", "wind_gust_ms"]


def fetch_weather(points, timeout: int = 30, session=None):
    """Fetch current weather for a list of (lat, lon) points.

    Returns a list aligned to `points`; each item is a dict with WEATHER_COLUMNS
    or None if that point could not be resolved. Network/parse failures degrade
    gracefully to all-None (the app still shows perimeters, just no risk).
    """
    if not points:
        return []
    sess = session or requests
    lats = ",".join(f"{lat:.4f}" for lat, _ in points)
    lons = ",".join(f"{lon:.4f}" for _, lon in points)
    try:
        r = sess.get(
            OPEN_METEO_URL,
            params={
                "latitude": lats, "longitude": lons, "current": _CURRENT_VARS,
                "wind_speed_unit": "ms", "timezone": "UTC",
            },
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as exc:  # noqa: BLE001 - degrade gracefully
        log.warning("Open-Meteo fetch failed: %s", exc)
        return [None] * len(points)

    # Single coordinate -> dict; multiple -> list. Normalize to list.
    if isinstance(data, dict):
        data = [data]
    out = [parse_current(item) for item in data]
    while len(out) < len(points):
        out.append(None)
    return out[: len(points)]


def parse_current(item) -> dict | None:
    """Map an Open-Meteo response object to the standardized weather dict."""
    if not isinstance(item, dict):
        return None
    cur = item.get("current") or {}
    if not cur:
        return None
    return {
        "temp_c": _num(cur.get("temperature_2m")),
        "rh_pct": _num(cur.get("relative_humidity_2m")),
        "wind_speed_ms": _num(cur.get("wind_speed_10m")),
        "wind_dir_deg": _num(cur.get("wind_direction_10m")),
        "wind_gust_ms": _num(cur.get("wind_gusts_10m")),
    }


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
