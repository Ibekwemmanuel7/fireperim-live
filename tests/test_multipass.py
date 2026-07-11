"""Tests for the multi-pass IR fusion chain."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "raster"))
import multipass as mp


@pytest.fixture(scope="module")
def run():
    return mp.run(n_passes=6, size_px=200, seed=11)


def test_passes_are_degraded(run):
    """Each simulated pass carries noise and at least one has a data gap."""
    passes = run["passes"]
    assert len(passes) == 6
    assert any((~p.valid).any() for p in passes)          # gaps present
    truth = mp.truth_scene(200, grow=passes[2].t)
    err = np.nanmean(np.abs(passes[2].image - truth))
    assert err > 3.0                                       # meaningfully noisy


def test_fusion_beats_single_pass_on_psnr(run):
    m = run["metrics"]
    assert m["full_fusion"]["psnr_db"] > m["single_pass"]["psnr_db"] + 3.0


def test_fusion_reduces_noise(run):
    m = run["metrics"]
    assert m["full_fusion"]["bg_noise_std_k"] < m["single_pass"]["bg_noise_std_k"]
    assert m["improvements"]["noise_reduction_pct"] > 10.0


def test_fusion_fills_gaps(run):
    """The composite covers pixels a single pass dropped."""
    assert run["metrics"]["improvements"]["gap_fill_pct"] > 0.0
    assert np.isfinite(run["result"]["fused"]).all()      # fused image has no gaps


def test_fused_edges_sharper_than_naive(run):
    m = run["metrics"]
    assert m["full_fusion"]["edge_sharpness"] >= m["naive_average"]["edge_sharpness"]


def test_registration_recovers_shift():
    """Phase-correlation registration should reduce a known injected shift."""
    truth = mp.truth_scene(200, grow=0.3)
    from scipy import ndimage
    shifted = ndimage.shift(truth, (4.0, -3.0), order=1, mode="nearest")
    reg, est = mp.register_to_reference(shifted, truth)
    # estimated shift should be close to the inverse of what we injected
    assert abs(est[0] + 4.0) < 1.0 and abs(est[1] - 3.0) < 1.0
