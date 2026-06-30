"""Tests for Day 3: Open-Meteo weather parsing + spread-risk scoring."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import geopandas as gpd

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from fireperim.weather.open_meteo import fetch_weather, parse_current
from fireperim.processing.risk import (
    enrich_events, risk_class, spread_risk_score,
)


def test_score_monotonic_in_wind():
    low = spread_risk_score(25, 40, 2)
    high = spread_risk_score(25, 40, 12)
    assert high > low
    assert 0 <= low <= 100 and 0 <= high <= 100


def test_score_dry_hot_windy_is_extreme():
    s = spread_risk_score(40, 5, 15)
    assert s >= 75
    assert risk_class(s)[0] == "Extreme"


def test_score_calm_humid_is_low():
    s = spread_risk_score(12, 90, 0.5)
    assert s < 25
    assert risk_class(s)[0] == "Low"


def test_score_none_when_no_data():
    assert spread_risk_score(None, None, None) is None
    assert risk_class(None)[0] == "Unknown"


def test_parse_current_handles_full_and_missing():
    item = {"current": {"temperature_2m": 30.0, "relative_humidity_2m": 18,
                        "wind_speed_10m": 7.5, "wind_direction_10m": 220,
                        "wind_gusts_10m": 12.0}}
    w = parse_current(item)
    assert w["temp_c"] == 30.0 and w["wind_dir_deg"] == 220.0
    assert parse_current({}) is None
    assert parse_current({"current": {}}) is None


class _FakeResp:
    def __init__(self, payload):
        self._p = payload
    def raise_for_status(self):
        pass
    def json(self):
        return self._p


class _FakeSession:
    def __init__(self, payload):
        self._p = payload
    def get(self, *a, **k):
        return _FakeResp(self._p)


def test_fetch_weather_aligns_multiple_points():
    payload = [
        {"current": {"temperature_2m": 30, "relative_humidity_2m": 20,
                     "wind_speed_10m": 8, "wind_direction_10m": 200, "wind_gusts_10m": 11}},
        {"current": {"temperature_2m": 22, "relative_humidity_2m": 60,
                     "wind_speed_10m": 3, "wind_direction_10m": 90, "wind_gusts_10m": 5}},
    ]
    out = fetch_weather([(37.0, -120.0), (40.0, -122.0)], session=_FakeSession(payload))
    assert len(out) == 2
    assert out[0]["temp_c"] == 30.0 and out[1]["wind_dir_deg"] == 90.0


def test_fetch_weather_single_dict_response():
    payload = {"current": {"temperature_2m": 25, "relative_humidity_2m": 30,
                           "wind_speed_10m": 5, "wind_direction_10m": 180, "wind_gusts_10m": 7}}
    out = fetch_weather([(37.0, -120.0)], session=_FakeSession(payload))
    assert len(out) == 1 and out[0]["temp_c"] == 25.0


def test_fetch_weather_failure_degrades_to_none():
    class Boom:
        def get(self, *a, **k):
            raise RuntimeError("network down")
    out = fetch_weather([(1, 2), (3, 4)], session=Boom())
    assert out == [None, None]


def test_enrich_events_adds_risk_columns():
    events = gpd.GeoDataFrame(
        {"event_id": [1, 2], "centroid_lat": [37.0, 40.0],
         "centroid_lon": [-120.0, -122.0]},
        geometry=gpd.points_from_xy([-120.0, -122.0], [37.0, 40.0]), crs="EPSG:4326")
    weather = [
        {"temp_c": 40, "rh_pct": 8, "wind_speed_ms": 14, "wind_dir_deg": 210, "wind_gust_ms": 20},
        {"temp_c": 15, "rh_pct": 85, "wind_speed_ms": 1, "wind_dir_deg": 10, "wind_gust_ms": 2},
    ]
    out = enrich_events(events, weather)
    assert "risk_score" in out.columns and "risk_class" in out.columns
    assert out.loc[0, "risk_class"] in ("High", "Extreme")
    assert out.loc[1, "risk_class"] == "Low"
