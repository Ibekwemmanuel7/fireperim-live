"""Fire spread-risk scoring (Day 3).

A transparent, weather-driven 0-100 spread-risk index per fire event. Wind is
the dominant driver of fire spread, with low humidity and high temperature
amplifying it. Deliberately simple and explainable - an operator (or
interviewer) can read the formula and agree with it. It is NOT a calibrated
fire-danger index; it is an operational triage signal.
"""
from __future__ import annotations

# (threshold, label, color) ascending. Color used for map + table.
RISK_BANDS = [
    (0, "Low", "#2E9E5B"),
    (25, "Moderate", "#E0B43A"),
    (50, "High", "#E8552B"),
    (75, "Extreme", "#B71C1C"),
]
UNKNOWN = ("Unknown", "#888888")


def spread_risk_score(temp_c, rh_pct, wind_speed_ms):
    """Return a 0-100 spread-risk score from current weather (or None).

    Weights: wind 55%, dryness 30%, heat 15%. Each component is normalized to
    0-1 over an operationally meaningful range.
    """
    if temp_c is None and rh_pct is None and wind_speed_ms is None:
        return None
    wind = wind_speed_ms if wind_speed_ms is not None else 0.0
    rh = rh_pct if rh_pct is not None else 50.0
    temp = temp_c if temp_c is not None else 20.0

    wind_score = _clamp(wind / 15.0)        # ~15 m/s (~34 mph) -> max
    dryness_score = _clamp((45.0 - rh) / 45.0)  # RH<45% dry; ~0% -> max
    heat_score = _clamp((temp - 15.0) / 25.0)   # 15C..40C

    score = 100.0 * (0.55 * wind_score + 0.30 * dryness_score + 0.15 * heat_score)
    return round(float(score), 1)


def risk_class(score):
    """Map a score to (label, color)."""
    if score is None:
        return UNKNOWN
    label, color = RISK_BANDS[0][1], RISK_BANDS[0][2]
    for thr, lbl, clr in RISK_BANDS:
        if score >= thr:
            label, color = lbl, clr
    return label, color


def enrich_events(events, weather_list):
    """Attach weather + risk columns to an events GeoDataFrame (positional join)."""
    events = events.copy()
    keys = ["temp_c", "rh_pct", "wind_speed_ms", "wind_dir_deg", "wind_gust_ms",
            "risk_score", "risk_class"]
    cols = {k: [] for k in keys}
    for i in range(len(events)):
        w = weather_list[i] if i < len(weather_list) and weather_list[i] else {}
        t, rh, ws = w.get("temp_c"), w.get("rh_pct"), w.get("wind_speed_ms")
        score = spread_risk_score(t, rh, ws)
        label, _ = risk_class(score)
        cols["temp_c"].append(t)
        cols["rh_pct"].append(rh)
        cols["wind_speed_ms"].append(ws)
        cols["wind_dir_deg"].append(w.get("wind_dir_deg"))
        cols["wind_gust_ms"].append(w.get("wind_gust_ms"))
        cols["risk_score"].append(score)
        cols["risk_class"].append(label)
    for k, v in cols.items():
        events[k] = v
    return events


def _clamp(x):
    return max(0.0, min(1.0, x))
