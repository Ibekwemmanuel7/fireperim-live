"""DBSCAN clustering — group raw detections into distinct fire events.

This is the first real processing stage and the direct analog of how ORBIT
would separate concurrent incidents in a scan: nearby hot detections belong to
the same fire; isolated ones are noise. We cluster in a projected CRS (meters)
so `eps` is a real ground distance, not degrees.
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
from sklearn.cluster import DBSCAN

from fireperim.config import WORKING_CRS

EVENT_ID_COL = "event_id"
NOISE_LABEL = -1


def cluster_detections(
    detections: gpd.GeoDataFrame,
    eps_m: float = 1500.0,
    min_samples: int = 4,
    keep_noise: bool = False,
) -> gpd.GeoDataFrame:
    """Tag each detection with an `event_id` via DBSCAN on ground distance.

    Args:
        detections: standardized detections in EPSG:4326.
        eps_m: neighborhood radius in meters (two detections within this
            distance are density-reachable).
        min_samples: minimum detections to form a dense core (seeds an event).
        keep_noise: if False, drop unclustered (noise) detections.

    Returns:
        A copy of `detections` (EPSG:4326) with an integer `event_id`. Event ids
        are 1-based and ordered by size (largest fire = 1). Noise is -1.
    """
    out = detections.copy()
    if len(out) == 0:
        out[EVENT_ID_COL] = np.array([], dtype=int)
        return out

    # Project to meters so eps is a physical distance.
    projected = out.to_crs(WORKING_CRS)
    coords = np.column_stack([projected.geometry.x, projected.geometry.y])

    labels = DBSCAN(eps=eps_m, min_samples=min_samples, metric="euclidean").fit_predict(
        coords
    )

    # Renumber clusters so the biggest fire is event 1 (nice for demo labels).
    out[EVENT_ID_COL] = _relabel_by_size(labels)

    if not keep_noise:
        out = out[out[EVENT_ID_COL] != NOISE_LABEL].copy()
    return out.reset_index(drop=True)


def _relabel_by_size(labels: np.ndarray) -> np.ndarray:
    """Map raw DBSCAN labels to 1-based ids ordered by cluster size (noise=-1)."""
    result = np.full(labels.shape, NOISE_LABEL, dtype=int)
    clusters = [c for c in set(labels) if c != NOISE_LABEL]
    if not clusters:
        return result
    sizes = {c: int(np.sum(labels == c)) for c in clusters}
    ordered = sorted(clusters, key=lambda c: sizes[c], reverse=True)
    remap = {old: new for new, old in enumerate(ordered, start=1)}
    for old, new in remap.items():
        result[labels == old] = new
    return result


def cluster_summary(clustered: gpd.GeoDataFrame) -> dict:
    """Quick counts for the UI: number of events and clustered detections."""
    if EVENT_ID_COL not in clustered.columns or len(clustered) == 0:
        return {"n_events": 0, "n_clustered": 0}
    events = clustered[clustered[EVENT_ID_COL] != NOISE_LABEL]
    return {
        "n_events": int(events[EVENT_ID_COL].nunique()),
        "n_clustered": int(len(events)),
    }
