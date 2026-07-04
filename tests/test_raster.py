"""Tests for the airborne raster track (skipped if rasterio isn't installed)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("rasterio")  # raster deps are optional (offline build only)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from raster import airborne as A
from fireperim.ingest.base import DETECTION_COLUMNS
from fireperim.processing import build_events, cluster_detections


def test_synthesize_frame_shape_and_crs():
    bt, transform, crs = A.synthesize_thermal_frame(size_px=120)
    assert bt.shape == (120, 120)
    assert crs.to_epsg() == 32611  # UTM 11N for the CA test location
    assert bt.max() > A.ACTIVE_FIRE_K  # contains active fire


def test_extract_perimeter_from_raster():
    bt, transform, crs = A.synthesize_thermal_frame(size_px=200)
    gdf, stats = A.extract_perimeter(bt, transform, crs)
    assert len(gdf) == 1
    assert gdf.crs.to_epsg() == 4326
    assert gdf.geometry.iloc[0].geom_type in ("Polygon", "MultiPolygon")
    assert gdf.geometry.is_valid.all()
    assert stats["area_ha"] > 0 and stats["hot_pixels"] > 0


def test_reproject_to_4326_bounds():
    bt, transform, crs = A.synthesize_thermal_frame(size_px=150)
    arr, tr, bounds = A.reproject_to_4326(bt, transform, crs)
    assert bounds["west"] < bounds["east"] and bounds["south"] < bounds["north"]
    assert -120.5 < bounds["west"] < -118.5


def test_frame_emits_standardized_detections_and_flows_through_pipeline():
    bt, transform, crs = A.synthesize_thermal_frame(size_px=200)
    dets = A.frame_to_detections(bt, transform, crs)
    # the airborne frame speaks the SAME schema as the FIRMS client
    assert list(dets.columns) == list(DETECTION_COLUMNS) + ["geometry"]
    assert (dets["sensor"] == "AIRBORNE_IR (sim)").all()
    # and it runs through the satellite pipeline unchanged
    events = build_events(cluster_detections(dets, eps_m=200, min_samples=4),
                          alpha_per_m=0.02)
    assert len(events) >= 1
