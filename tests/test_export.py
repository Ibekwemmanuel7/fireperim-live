"""Tests for Day 4: GeoJSON + KMZ export."""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from fireperim.ingest.firms import FirmsSource
from fireperim.processing import build_events, cluster_detections
from fireperim.processing.risk import enrich_events
from fireperim.export import events_to_geojson, events_to_kmz

SAMPLE = Path(__file__).parents[1] / "data" / "sample" / "viirs_california_sample.csv"


def _events():
    raw = pd.read_csv(SAMPLE)
    norm = FirmsSource._normalize(raw, "VIIRS_SNPP_NRT")
    gdf = gpd.GeoDataFrame(
        norm, geometry=gpd.points_from_xy(norm["longitude"], norm["latitude"]),
        crs="EPSG:4326")
    ev = build_events(cluster_detections(gdf, eps_m=1500, min_samples=4))
    wx = [{"temp_c": 33, "rh_pct": 15, "wind_speed_ms": 9, "wind_dir_deg": 210,
           "wind_gust_ms": 14}] * len(ev)
    return enrich_events(ev, wx)


def test_geojson_is_valid_featurecollection():
    fc = json.loads(events_to_geojson(_events()))
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 6
    f0 = fc["features"][0]
    assert f0["geometry"]["type"] in ("Polygon", "MultiPolygon")
    props = f0["properties"]
    assert "risk_class" in props and "area_ha" in props
    # datetimes serialized as ISO strings, not raw timestamps
    assert isinstance(props["first_seen"], str) and props["first_seen"].endswith("Z")


def test_geojson_empty_is_safe():
    fc = json.loads(events_to_geojson(None))
    assert fc["features"] == []


def test_kmz_is_valid_zip_with_polygons():
    kmz = events_to_kmz(_events())
    assert isinstance(kmz, bytes) and len(kmz) > 0
    with zipfile.ZipFile(io.BytesIO(kmz)) as z:
        assert "doc.kml" in z.namelist()
        doc = z.read("doc.kml").decode("utf-8")
    assert "<Polygon" in doc
    assert "Spread risk" in doc  # description embedded
    assert "FirePerim Live" in doc
