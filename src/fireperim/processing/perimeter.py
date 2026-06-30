"""Alpha-shape perimeter extraction - turn a cluster of points into a polygon.

For each fire event (cluster), we fit an alpha shape: a concave hull that hugs
the detection footprint more tightly than a convex hull would. This is the
satellite analog of ORBIT tracing a fire perimeter from an IR frame.

Robustness matters - alpha shapes can degenerate on collinear or tiny clusters,
so we fall back convex-hull -> buffered-points as needed. All geometry work
happens in a projected CRS (meters); outputs are reprojected to EPSG:4326.
"""
from __future__ import annotations

import logging

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import MultiPoint, Point
from shapely.geometry.base import BaseGeometry

from fireperim.config import GEOGRAPHIC_CRS, WORKING_CRS
from fireperim.processing.cluster import EVENT_ID_COL, NOISE_LABEL

log = logging.getLogger(__name__)

try:
    import alphashape
    _HAS_ALPHASHAPE = True
except Exception:  # pragma: no cover
    _HAS_ALPHASHAPE = False

EVENT_COLUMNS = [
    "event_id", "label", "n_detections", "total_frp_mw", "max_frp_mw",
    "mean_frp_mw", "area_ha", "perimeter_km", "centroid_lat", "centroid_lon",
    "first_seen", "last_seen", "sensors", "perimeter_method",
]


def build_events(clustered, alpha_per_m=0.0005, point_buffer_m=375.0, smoothing_m=150.0):
    """Build one perimeter polygon + stats per fire event."""
    if EVENT_ID_COL not in clustered.columns or len(clustered) == 0:
        return _empty_events()

    proj = clustered.to_crs(WORKING_CRS)
    records, geoms = [], []
    for event_id, grp in proj.groupby(EVENT_ID_COL):
        if event_id == NOISE_LABEL:
            continue
        poly, method = _polygon_for_group(grp, alpha_per_m, point_buffer_m, smoothing_m)
        if poly is None or poly.is_empty:
            continue
        frp = pd.to_numeric(grp["frp_mw"], errors="coerce")
        centroid = poly.centroid
        records.append({
            "event_id": int(event_id),
            "label": f"Event {int(event_id)}",
            "n_detections": int(len(grp)),
            "total_frp_mw": float(np.nansum(frp)),
            "max_frp_mw": float(np.nanmax(frp)) if frp.notna().any() else 0.0,
            "mean_frp_mw": float(np.nanmean(frp)) if frp.notna().any() else 0.0,
            "area_ha": float(poly.area / 10_000.0),
            "perimeter_km": float(poly.length / 1_000.0),
            "first_seen": grp["acq_datetime"].min(),
            "last_seen": grp["acq_datetime"].max(),
            "sensors": ", ".join(sorted(grp["sensor"].astype(str).unique())),
            "perimeter_method": method,
            "_cx": centroid.x, "_cy": centroid.y,
        })
        geoms.append(poly)

    if not records:
        return _empty_events()

    events = gpd.GeoDataFrame(records, geometry=geoms, crs=WORKING_CRS)
    cent_pts = gpd.GeoSeries(
        gpd.points_from_xy(events["_cx"], events["_cy"]), crs=WORKING_CRS
    ).to_crs(GEOGRAPHIC_CRS)
    events = events.to_crs(GEOGRAPHIC_CRS)
    events["centroid_lat"] = cent_pts.y.values
    events["centroid_lon"] = cent_pts.x.values
    events = events.drop(columns=["_cx", "_cy"])
    events = events.sort_values("event_id").reset_index(drop=True)
    return events[EVENT_COLUMNS + ["geometry"]]


def _polygon_for_group(grp, alpha_per_m, point_buffer_m, smoothing_m):
    """Return (polygon, method_label) for one cluster, in the projected CRS."""
    pts = [(geom.x, geom.y) for geom in grp.geometry]
    n = len(pts)
    if n < 3:
        poly = MultiPoint([Point(p) for p in pts]).buffer(point_buffer_m)
        return _finalize(poly, smoothing_m), "point_buffer"

    poly = None
    method = "alpha_shape"
    if _HAS_ALPHASHAPE and alpha_per_m > 0:
        try:
            poly = alphashape.alphashape(pts, alpha_per_m)
        except Exception as exc:  # noqa: BLE001
            log.debug("alphashape failed: %s", exc)
            poly = None
    if poly is None or poly.is_empty or poly.geom_type not in ("Polygon", "MultiPolygon"):
        method = "convex_hull"
        poly = MultiPoint(pts).convex_hull
        if poly.geom_type not in ("Polygon", "MultiPolygon"):
            method = "point_buffer"
            poly = MultiPoint([Point(p) for p in pts]).buffer(point_buffer_m)
    return _finalize(poly, smoothing_m), method


def _finalize(poly, smoothing_m):
    """Close small gaps and remove slivers via a buffer-out/in, then validate."""
    if smoothing_m > 0:
        poly = poly.buffer(smoothing_m).buffer(-smoothing_m * 0.5)
    if not poly.is_valid:
        poly = poly.buffer(0)
    return poly


def _empty_events():
    return gpd.GeoDataFrame({c: [] for c in EVENT_COLUMNS}, geometry=[], crs=GEOGRAPHIC_CRS)
