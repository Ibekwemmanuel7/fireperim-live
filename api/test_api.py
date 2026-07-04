"""Endpoint tests for the FastAPI service (sample mode, no network needed)."""
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_events_is_featurecollection():
    r = client.get("/api/events", params={"sample": True})
    assert r.status_code == 200
    fc = r.json()
    assert fc["type"] == "FeatureCollection"
    assert fc["metadata"]["event_count"] == len(fc["features"]) == 6
    props = fc["features"][0]["properties"]
    assert "risk_class" in props and "area_ha" in props


def test_detections_is_featurecollection():
    r = client.get("/api/detections", params={"sample": True})
    assert r.status_code == 200
    fc = r.json()
    assert fc["type"] == "FeatureCollection"
    assert fc["metadata"]["count"] == 188
    assert fc["features"][0]["geometry"]["type"] == "Point"


def test_export_geojson_download():
    r = client.get("/api/export/geojson", params={"sample": True})
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    assert r.json()["type"] == "FeatureCollection"


def test_export_kmz_download():
    r = client.get("/api/export/kmz", params={"sample": True})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/vnd.google-earth.kmz"
    assert r.content[:2] == b"PK"  # zip magic
