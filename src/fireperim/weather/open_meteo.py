"""Open-Meteo fire-weather client.

Pulls current wind (speed/direction/gusts), relative humidity, and temperature
for each fire event centroid. Open-Meteo is free and key-less.

Requests are made per-point (single-location `current` calls are the most
reliable form of the API). Network/parse failures degrade gracefully to None so
the app still shows perimeters, just without risk.
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

WEATHER_COLUMNS = ["temp_c", "rh_pct", "wind_speed_ms", "wind_dir_deg", "wind_gust_ms"]
MAX_POINTS = 40  # safety cap on per-request work


def _params(lat, lon):
    return {
        "latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}",
        "current": _CURRENT_VARS, "wind_speed_unit": "ms", "timezone": "UTC",
    }


def fetch_one(lat, lon, session, timeout=10):
    """Fetch current weather for a single point; returns dict or None."""
    r = session.get(OPEN_METEO_URL, params=_params(lat, lon), timeout=timeout)
    r.raise_for_status()
    return parse_current(r.json())


def fetch_weather(points, timeout=10, session=None):
    """Current weather per (lat, lon); list aligned to input (None on failure)."""
    if not points:
        return []
    sess = session or requests.Session()
    out = []
    for i, (lat, lon) in enumerate(points):
        if i >= MAX_POINTS:
            out.append(None)
            continue
        try:
            out.append(fetch_one(lat, lon, sess, timeout))
        except Exception as exc:  # noqa: BLE001 - degrade gracefully
            log.warning("Open-Meteo fetch failed at (%s,%s): %s", lat, lon, exc)
            out.append(None)
    return out


def parse_current(item):
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


def debug_fetch(lat=37.85, lon=-119.55, timeout=10):
    """Diagnostic: raw reachability check for a single point."""
    try:
        r = requests.get(OPEN_METEO_URL, params=_params(lat, lon), timeout=timeout)
        return {
            "ok": r.status_code == 200,
            "status_code": r.status_code,
            "parsed": parse_current(r.json()) if r.status_code == 200 else None,
            "body_preview": r.text[:300],
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": repr(exc)}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
