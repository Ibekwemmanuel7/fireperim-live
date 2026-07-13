"""
georef.py — direct georeferencing of airborne frames from REAL onboard pose.

This closes the "frames assume they're already aligned" gap: instead of simulating sub-pixel
jitter, it takes each frame's real telemetry (camera GPS position + altitude, and the onboard
laser-rangefinder's measured ground target) and projects the image onto the ground, so multiple
oblique passes over the same terrain can be orthorectified onto ONE common grid and then fused.

Pose model (DJI M30T, as shipped in the FLAME 3 EXIF/XMP):
  - camera position  : GPS lat/lon + altitude (MSL)
  - optical axis      : the vector from the camera to the laser-rangefinder target
                        (LRFTargetLat/Lon/AbsAlt) — this is a *measured* boresight, so it
                        implicitly carries the heading/yaw that isn't in the metadata.
  - roll              : the gimbal is roll-stabilized, so image "up" = world-up projected
                        perpendicular to the optical axis (standard gimballed-camera assumption).
  - ground            : local plane at the LRF target altitude (a DEM can be dropped in here for
                        terrain-aware ortho — see `ground_z` hook).

Validation: the image centre must reproject to the LRF target. `reprojection_error_m()` reports
that residual in metres — a real, honest accuracy number, not a synthetic one.

Intrinsics: M30T wide camera, 4000x3000, focal 4.4 mm, 1/2" sensor 6.4x4.8 mm (DFOV ~84°).
"""
from __future__ import annotations
import re, math
import numpy as np
import cv2
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

# --- camera intrinsics (M30T wide) -------------------------------------------
SENSOR_W_MM, SENSOR_H_MM = 6.4, 4.8
DEFAULT_FOCAL_MM = 4.4


def intrinsics(img_w: int, img_h: int, focal_mm: float = DEFAULT_FOCAL_MM):
    fx = focal_mm / SENSOR_W_MM * img_w
    fy = focal_mm / SENSOR_H_MM * img_h
    return fx, fy, img_w / 2.0, img_h / 2.0


# --- pose extraction ----------------------------------------------------------
def _dms(v):
    return float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600


def read_pose(path: str) -> dict:
    """Return camera + LRF-target pose from a DJI JPG's EXIF + XMP."""
    im = Image.open(path)
    ex = im._getexif() or {}
    lat = lon = alt = focal = None
    for k, v in ex.items():
        name = TAGS.get(k, k)
        if name == "GPSInfo":
            g = {GPSTAGS.get(kk, kk): vv for kk, vv in v.items()}
            lat, lon = _dms(g["GPSLatitude"]), _dms(g["GPSLongitude"])
            if g.get("GPSLatitudeRef") == "S": lat = -lat
            if g.get("GPSLongitudeRef") == "W": lon = -lon
            alt = float(g.get("GPSAltitude", 0))
        elif name == "FocalLength":
            focal = float(v)
    raw = open(path, "rb").read(200000)
    s, e = raw.find(b"<x:xmpmeta"), raw.find(b"</x:xmpmeta")
    d = {}
    if s != -1:
        t = raw[s:e + 12].decode("utf-8", "ignore")
        for k, v in re.findall(r'([A-Za-z]+)="(-?[\d.]+)"', t):
            d.setdefault(k, float(v))
    return {
        "lat": lat, "lon": lon, "alt": alt,
        "focal_mm": focal or DEFAULT_FOCAL_MM,
        "img_w": im.size[0], "img_h": im.size[1],
        "lrf_lat": d.get("LRFTargetLat", 0.0), "lrf_lon": d.get("LRFTargetLon", 0.0),
        "lrf_alt": d.get("LRFTargetAbsAlt", 0.0), "lrf_dist": d.get("LRFTargetDistance", 0.0),
        "gimbal_pitch": d.get("GimbalPitchDegree"),
    }


def has_lrf(p: dict) -> bool:
    return abs(p.get("lrf_lat", 0)) > 1 and p.get("lrf_dist", 0) > 0


# --- local ENU frame (metres) centred on a reference lat/lon -----------------
def enu_scale(lat0: float):
    return 111320.0 * math.cos(math.radians(lat0)), 110540.0  # (m per deg lon, m per deg lat)


def lonlat_to_enu(lon, lat, lon0, lat0):
    mx, my = enu_scale(lat0)
    return (np.asarray(lon) - lon0) * mx, (np.asarray(lat) - lat0) * my


def enu_to_lonlat(e, n, lon0, lat0):
    mx, my = enu_scale(lat0)
    return lon0 + np.asarray(e) / mx, lat0 + np.asarray(n) / my


# --- camera basis from pose (right, up, forward in ENU) ----------------------
def camera_basis(pose: dict, lon0: float, lat0: float, ground_z: float | None = None):
    """
    Build camera position and orthonormal (right, up, fwd) in the local ENU frame.
    fwd  = camera -> LRF target (measured boresight).
    up   = world-up projected orthogonal to fwd (gimbal roll-stabilized).
    """
    ce, cn = lonlat_to_enu(pose["lon"], pose["lat"], lon0, lat0)
    cu = pose["alt"]
    C = np.array([float(ce), float(cn), float(cu)])
    te, tn = lonlat_to_enu(pose["lrf_lon"], pose["lrf_lat"], lon0, lat0)
    tz = pose["lrf_alt"] if ground_z is None else ground_z
    T = np.array([float(te), float(tn), float(tz)])
    fwd = T - C
    fwd /= np.linalg.norm(fwd)
    world_up = np.array([0.0, 0.0, 1.0])
    up = world_up - fwd * (world_up @ fwd)
    up /= np.linalg.norm(up)
    right = np.cross(fwd, up)
    right /= np.linalg.norm(right)
    # re-orthogonalize up to keep a clean right-handed basis
    up = np.cross(right, fwd)
    return C, right, up, fwd


def ground_from_pixel(u, v, pose, C, right, up, fwd, ground_z):
    """Project image pixels (u,v) to ground plane z=ground_z. Returns (E, N) arrays; NaN if it misses."""
    fx, fy, cx, cy = intrinsics(pose["img_w"], pose["img_h"], pose["focal_mm"])
    x = (np.asarray(u) - cx) / fx
    y = (cy - np.asarray(v)) / fy            # image row grows downward -> flip for world-up
    d = (fwd[None, ...] + x[..., None] * right[None, ...] + y[..., None] * up[None, ...])
    dz = d[..., 2]
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (ground_z - C[2]) / dz
    t = np.where(t > 0, t, np.nan)
    E = C[0] + t * d[..., 0]
    N = C[1] + t * d[..., 1]
    return E, N


def pixel_from_ground(E, N, ground_z, pose, C, right, up, fwd):
    """Inverse map: ground (E,N,ground_z) -> image pixel (u,v). NaN if behind camera."""
    fx, fy, cx, cy = intrinsics(pose["img_w"], pose["img_h"], pose["focal_mm"])
    P = np.stack([np.asarray(E) - C[0], np.asarray(N) - C[1],
                  np.full(np.asarray(E).shape, ground_z - C[2])], axis=-1)
    xf = P @ fwd
    xr = P @ right
    xu = P @ up
    with np.errstate(divide="ignore", invalid="ignore"):
        u = cx + fx * (xr / xf)
        v = cy - fy * (xu / xf)
    bad = xf <= 0
    u = np.where(bad, np.nan, u)
    v = np.where(bad, np.nan, v)
    return u, v


def reprojection_error_m(pose: dict, lon0: float, lat0: float) -> float:
    """Project the image centre to ground; distance to the measured LRF target (metres)."""
    C, right, up, fwd = camera_basis(pose, lon0, lat0)
    E, N = ground_from_pixel(pose["img_w"] / 2.0, pose["img_h"] / 2.0, pose, C, right, up, fwd, pose["lrf_alt"])
    te, tn = lonlat_to_enu(pose["lrf_lon"], pose["lrf_lat"], lon0, lat0)
    return float(math.hypot(float(E) - float(te), float(N) - float(tn)))


def footprint_quad(pose: dict, lon0: float, lat0: float, ground_z: float | None = None):
    """Ground footprint of the 4 image corners as (lon,lat) pairs, order TL,TR,BR,BL."""
    gz = pose["lrf_alt"] if ground_z is None else ground_z
    C, right, up, fwd = camera_basis(pose, lon0, lat0, gz)
    w, h = pose["img_w"], pose["img_h"]
    us = np.array([0, w, w, 0], float); vs = np.array([0, 0, h, h], float)
    E, N = ground_from_pixel(us, vs, pose, C, right, up, fwd, gz)
    lon, lat = enu_to_lonlat(E, N, lon0, lat0)
    return list(zip(lon.tolist(), lat.tolist()))


# --- orthorectify one frame onto a shared ENU grid ---------------------------
def orthorectify(img: np.ndarray, pose: dict, grid, lon0: float, lat0: float,
                 ground_z: float | None = None):
    """
    Resample `img` onto a north-up ground grid.
    `grid` = (E_min, E_max, N_min, N_max, px_per_m). Returns (ortho_img, valid_mask).
    """
    gz = pose["lrf_alt"] if ground_z is None else ground_z
    C, right, up, fwd = camera_basis(pose, lon0, lat0, gz)
    Emin, Emax, Nmin, Nmax, ppm = grid
    W = int(round((Emax - Emin) * ppm)); H = int(round((Nmax - Nmin) * ppm))
    ee = Emin + (np.arange(W) + 0.5) / ppm
    nn = Nmax - (np.arange(H) + 0.5) / ppm          # north up => row 0 is top (max N)
    E, N = np.meshgrid(ee, nn)
    u, v = pixel_from_ground(E, N, gz, pose, C, right, up, fwd)
    mapx = u.astype(np.float32); mapy = v.astype(np.float32)
    valid = np.isfinite(mapx) & np.isfinite(mapy) & (mapx >= 0) & (mapx < pose["img_w"]) & \
            (mapy >= 0) & (mapy < pose["img_h"])
    mapx = np.where(valid, mapx, -1); mapy = np.where(valid, mapy, -1)
    ortho = cv2.remap(img, mapx, mapy, cv2.INTER_LINEAR, borderValue=0)
    return ortho, valid
