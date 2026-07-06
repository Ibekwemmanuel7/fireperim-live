"""Direct georeferencing (orthorectification) — the airborne geometry step.

An airborne IR scanner sees the ground *obliquely*, distorted by the aircraft's
position and attitude. Orthorectification removes that distortion by projecting
each pixel to true ground coordinates using the sensor pose (and a terrain
model). For a line/frame sensor this is *direct georeferencing* (project with the
GNSS/IMU pose), NOT structure-from-motion / bundle adjustment.

This module is a self-validating concept demo of that core operation:
  1. Define a camera pose (position + attitude) and an analytic ground scene.
  2. Render the oblique sensor image (what the scanner would see).
  3. Orthorectify it back to a north-up, georeferenced grid via the collinearity
     equations + indirect resampling.
  4. Validate: the orthophoto reconstructs the ground truth (high correlation).

The frame is synthesized and the terrain is a flat plane (constant elevation) for
clarity; swapping the constant plane for a real DEM (Z = DEM(X, Y)) makes it full
terrain orthorectification with the same equations.
"""
from __future__ import annotations

import numpy as np
from pyproj import Transformer
from rasterio.crs import CRS

GEO = CRS.from_epsg(4326)


# ----------------------------------------------------------------- camera model
def _camera_axes(view_dir):
    z = view_dir / np.linalg.norm(view_dir)          # optical axis (into scene)
    world_up = np.array([0.0, 0.0, 1.0])
    x = np.cross(world_up, z)
    if np.linalg.norm(x) < 1e-6:
        x = np.array([1.0, 0.0, 0.0])
    x = x / np.linalg.norm(x)                        # image right
    y = np.cross(z, x)
    y = y / np.linalg.norm(y)                        # image down
    return x, y, z


def make_camera(alt=1800.0, off_nadir_deg=35.0, heading_deg=20.0,
                f=650.0, W=480, H=480):
    """Aircraft camera: altitude (m), off-nadir tilt, heading; f in pixels."""
    th, ps = np.radians(off_nadir_deg), np.radians(heading_deg)
    view = np.array([np.sin(th) * np.sin(ps), np.sin(th) * np.cos(ps), -np.cos(th)])
    C = np.array([0.0, 0.0, alt])
    x, y, z = _camera_axes(view)
    return {"C": C, "x": x, "y": y, "z": z, "f": f, "cx": W / 2.0,
            "cy": H / 2.0, "W": W, "H": H, "view": view}


def ground_center(cam, z0=0.0):
    """Where the optical axis hits the ground plane Z=z0."""
    t = (z0 - cam["C"][2]) / cam["view"][2]
    return cam["C"][:2] + t * cam["view"][:2]


# --------------------------------------------------------- projection geometry
def project(cam, X, Y, Z):
    """World (X,Y,Z) -> image (px,py) via the collinearity equations."""
    rel = np.stack([X - cam["C"][0], Y - cam["C"][1], Z - cam["C"][2]], axis=-1)
    xc = rel @ cam["x"]
    yc = rel @ cam["y"]
    zc = rel @ cam["z"]
    zc = np.where(np.abs(zc) < 1e-6, 1e-6, zc)
    px = cam["cx"] + cam["f"] * xc / zc
    py = cam["cy"] + cam["f"] * yc / zc
    return px, py, zc


def raycast_to_plane(cam, px, py, z0=0.0):
    """Image (px,py) -> ground (X,Y) on plane Z=z0 (ray-plane intersection)."""
    dx = (px - cam["cx"])[..., None] * cam["x"]
    dy = (py - cam["cy"])[..., None] * cam["y"]
    d = dx + dy + cam["f"] * cam["z"]                 # ray direction in world
    t = (z0 - cam["C"][2]) / d[..., 2]
    X = cam["C"][0] + t * d[..., 0]
    Y = cam["C"][1] + t * d[..., 1]
    return X, Y


# ------------------------------------------------------------------ the scene
def scene_value(X, Y, cx, cy):
    """Analytic ground truth: a fire blob + a reference grid (to show geometry)."""
    r2 = ((X - cx) / 130.0) ** 2 + ((Y - cy) / 80.0) ** 2
    blob = np.exp(-r2)
    grid = (((np.abs((X - cx) % 60) < 2.0)) | ((np.abs((Y - cy) % 60) < 2.0))).astype(float) * 0.28
    return np.clip(blob + grid, 0, 1)


def render_oblique(cam, gc, z0=0.0):
    """The oblique sensor image: sample the analytic scene through the camera."""
    py, px = np.mgrid[0:cam["H"], 0:cam["W"]].astype(float)
    X, Y = raycast_to_plane(cam, px, py, z0)
    return scene_value(X, Y, gc[0], gc[1]).astype("float32")


def orthorectify(cam, oblique, gc, extent=520.0, res=2.0, z0=0.0):
    """Indirect resampling: for each ground cell, project into the oblique image.

    Returns (ortho array, ground-truth array, transform-origin, res).
    """
    n = int(extent / res)
    xs = gc[0] - extent / 2 + (np.arange(n) + 0.5) * res
    ys = gc[1] + extent / 2 - (np.arange(n) + 0.5) * res     # north-up (Y decreasing)
    Xo, Yo = np.meshgrid(xs, ys)
    px, py, zc = project(cam, Xo, Yo, np.full_like(Xo, z0))
    ipx = np.round(px).astype(int)
    ipy = np.round(py).astype(int)
    valid = (zc > 0) & (ipx >= 0) & (ipx < cam["W"]) & (ipy >= 0) & (ipy < cam["H"])
    ortho = np.zeros_like(Xo, dtype="float32")
    ortho[valid] = oblique[ipy[valid], ipx[valid]]
    truth = scene_value(Xo, Yo, gc[0], gc[1]).astype("float32")
    x0 = gc[0] - extent / 2
    y0 = gc[1] + extent / 2
    return ortho, truth, valid, (x0, y0), res


def validation_score(ortho, truth, valid):
    """Correlation between orthophoto and ground truth over the valid region."""
    a = ortho[valid].ravel()
    b = truth[valid].ravel()
    if a.size < 10 or a.std() < 1e-6 or b.std() < 1e-6:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def georeference(origin_xy, res, shape, center_lat=37.85, center_lon=-119.55,
                 epsg=32611):
    """Place the local metric grid at a real UTM location; return affine + bounds4326."""
    from affine import Affine
    to_utm = Transformer.from_crs(GEO, CRS.from_epsg(epsg), always_xy=True)
    e0, n0 = to_utm.transform(center_lon, center_lat)
    x0, y0 = origin_xy
    transform = Affine(res, 0, e0 + x0, 0, -res, n0 + y0)
    h, w = shape
    to_geo = Transformer.from_crs(CRS.from_epsg(epsg), GEO, always_xy=True)
    lons, lats = to_geo.transform(
        [e0 + x0, e0 + x0 + w * res], [n0 + y0, n0 + y0 - h * res])
    bounds = {"west": min(lons), "east": max(lons), "south": min(lats), "north": max(lats)}
    return transform, CRS.from_epsg(epsg), bounds
