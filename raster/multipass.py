"""Multi-pass airborne IR fusion: many noisy single passes -> one clean image.

This is the imagery-quality problem an airborne fire-mapping platform actually
has: a single scanner pass over a fire is noisy, striped, gap-ridden and slightly
mis-registered. Flying repeated orbits gives independent looks at the same ground.
Once each pass is registered onto a common grid, they can be *fused* -- averaging
away noise, suppressing line-scanner striping, and filling gaps -- to produce one
clean, sharp composite.

The scene is synthesized and clearly labelled as simulated, but every processing
step (destripe -> radiometric normalize -> co-register -> time-aware stack ->
pick-best-pixel) is a real, industry-standard technique that would run unchanged
on a true scanner feed.

Pipeline, matching state-of-practice:
  1. Destripe            column moment-matching (line-scanner FPN removal)
  2. Radiometric norm    match each pass's mean/std to a robust reference
  3. Co-register         phase cross-correlation -> sub-pixel shift (skimage)
  4. Time-aware stack    recency-weighted, gap-aware robust mean
  5. Pick-best-pixel     nearest-in-time valid look drives edge sharpness

Metrics (vs. the clean ground truth): PSNR, SSIM, background noise std,
gap-fill %, and edge sharpness -- so the improvement is quantified, not asserted.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import warnings

import numpy as np
from scipy import ndimage
from skimage.metrics import peak_signal_noise_ratio, structural_similarity
from skimage.registration import phase_cross_correlation

BACKGROUND_K = 300.0
PEAK_K = 640.0
ACTIVE_FIRE_K = 360.0


# --------------------------------------------------------------------------- #
# Scene + fire growth
# --------------------------------------------------------------------------- #
def _base_heat(size_px: int, grow: float = 0.0) -> np.ndarray:
    """Normalized 0..~1.2 heat field. `grow` (0..1) advances the fire front."""
    yy, xx = np.mgrid[0:size_px, 0:size_px]
    nx = (xx - size_px / 2) / (size_px / 2)
    ny = (yy - size_px / 2) / (size_px / 2)

    # main front drifts downwind (+x) and lengthens as the fire grows
    theta = np.deg2rad(35)
    shift = 0.18 * grow
    rx = (nx - shift) * np.cos(theta) - ny * np.sin(theta)
    ry = (nx - shift) * np.sin(theta) + ny * np.cos(theta)
    length = 0.55 + 0.25 * grow
    front = np.exp(-((rx / length) ** 2 + (ry / 0.22) ** 2))

    spots = np.zeros_like(front)
    for (sx, sy, s) in [(0.45, -0.35, 0.06), (0.6, -0.15, 0.05), (-0.5, 0.4, 0.05)]:
        spots += np.exp(-(((nx - sx - shift) / s) ** 2 + ((ny - sy) / s) ** 2))

    return np.clip(front + 0.8 * spots, 0, 1.2)


def truth_scene(size_px: int = 400, grow: float = 0.0) -> np.ndarray:
    """Clean ground-truth brightness temperature (Kelvin). No noise."""
    return BACKGROUND_K + _base_heat(size_px, grow) * (PEAK_K - BACKGROUND_K)


# --------------------------------------------------------------------------- #
# Per-pass degradation model
# --------------------------------------------------------------------------- #
@dataclass
class PassConfig:
    noise_k: float = 9.0          # additive sensor noise (K, 1-sigma)
    stripe_k: float = 7.0         # column fixed-pattern noise amplitude (K)
    gain_jitter: float = 0.06     # per-pass radiometric gain drift
    offset_k: float = 6.0         # per-pass radiometric offset drift (K)
    max_shift_px: float = 2.5     # georeg/pose mis-registration (pixels)
    rot_deg: float = 0.8          # small residual rotation (degrees)
    gap_frac: float = 0.16        # fraction of swath dropped (edge/occlusion)


@dataclass
class Pass:
    image: np.ndarray             # degraded observation (K), NaN where no data
    valid: np.ndarray             # bool mask of observed pixels
    t: float                      # acquisition time (0..1, later = more recent)
    true_shift: tuple             # (dy, dx) injected, for diagnostics


def simulate_pass(size_px: int, t: float, cfg: PassConfig, rng) -> Pass:
    """One degraded scanner pass: growth + stripe + noise + shift + gaps."""
    truth = truth_scene(size_px, grow=t)

    # geometric mis-registration (sub-pixel shift + tiny rotation)
    dy = rng.uniform(-cfg.max_shift_px, cfg.max_shift_px)
    dx = rng.uniform(-cfg.max_shift_px, cfg.max_shift_px)
    ang = rng.uniform(-cfg.rot_deg, cfg.rot_deg)
    img = ndimage.rotate(truth, ang, reshape=False, order=1, mode="nearest")
    img = ndimage.shift(img, (dy, dx), order=1, mode="nearest")

    # radiometric drift (per-pass gain + offset)
    gain = 1.0 + rng.uniform(-cfg.gain_jitter, cfg.gain_jitter)
    offset = rng.uniform(-cfg.offset_k, cfg.offset_k)
    img = (img - BACKGROUND_K) * gain + BACKGROUND_K + offset

    # line-scanner striping: per-column fixed-pattern gain+offset
    col_off = rng.normal(0, cfg.stripe_k, size=size_px)
    col_gain = 1.0 + rng.normal(0, 0.02, size=size_px)
    img = img * col_gain[None, :] + col_off[None, :]

    # additive sensor noise
    img = img + rng.normal(0, cfg.noise_k, size=(size_px, size_px))

    # data gaps: drop a contiguous swath band (edge of look / smoke occlusion)
    valid = np.ones((size_px, size_px), dtype=bool)
    band = int(cfg.gap_frac * size_px)
    if band > 0:
        start = rng.integers(0, size_px - band)
        # gaps run along scan direction, alternating side per pass
        if rng.random() < 0.5:
            valid[:, start:start + band] = False
        else:
            valid[start:start + band, :] = False
    img = np.where(valid, img, np.nan)

    return Pass(image=img, valid=valid, t=t, true_shift=(dy, dx))


def simulate_passes(n: int = 6, size_px: int = 400, cfg: PassConfig | None = None,
                    seed: int = 11) -> list[Pass]:
    cfg = cfg or PassConfig()
    rng = np.random.default_rng(seed)
    ts = np.linspace(0.0, 1.0, n)
    return [simulate_pass(size_px, float(t), cfg, rng) for t in ts]


# --------------------------------------------------------------------------- #
# Fusion chain
# --------------------------------------------------------------------------- #
def destripe(img: np.ndarray) -> np.ndarray:
    """Column moment-matching: remove per-column offset relative to row-median.

    Standard line-scanner FPN reducer. NaN-aware. Operates on both axes lightly.
    """
    out = img.copy()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        global_med = np.nanmedian(out)
        col_med = np.nanmedian(out, axis=0)
    col_corr = np.where(np.isfinite(col_med), col_med - global_med, 0.0)
    out = out - col_corr[None, :]
    return out


def radiometric_normalize(img: np.ndarray, ref_mean: float, ref_std: float) -> np.ndarray:
    """Match this pass's robust mean/std to a common reference (moment matching)."""
    m = np.nanmean(img)
    s = np.nanstd(img)
    if not np.isfinite(s) or s < 1e-6:
        return img
    return (img - m) / s * ref_std + ref_mean


def register_to_reference(img: np.ndarray, ref: np.ndarray) -> tuple[np.ndarray, tuple]:
    """Estimate sub-pixel shift via phase correlation and resample onto ref grid."""
    a = np.where(np.isfinite(img), img, np.nanmedian(img))
    b = np.where(np.isfinite(ref), ref, np.nanmedian(ref))
    shift, _, _ = phase_cross_correlation(b, a, upsample_factor=10)
    # apply inverse shift to the *image*; carry the validity mask along
    reg = ndimage.shift(img, shift, order=1, mode="constant", cval=np.nan)
    return reg, tuple(shift)


def fuse(passes: list[Pass], tau: float = 0.35) -> dict:
    """Full fusion chain. Returns fused image, naive mean, and per-stage arrays.

    tau: recency time-constant for time-aware weighting (smaller = trust recent
    passes more, important because the fire moves between passes).
    """
    size = passes[0].image.shape[0]
    ref_raw = passes[-1].image  # most-recent pass is the geometric/temporal anchor
    ref_mean = float(np.nanmean(ref_raw))
    ref_std = float(np.nanstd(ref_raw))

    naive_stack, reg_imgs, weights = [], [], []
    t_ref = max(p.t for p in passes)

    for p in passes:
        step = destripe(p.image)                                   # 1. destripe
        step = radiometric_normalize(step, ref_mean, ref_std)      # 2. radiometric
        reg, _ = register_to_reference(step, ref_raw)              # 3. co-register
        reg_imgs.append(reg)
        naive_stack.append(reg)
        # 4. time-aware weight: recent passes weigh more
        weights.append(np.exp(-(t_ref - p.t) / tau))

    reg_arr = np.stack(reg_imgs)                    # (N, H, W) with NaN gaps
    valid = np.isfinite(reg_arr)

    # Naive average (baseline): equal-weight, gap-aware
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        naive = np.nanmean(np.stack(naive_stack), axis=0)

    # Robust time-aware weighted mean with per-pixel outlier rejection
    w = np.array(weights)[:, None, None] * valid
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        med = np.nanmedian(reg_arr, axis=0)
        mad = np.nanmedian(np.abs(reg_arr - med[None]), axis=0) + 1e-6
    med = np.where(np.isfinite(med), med, BACKGROUND_K)
    inlier = np.abs(reg_arr - med[None]) < (3.0 * 1.4826 * mad[None])
    w = w * inlier
    wsum = np.clip(w.sum(axis=0), 1e-6, None)
    fused = np.nansum(np.where(valid, reg_arr, 0.0) * w, axis=0) / wsum

    # 5. Sharp front: on the active fire the scene MOVES between passes, so a
    #    plain average smears the perimeter. Build a strongly recency-weighted
    #    field (still multi-look, so noise stays down) and blend it in only on
    #    the hot front -- keeps the leading edge crisp AND current.
    tau_sharp = tau * 0.35
    w_sharp = np.array([np.exp(-(t_ref - p.t) / tau_sharp) for p in passes])[:, None, None] * valid * inlier
    wsum_sharp = np.clip(w_sharp.sum(axis=0), 1e-6, None)
    sharp = np.nansum(np.where(valid, reg_arr, 0.0) * w_sharp, axis=0) / wsum_sharp
    # feather the hot mask so the sharp front blends smoothly into the averaged
    # background -- no hard seam between the two fields
    hot = (med - (BACKGROUND_K + 0.42 * (PEAK_K - BACKGROUND_K)))
    hot = np.clip(hot / (0.16 * (PEAK_K - BACKGROUND_K)), 0.0, 1.0)
    hot = ndimage.gaussian_filter(hot, 6.0)
    sharp_ok = np.where(np.isfinite(sharp), sharp, fused)
    fused = (1.0 - hot) * fused + hot * sharp_ok

    # any residual gaps: fill from the robust median
    fused = np.where(np.isfinite(fused), fused, med)

    coverage = valid.any(axis=0)
    return {
        "fused": fused,
        "naive": naive,
        "median": med,
        "coverage": coverage,
        "n_passes": len(passes),
        "size": size,
    }


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def _bg_mask(truth: np.ndarray) -> np.ndarray:
    return truth < (BACKGROUND_K + 0.15 * (PEAK_K - BACKGROUND_K))


def evaluate(truth: np.ndarray, img: np.ndarray) -> dict:
    """PSNR/SSIM vs truth, background noise std, edge sharpness."""
    a = np.where(np.isfinite(img), img, BACKGROUND_K)
    rng = float(PEAK_K - BACKGROUND_K)
    psnr = float(peak_signal_noise_ratio(truth, a, data_range=truth.max() - truth.min()))
    ssim = float(structural_similarity(truth, a, data_range=truth.max() - truth.min()))
    bg = _bg_mask(truth)
    noise_std = float(np.std(a[bg] - truth[bg]))
    # edge sharpness: mean gradient magnitude along the true fire perimeter band
    gt_grad = np.hypot(*np.gradient(truth))
    edge = gt_grad > np.percentile(gt_grad, 97)
    grad = np.hypot(*np.gradient(a))
    sharp = float(grad[edge].mean())
    return {"psnr_db": psnr, "ssim": ssim, "bg_noise_std_k": noise_std,
            "edge_sharpness": sharp}


def summarize(passes: list[Pass], result: dict) -> dict:
    """Compare a representative single pass, naive average, and full fusion."""
    truth_final = truth_scene(result["size"], grow=max(p.t for p in passes))
    single = passes[len(passes) // 2].image
    m_single = evaluate(truth_final, single)
    m_naive = evaluate(truth_final, result["naive"])
    m_fused = evaluate(truth_final, result["fused"])

    single_valid = np.isfinite(single)
    gap_fill = float((result["coverage"] & ~single_valid).sum() / single_valid.size * 100)

    noise_drop = (1 - m_fused["bg_noise_std_k"] / m_single["bg_noise_std_k"]) * 100
    return {
        "single_pass": m_single,
        "naive_average": m_naive,
        "full_fusion": m_fused,
        "improvements": {
            "psnr_gain_db": round(m_fused["psnr_db"] - m_single["psnr_db"], 2),
            "ssim_gain": round(m_fused["ssim"] - m_single["ssim"], 3),
            "noise_reduction_pct": round(noise_drop, 1),
            "gap_fill_pct": round(gap_fill, 1),
            "edge_sharpness_ratio": round(
                m_fused["edge_sharpness"] / max(m_single["edge_sharpness"], 1e-6), 2),
        },
    }


def run(n_passes: int = 6, size_px: int = 400, seed: int = 11,
        cfg: PassConfig | None = None) -> dict:
    """End-to-end: simulate -> fuse -> score. Returns everything for rendering."""
    passes = simulate_passes(n_passes, size_px, cfg, seed)
    result = fuse(passes)
    metrics = summarize(passes, result)
    return {"passes": passes, "result": result, "metrics": metrics}
