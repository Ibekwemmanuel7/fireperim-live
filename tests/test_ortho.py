"""Tests for the orthorectification / direct-georeferencing demo."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("rasterio")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from raster import ortho as O


def test_project_raycast_roundtrip():
    """Ray-cast a pixel to the ground, project it back -> same pixel."""
    cam = O.make_camera()
    px, py = 210.0, 160.0
    X, Y = O.raycast_to_plane(cam, np.array([px]), np.array([py]), z0=0.0)
    bx, by, zc = O.project(cam, X, Y, np.array([0.0]))
    assert zc[0] > 0                        # ground is in front of the camera
    assert abs(bx[0] - px) < 1e-3 and abs(by[0] - py) < 1e-3


def test_orthorectification_reconstructs_ground_truth():
    """The orthophoto must match the analytic ground scene (geometry corrected)."""
    cam = O.make_camera(alt=1800, off_nadir_deg=35, heading_deg=20)
    gc = O.ground_center(cam)
    oblique = O.render_oblique(cam, gc)
    ortho, truth, valid, origin, res = O.orthorectify(cam, oblique, gc)
    assert valid.mean() > 0.5
    assert O.validation_score(ortho, truth, valid) > 0.9   # strong correlation


def test_more_oblique_still_valid():
    cam = O.make_camera(alt=2200, off_nadir_deg=45, heading_deg=70)
    gc = O.ground_center(cam)
    ob = O.render_oblique(cam, gc)
    ortho, truth, valid, _, _ = O.orthorectify(cam, ob, gc)
    assert O.validation_score(ortho, truth, valid) > 0.85


def test_georeference_bounds_in_california():
    cam = O.make_camera()
    gc = O.ground_center(cam)
    ob = O.render_oblique(cam, gc)
    ortho, _, _, origin, res = O.orthorectify(cam, ob, gc)
    _, crs, bounds = O.georeference(origin, res, ortho.shape)
    assert crs.to_epsg() == 32611
    assert -120.5 < bounds["west"] < -118.5 and 37.0 < bounds["south"] < 38.5
