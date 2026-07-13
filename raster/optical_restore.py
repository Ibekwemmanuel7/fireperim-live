"""
optical_restore.py — single-frame image-quality restoration for airborne optical imagery.

Built for the FirePerim / ORBIT context: aircraft optical frames over a fire are degraded by
SMOKE/HAZE, low contrast, colour cast, sensor noise and mild blur. This module recovers a
clean, high-contrast frame from ONE image (no second look required), so the fire front and
terrain become visible again.

Two chains, both made of standard, citable techniques:

  standard  : gray-world white balance -> CLAHE contrast -> bilateral denoise -> unsharp mask
  sota      : the above PLUS dark-channel-prior (DCP) dehazing with guided-filter transmission
              refinement (He, Sun & Tang, CVPR 2009) to physically strip the smoke veil.

No-reference quality metrics (no clean ground truth needed):
  contrast (global std), sharpness (variance of Laplacian), entropy, colourfulness (Hasler-Susstrunk),
  haze density (mean dark channel), and the dehazing 'e' metric (Hautiere et al. 2008 — ratio of
  newly-visible edges after restoration).

Dependencies: numpy, opencv (cv2). Pure-CPU, runs on a single frame in well under a second at 1 MP.
"""
from __future__ import annotations
import numpy as np
import cv2


# ----------------------------------------------------------------------------- helpers
def _to_float(bgr: np.ndarray) -> np.ndarray:
    return bgr.astype(np.float32) / 255.0


def _to_u8(bgr: np.ndarray) -> np.ndarray:
    return np.clip(bgr * 255.0, 0, 255).astype(np.uint8)


def gray_world_wb(bgr: np.ndarray) -> np.ndarray:
    """Gray-world white balance: neutralize the smoke/atmosphere colour cast."""
    f = _to_float(bgr)
    means = f.reshape(-1, 3).mean(0) + 1e-6
    g = means.mean()
    return _to_u8(f * (g / means))


def clahe_contrast(bgr: np.ndarray, clip: float = 2.5, grid: int = 8) -> np.ndarray:
    """Contrast-limited adaptive histogram equalization on luminance (L in LAB)."""
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(clipLimit=clip, tileGridSize=(grid, grid)).apply(l)
    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)


def bilateral_denoise(bgr: np.ndarray, d: int = 5, sc: float = 40, ss: float = 40) -> np.ndarray:
    """Edge-preserving denoise (keeps the fire edge crisp while smoothing sensor noise)."""
    return cv2.bilateralFilter(bgr, d, sc, ss)


def unsharp(bgr: np.ndarray, amount: float = 0.5, sigma: float = 2.0) -> np.ndarray:
    """Unsharp mask: restore mid/high-frequency detail lost to atmospheric blur."""
    blur = cv2.GaussianBlur(bgr, (0, 0), sigma)
    out = cv2.addWeighted(bgr, 1 + amount, blur, -amount, 0)
    return out


# ----------------------------------------------------------------------------- dehazing (DCP)
def dark_channel(bgr: np.ndarray, patch: int = 15) -> np.ndarray:
    minc = bgr.min(axis=2)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (patch, patch))
    return cv2.erode(minc, k)


def estimate_airlight(bgr: np.ndarray, dc: np.ndarray, top: float = 0.001) -> np.ndarray:
    """Atmospheric light A = brightest pixels within the haziest (dark-channel) region."""
    flat = dc.reshape(-1)
    n = max(int(flat.size * top), 1)
    idx = np.argpartition(flat, -n)[-n:]
    pix = bgr.reshape(-1, 3)[idx]
    return pix.mean(0)


def guided_filter(guide: np.ndarray, src: np.ndarray, r: int = 40, eps: float = 1e-3) -> np.ndarray:
    """Edge-aware refinement of the transmission map (He et al. guided filter)."""
    g = guide.astype(np.float32)
    p = src.astype(np.float32)
    mean = lambda x: cv2.boxFilter(x, cv2.CV_32F, (r, r))
    mg, mp = mean(g), mean(p)
    mgp = mean(g * p)
    cov = mgp - mg * mp
    mgg = mean(g * g)
    var = mgg - mg * mg
    a = cov / (var + eps)
    b = mp - a * mg
    return mean(a) * g + mean(b)


def dehaze_dcp(bgr: np.ndarray, omega: float = 0.88, t0: float = 0.16,
               patch: int = 15) -> tuple[np.ndarray, np.ndarray]:
    """
    Dark-Channel-Prior dehazing (He, Sun & Tang 2009). Physically strips the smoke veil:
      I = J*t + A*(1-t)  ->  J = (I - A)/max(t, t0) + A
    Returns (dehazed_u8, transmission_map).
    """
    f = _to_float(bgr)
    A = estimate_airlight(f, dark_channel(f, patch))
    A = np.maximum(A, 1e-3)
    norm = f / A
    t = 1.0 - omega * dark_channel(norm, patch)               # coarse transmission
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    t = guided_filter(gray, t, r=40, eps=1e-3)                # refined transmission
    t = np.clip(t, t0, 1.0)[..., None]
    J = (f - A) / t + A
    return _to_u8(J), (t[..., 0])


# ----------------------------------------------------------------------------- chains
def restore(bgr: np.ndarray, method: str = "sota") -> dict:
    """
    Run a restoration chain and return {'result', 'stages', 'transmission'}.
      standard: WB -> CLAHE -> denoise -> unsharp
      sota    : WB -> DCP dehaze -> CLAHE -> denoise -> unsharp
    """
    stages = {}
    x = gray_world_wb(bgr); stages["white_balance"] = x
    trans = None
    if method == "sota":
        x, trans = dehaze_dcp(x); stages["dehaze"] = x
    x = clahe_contrast(x); stages["clahe"] = x
    x = bilateral_denoise(x); stages["denoise"] = x
    x = unsharp(x); stages["unsharp"] = x
    return {"result": x, "stages": stages, "transmission": trans}


# ----------------------------------------------------------------------------- metrics
def _colourfulness(bgr: np.ndarray) -> float:
    b, g, r = [c.astype(np.float32) for c in cv2.split(bgr)]
    rg = r - g
    yb = 0.5 * (r + g) - b
    return float(np.sqrt(rg.std()**2 + yb.std()**2) + 0.3 * np.sqrt(rg.mean()**2 + yb.mean()**2))


def _entropy(gray: np.ndarray) -> float:
    h = np.bincount(gray.reshape(-1), minlength=256).astype(np.float64)
    p = h / max(h.sum(), 1)
    p = p[p > 0]
    return float(-(p * np.log2(p)).sum())


def visible_edges(gray: np.ndarray, thresh: float = 12.0) -> int:
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.hypot(gx, gy)
    return int((mag > thresh).sum())


def metrics(bgr: np.ndarray) -> dict:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return {
        "contrast": round(float(gray.std()), 2),
        "sharpness": round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 1),
        "entropy": round(_entropy(gray), 3),
        "colourfulness": round(_colourfulness(bgr), 2),
        "haze_density": round(float(dark_channel(_to_float(bgr)).mean()), 4),
        "visible_edges": visible_edges(gray),
    }


def compare(before: np.ndarray, after: np.ndarray) -> dict:
    mb, ma = metrics(before), metrics(after)
    e = ma["visible_edges"] / max(mb["visible_edges"], 1)     # Hautiere restoration ratio
    return {
        "before": mb, "after": ma,
        "contrast_gain_pct": round((ma["contrast"] / max(mb["contrast"], 1e-6) - 1) * 100, 1),
        "sharpness_gain_x": round(ma["sharpness"] / max(mb["sharpness"], 1e-6), 2),
        "haze_reduction_pct": round((1 - ma["haze_density"] / max(mb["haze_density"], 1e-6)) * 100, 1),
        "newly_visible_edge_ratio": round(e, 2),
    }
