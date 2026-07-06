"""Pipeline orchestration for the API.

Reuses the existing fireperim modules unchanged (ingest -> cluster -> perimeter
-> weather -> risk) and exposes a single cached run() returning the detections
and enriched events as GeoDataFrames. The Streamlit app and this API share the
exact same processing core.
"""
from __future__ import annotations

import os
import sys
import time
import threading
from pathlib import Path

import geopandas as gpd
import pandas as pd

# Make src/ importable whether run from repo root or the api/ dir.
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from fireperim.config import DEFAULT_SENSORS, REGIONS  # noqa: E402
from fireperim.ingest.base import DetectionSource  # noqa: E402
from fireperim.ingest.firms import FirmsAuthError, FirmsSource  # noqa: E402
from fireperim.processing import build_events, cluster_detections  # noqa: E402
from fireperim.processing.risk import enrich_events  # noqa: E402
from fireperim.weather import fetch_weather  # noqa: E402

SAMPLE_PATH = _ROOT / "data" / "sample" / "viirs_california_sample.csv"

# ----------------------------------------------------------------- result type
class PipelineResult:
    def __init__(self, detections, events, mode, region_key):
        self.detections = detections
        self.events = events
        self.mode = mode            # "live" | "sample"
        self.region_key = region_key


# ------------------------------------------------------------------ tiny cache
_CACHE: dict[tuple, tuple[float, PipelineResult]] = {}
_CACHE_TTL = 900  # 15 minutes
_LOCK = threading.Lock()


def _map_key() -> str:
    return os.environ.get("FIRMS_MAP_KEY", "").strip()


def _load_sample() -> gpd.GeoDataFrame:
    if not SAMPLE_PATH.exists():
        return DetectionSource.empty()
    raw = pd.read_csv(SAMPLE_PATH)
    norm = FirmsSource._normalize(raw, "VIIRS_SNPP_NRT (sample)")
    return gpd.GeoDataFrame(
        norm, geometry=gpd.points_from_xy(norm["longitude"], norm["latitude"]),
        crs="EPSG:4326")


def run(region_key="california", days=3, sensors=None, sample=False,
        eps_m=1500.0, min_samples=5, alpha=0.0005) -> PipelineResult:
    """Run (or serve cached) the full pipeline. Falls back to sample with no key."""
    if region_key not in REGIONS:
        region_key = "california"
    sensors = tuple(sensors) if sensors else tuple(DEFAULT_SENSORS)
    use_sample = sample or not _map_key()

    key = (region_key, days, sensors, use_sample, eps_m, min_samples, round(alpha, 5))
    now = time.time()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < _CACHE_TTL:
            return hit[1]

    region = REGIONS[region_key]
    if use_sample:
        detections = _load_sample()
        mode = "sample"
    else:
        detections = FirmsSource(
            map_key=_map_key(), bbox=region.bbox, sensors=sensors,
            day_range=days).fetch()
        mode = "live"

    clustered = cluster_detections(detections, eps_m=eps_m, min_samples=min_samples)
    events = build_events(clustered, alpha_per_m=alpha)
    if len(events):
        pts = tuple((float(r.centroid_lat), float(r.centroid_lon))
                    for r in events.itertuples())
        events = enrich_events(events, fetch_weather(list(pts)))

    result = PipelineResult(detections, events, mode, region_key)
    with _LOCK:
        _CACHE[key] = (now, result)
    return result


__all__ = ["run", "PipelineResult", "FirmsAuthError"]
