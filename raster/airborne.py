"""Airborne thermal-frame processing: reproject -> threshold -> COG -> perimeter.

The techniques here (reprojection, hotspot thresholding, raster->vector
polygonization, COG generation) are exactly those an airborne IR pipeline needs;
the input frame is synthesized and clearly labelled as simulated, but the
processing is real and would run unchanged on a true scanner frame.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from pyproj import Transformer
from rasterio.crs import CRS
from rasterio.features import shapes
from rasterio.warp import Resampling, calculate_default_transform, reproject

import geopandas as gpd
from shapely.geometry import shape
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fireperim.ingest.base import DETECTION_COLUMNS  # noqa: E402

GEO = CRS.from_epsg(4326)
ACTIVE_FIRE_K = 360.0   # brightness-temperature threshold for "active fire"
BACKGROUND_K = 300.0


def _utm_epsg(lat: float, lon: float) -> int:
    zone = int((lon + 180) // 6) + 1
    return (32600 if lat >= 0 else 32700) + zone


def synthesize_thermal_frame(
    center_lat: float = 37.851,
    center_lon: float = -119.551,
    size_px: int = 500,
    res_m: float = 5.0,
    seed: int = 7,
):
    """Return (brightness_K array, affine transform, CRS) for a simulated frame.

    A high-resolution (res_m) airborne IR frame in the local UTM zone: cool
    background with an elongated, wind-driven hot fire front and a few spot
    fires ahead of it. Values are brightness temperature in Kelvin.
    """
    rng = np.random.default_rng(seed)
    epsg = _utm_epsg(center_lat, center_lon)
    to_utm = Transformer.from_crs(GEO, CRS.from_epsg(epsg), always_xy=True)
    cx, cy = to_utm.transform(center_lon, center_lat)

    half = size_px * res_m / 2.0
    # north-up affine: top-left origin
    transform = Affine(res_m, 0, cx - half, 0, -res_m, cy + half)

    yy, xx = np.mgrid[0:size_px, 0:size_px]
    # normalized coords centered at 0
    nx = (xx - size_px / 2) / (size_px / 2)
    ny = (yy - size_px / 2) / (size_px / 2)

    # main fire front: rotated elongated gaussian
    theta = np.deg2rad(35)
    rx = nx * np.cos(theta) - ny * np.sin(theta)
    ry = nx * np.sin(theta) + ny * np.cos(theta)
    front = np.exp(-((rx / 0.55) ** 2 + (ry / 0.22) ** 2))

    # a couple of spot fires ahead of the front
    spots = np.zeros_like(front)
    for (sx, sy, s) in [(0.45, -0.35, 0.06), (0.6, -0.15, 0.05), (-0.5, 0.4, 0.05)]:
        spots += np.exp(-(((nx - sx) / s) ** 2 + ((ny - sy) / s) ** 2))

    heat = np.clip(front + 0.8 * spots, 0, 1.2)
    noise = rng.normal(0, 2.0, size=(size_px, size_px))
    # background ~300K, hottest core ~640K
    bt = BACKGROUND_K + heat * 340.0 + noise
    return bt.astype("float32"), transform, CRS.from_epsg(epsg)


def write_geotiff(array, transform, crs, path, nodata=None):
    path = str(path)
    with rasterio.open(
        path, "w", driver="GTiff", height=array.shape[0], width=array.shape[1],
        count=1, dtype=array.dtype, crs=crs, transform=transform, nodata=nodata,
    ) as dst:
        dst.write(array, 1)
    return path


def write_cog(array, transform, crs, path):
    """Write a Cloud-Optimized GeoTIFF (internal tiling + overviews)."""
    path = str(path)
    with rasterio.open(
        path, "w", driver="COG", height=array.shape[0], width=array.shape[1],
        count=1, dtype=array.dtype, crs=crs, transform=transform,
        compress="deflate", blocksize=256,
    ) as dst:
        dst.write(array, 1)
    return path


def reproject_to_4326(array, transform, crs):
    """Reproject a frame to EPSG:4326. Returns (array, transform, bounds)."""
    h, w = array.shape
    left, top = transform * (0, 0)
    right, bottom = transform * (w, h)
    dst_transform, dw, dh = calculate_default_transform(
        crs, GEO, w, h, left=left, bottom=bottom, right=right, top=top
    )
    dst = np.zeros((dh, dw), dtype=array.dtype)
    reproject(
        source=array, destination=dst, src_transform=transform, src_crs=crs,
        dst_transform=dst_transform, dst_crs=GEO, resampling=Resampling.bilinear,
    )
    l2, t2 = dst_transform * (0, 0)
    r2, b2 = dst_transform * (dw, dh)
    bounds = {"west": l2, "south": b2, "east": r2, "north": t2}
    return dst, dst_transform, bounds


def extract_perimeter(array, transform, crs, threshold_k: float = ACTIVE_FIRE_K):
    """Threshold hot pixels and polygonize to a perimeter (raster -> vector).

    Returns (GeoDataFrame in EPSG:4326 with one perimeter row, stats dict).
    Area is computed in the projected (metre) CRS for accuracy.
    """
    mask = (array >= threshold_k).astype("uint8")
    geoms = [
        shape(geom)
        for geom, val in shapes(mask, mask=mask.astype(bool), transform=transform)
        if val == 1
    ]
    if not geoms:
        empty = gpd.GeoDataFrame({"perimeter_method": []}, geometry=[], crs=GEO)
        return empty, {"hot_pixels": 0, "area_ha": 0.0}

    merged = unary_union(geoms)
    # smooth: close small gaps in projected metres
    merged = merged.buffer(transform.a * 1.5).buffer(-transform.a * 0.75)
    merged = merged.simplify(transform.a * 2.0)  # thin vertices for web delivery
    area_ha = float(merged.area / 10_000.0)

    gdf_utm = gpd.GeoDataFrame(
        {
            "perimeter_method": ["raster_threshold"],
            "area_ha": [round(area_ha, 1)],
            "threshold_k": [threshold_k],
            "max_brightness_k": [round(float(array.max()), 1)],
        },
        geometry=[merged], crs=crs,
    )
    gdf = gdf_utm.to_crs(GEO)
    stats = {
        "hot_pixels": int(mask.sum()),
        "area_ha": round(area_ha, 1),
        "max_brightness_k": round(float(array.max()), 1),
    }
    return gdf, stats


def frame_to_detections(array, transform, crs, threshold_k: float = ACTIVE_FIRE_K,
                        step: int = 6):
    """Emit hot pixels as STANDARDIZED detections (the swap-seam payoff).

    The airborne frame becomes the exact same schema the FIRMS client produces,
    so it flows into cluster_detections / build_events unchanged.
    """
    import pandas as pd

    ys, xs = np.where(array[::step, ::step] >= threshold_k)
    ys, xs = ys * step, xs * step
    if len(xs) == 0:
        from fireperim.ingest.base import DetectionSource
        return DetectionSource.empty()

    eastings, northings = transform * (xs + 0.5, ys + 0.5)
    to_geo = Transformer.from_crs(crs, GEO, always_xy=True)
    lon, lat = to_geo.transform(eastings, northings)
    bt = array[ys, xs].astype(float)

    df = pd.DataFrame({
        "latitude": lat, "longitude": lon,
        "acq_datetime": pd.Timestamp.utcnow().floor("min"),
        "frp_mw": np.round((bt - BACKGROUND_K) / 12.0, 1),  # crude energy proxy
        "brightness_k": np.round(bt, 1),
        "confidence": 90.0, "confidence_class": "high", "daynight": "D",
        "sensor": "AIRBORNE_IR (sim)", "satellite": "aircraft",
        "scan_km": round(transform.a / 1000.0, 4), "track_km": round(transform.a / 1000.0, 4),
    })
    gdf = gpd.GeoDataFrame(
        df, geometry=gpd.points_from_xy(df["longitude"], df["latitude"]), crs=GEO
    )
    return gdf[list(DETECTION_COLUMNS) + ["geometry"]]


def render_overlay_png(array_4326, path, threshold_k: float = ACTIVE_FIRE_K):
    """Colorize a (reprojected) thermal array to an RGBA fire ramp PNG.

    Cold background is transparent; heat ramps black->red->orange->yellow->white
    with increasing opacity, so it reads as a heat overlay on the basemap.
    """
    from PIL import Image

    a = array_4326.astype("float32")
    lo, hi = threshold_k - 20, float(np.nanmax(a))
    t = np.clip((a - lo) / max(1e-3, (hi - lo)), 0, 1)

    # fire colormap stops: (pos, r, g, b)
    stops = [(0.0, 20, 0, 0), (0.35, 160, 20, 0), (0.6, 235, 90, 10),
             (0.8, 255, 180, 30), (1.0, 255, 255, 210)]
    r = np.interp(t, [s[0] for s in stops], [s[1] for s in stops])
    g = np.interp(t, [s[0] for s in stops], [s[2] for s in stops])
    b = np.interp(t, [s[0] for s in stops], [s[3] for s in stops])
    # alpha: transparent below threshold, ramping up above
    alpha = np.clip((a - (threshold_k - 15)) / 60.0, 0, 1) * 235
    rgba = np.dstack([r, g, b, alpha]).astype("uint8")
    Image.fromarray(rgba, "RGBA").save(str(path))
    return str(path)


def write_bounds_json(bounds, path):
    Path(path).write_text(json.dumps(bounds, indent=2))
    return str(path)
