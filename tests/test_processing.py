"""Tests for Day 2: DBSCAN clustering + alpha-shape perimeters."""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from fireperim.ingest.firms import FirmsSource
from fireperim.processing.cluster import EVENT_ID_COL, cluster_detections, cluster_summary
from fireperim.processing.perimeter import EVENT_COLUMNS, build_events

SAMPLE = Path(__file__).parents[1] / "data" / "sample" / "viirs_california_sample.csv"


@pytest.fixture(scope="module")
def detections() -> gpd.GeoDataFrame:
    raw = pd.read_csv(SAMPLE)
    norm = FirmsSource._normalize(raw, "VIIRS_SNPP_NRT")
    return gpd.GeoDataFrame(
        norm,
        geometry=gpd.points_from_xy(norm["longitude"], norm["latitude"]),
        crs="EPSG:4326",
    )


def test_clustering_finds_expected_fire_count(detections):
    # Sample was generated with 6 distinct fires + scattered noise.
    clustered = cluster_detections(detections, eps_m=1500, min_samples=4)
    summary = cluster_summary(clustered)
    assert 5 <= summary["n_events"] <= 7, summary
    # Noise dropped by default -> fewer rows than raw.
    assert len(clustered) < len(detections)
    # Event ids are 1-based and contiguous-ish.
    assert clustered[EVENT_ID_COL].min() >= 1


def test_event_ids_ordered_by_size(detections):
    clustered = cluster_detections(detections, eps_m=1500, min_samples=4)
    counts = clustered[EVENT_ID_COL].value_counts().sort_index()
    # Event 1 should be the largest cluster.
    assert counts.idxmax() == 1


def test_build_events_schema_and_geometry(detections):
    clustered = cluster_detections(detections, eps_m=1500, min_samples=4)
    events = build_events(clustered, alpha_per_m=0.0005)
    assert list(events.columns) == EVENT_COLUMNS + ["geometry"]
    assert events.crs.to_epsg() == 4326
    # Every event is a valid, non-empty polygon with positive area.
    assert (events.geometry.geom_type.isin(["Polygon", "MultiPolygon"])).all()
    assert events.geometry.is_valid.all()
    assert (events["area_ha"] > 0).all()
    assert (events["n_detections"] >= 4).all()


def test_empty_input_is_safe():
    from fireperim.ingest.base import DetectionSource

    empty = DetectionSource.empty()
    clustered = cluster_detections(empty)
    assert len(clustered) == 0
    events = build_events(clustered)
    assert len(events) == 0
    assert events.crs.to_epsg() == 4326


def test_tiny_cluster_uses_point_buffer():
    # Two coincident-ish points -> below alpha-shape minimum -> buffer fallback.
    pts = gpd.GeoDataFrame(
        {
            "frp_mw": [10.0, 12.0],
            "acq_datetime": pd.to_datetime(["2026-06-30", "2026-06-30"], utc=True),
            "sensor": ["VIIRS_SNPP_NRT", "VIIRS_SNPP_NRT"],
            "event_id": [1, 1],
        },
        geometry=gpd.points_from_xy([-119.50, -119.501], [37.80, 37.801]),
        crs="EPSG:4326",
    )
    events = build_events(pts)
    assert len(events) == 1
    assert events.loc[0, "perimeter_method"] == "point_buffer"
    assert events.loc[0, "area_ha"] > 0
