"""Build the multi-pass IR fusion demo artifacts.

Outputs (to web/public/ir/multipass/ and the repo root for presentation):
  comparison.png   single passes vs naive average vs full fusion vs truth
  fused_multipass.tif    georeferenced Cloud-Optimized GeoTIFF of the fused image
  metrics.json     PSNR / SSIM / noise / gap-fill / edge-sharpness table

Run:  python scripts/build_multipass_demo.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import cm

import rasterio
from affine import Affine
from pyproj import Transformer
from rasterio.crs import CRS

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "raster"))
import multipass as mp  # noqa: E402

OUT_WEB = ROOT / "web" / "public" / "ir" / "multipass"
OUT_WEB.mkdir(parents=True, exist_ok=True)

CENTER_LAT, CENTER_LON, RES_M = 37.851, -119.551, 3.0
VMIN, VMAX = mp.BACKGROUND_K, mp.PEAK_K
CMAP = "inferno"


def north_up_affine(size_px: int):
    epsg = 32600 + int((CENTER_LON + 180) // 6) + 1
    to_utm = Transformer.from_crs(CRS.from_epsg(4326), CRS.from_epsg(epsg), always_xy=True)
    cx, cy = to_utm.transform(CENTER_LON, CENTER_LAT)
    half = size_px * RES_M / 2.0
    return Affine(RES_M, 0, cx - half, 0, -RES_M, cy + half), epsg


def write_cog(path: Path, arr: np.ndarray, size_px: int):
    transform, epsg = north_up_affine(size_px)
    profile = dict(
        driver="COG", dtype="float32", count=1, height=size_px, width=size_px,
        crs=CRS.from_epsg(epsg), transform=transform, nodata=np.nan,
        compress="deflate", blocksize=256,
    )
    try:
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(arr.astype("float32"), 1)
    except Exception:
        profile["driver"] = "GTiff"; profile.pop("blocksize", None); profile["tiled"] = True
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(arr.astype("float32"), 1)


def write_web_overlay(png_path: Path, bounds_path: Path, arr: np.ndarray, size_px: int):
    """Colorized RGBA overlay (transparent cool background) + lat/lon bounds.json,
    matching the airborne/ortho overlay convention the Mapbox app already uses."""
    from matplotlib.colors import Normalize
    norm = Normalize(vmin=VMIN, vmax=VMAX)
    rgba = cm.get_cmap(CMAP)(norm(np.nan_to_num(arr, nan=VMIN)))
    # alpha ramps in over the low end so cool background is see-through
    t = np.clip((arr - (VMIN + 0.12 * (VMAX - VMIN))) / (0.25 * (VMAX - VMIN)), 0, 1)
    t = np.where(np.isfinite(arr), t, 0.0)
    rgba[..., 3] = t
    from PIL import Image
    Image.fromarray((rgba * 255).astype("uint8"), "RGBA").save(png_path)

    transform, epsg = north_up_affine(size_px)
    to_geo = Transformer.from_crs(CRS.from_epsg(epsg), CRS.from_epsg(4326), always_xy=True)
    xs = [transform.c, transform.c + transform.a * size_px]
    ys = [transform.f, transform.f + transform.e * size_px]
    lon_w, _ = to_geo.transform(xs[0], ys[0]); lon_e, _ = to_geo.transform(xs[1], ys[0])
    _, lat_n = to_geo.transform(xs[0], ys[0]); _, lat_s = to_geo.transform(xs[0], ys[1])
    bounds_path.write_text(json.dumps(
        {"west": lon_w, "south": lat_s, "east": lon_e, "north": lat_n}, indent=2))


def render_comparison(out: Path, passes, result, metrics, size_px):
    truth = mp.truth_scene(size_px, grow=max(p.t for p in passes))
    single = passes[len(passes) // 2].image
    fig, axes = plt.subplots(2, 3, figsize=(13.5, 9), constrained_layout=True)

    def show(ax, img, title, sub=None):
        ax.imshow(img, cmap=CMAP, vmin=VMIN, vmax=VMAX)
        ax.set_title(title, fontsize=12, fontweight="bold")
        if sub:
            ax.text(0.5, -0.06, sub, transform=ax.transAxes, ha="center",
                    va="top", fontsize=9.5, color="#333")
        ax.set_xticks([]); ax.set_yticks([])

    show(axes[0, 0], passes[0].image, "Single pass #1",
         "noisy · striped · gap · mis-registered")
    show(axes[0, 1], single, "Single pass #%d" % (len(passes) // 2 + 1),
         "PSNR %.1f dB · noise %.1f K" % (
             metrics["single_pass"]["psnr_db"], metrics["single_pass"]["bg_noise_std_k"]))
    show(axes[0, 2], passes[-1].image, "Single pass #%d (latest)" % len(passes),
         "most recent look")

    show(axes[1, 0], result["naive"], "Naive average",
         "PSNR %.1f dB · still noisy/smeared" % metrics["naive_average"]["psnr_db"])
    show(axes[1, 1], result["fused"], "FULL FUSION",
         "PSNR %.1f dB · noise %.1f K" % (
             metrics["full_fusion"]["psnr_db"], metrics["full_fusion"]["bg_noise_std_k"]))
    show(axes[1, 2], truth, "Ground truth", "(reference)")

    imp = metrics["improvements"]
    fig.suptitle(
        "Multi-pass airborne IR fusion  —  %d passes  →  one clean image\n"
        "+%.1f dB PSNR   ·   noise −%.0f%%   ·   %.0f%% gaps filled   ·   %.1f× sharper edges"
        % (result["n_passes"], imp["psnr_gain_db"], imp["noise_reduction_pct"],
           imp["gap_fill_pct"], imp["edge_sharpness_ratio"]),
        fontsize=14, fontweight="bold")
    sm = cm.ScalarMappable(cmap=CMAP,
                           norm=plt.Normalize(vmin=VMIN, vmax=VMAX))
    cb = fig.colorbar(sm, ax=axes, shrink=0.6, location="right", pad=0.01)
    cb.set_label("Brightness temperature (K)", fontsize=10)
    fig.savefig(out, dpi=130, bbox_inches="tight")
    plt.close(fig)


def main():
    n, size = 6, 400
    run = mp.run(n_passes=n, size_px=size, seed=11)
    passes, result, metrics = run["passes"], run["result"], run["metrics"]

    render_comparison(OUT_WEB / "comparison.png", passes, result, metrics, size)
    render_comparison(ROOT / "MultiPass_Fusion_Demo.png", passes, result, metrics, size)
    for cog in (OUT_WEB / "fused_multipass.tif", ROOT / "MultiPass_Fusion_fused_cog.tif"):
        try:
            if cog.exists():
                cog.unlink()
            write_cog(cog, result["fused"], size)
        except Exception as e:            # locked mount leftover -- non-fatal
            print("  (skipped COG %s: %s)" % (cog.name, e))
    write_web_overlay(OUT_WEB / "overlay.png", OUT_WEB / "bounds.json", result["fused"], size)
    (OUT_WEB / "metrics.json").write_text(json.dumps(metrics, indent=2))
    (ROOT / "MultiPass_Fusion_metrics.json").write_text(json.dumps(metrics, indent=2))

    imp = metrics["improvements"]
    print("Multi-pass fusion demo built:")
    print("  passes: %d   size: %dx%d" % (n, size, size))
    print("  PSNR gain: +%.1f dB   noise: -%.0f%%   gap-fill: %.0f%%   sharpness: %.1fx"
          % (imp["psnr_gain_db"], imp["noise_reduction_pct"],
             imp["gap_fill_pct"], imp["edge_sharpness_ratio"]))
    print("  -> web/public/ir/multipass/{comparison.png,fused_multipass.tif,metrics.json}")
    print("  -> MultiPass_Fusion_Demo.png, MultiPass_Fusion_metrics.json")


if __name__ == "__main__":
    main()
