"""Generate the orthorectification (direct-georeferencing) demo artifacts.

Writes into web/public/ir/ortho/:
  oblique.png            the oblique sensor frame (distorted, keystoned grid)
  orthorectified.png     the north-up, georeferenced orthophoto (square grid)
  comparison.png         side-by-side before/after (the demo money shot)
  ortho.tif              georeferenced orthophoto GeoTIFF (opens in QGIS)
  bounds.json            EPSG:4326 bounds for a map overlay
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from raster import ortho as O  # noqa: E402

OUT = ROOT / "web" / "public" / "ir" / "ortho"
OUT.mkdir(parents=True, exist_ok=True)

STOPS = [(0.0, 15, 12, 25), (0.3, 150, 25, 15), (0.6, 235, 95, 20),
         (0.82, 255, 180, 40), (1.0, 255, 250, 215)]


def colorize(a):
    t = np.clip(a, 0, 1)
    r = np.interp(t, [s[0] for s in STOPS], [s[1] for s in STOPS])
    g = np.interp(t, [s[0] for s in STOPS], [s[2] for s in STOPS])
    b = np.interp(t, [s[0] for s in STOPS], [s[3] for s in STOPS])
    return np.dstack([r, g, b]).astype("uint8")


def main() -> int:
    cam = O.make_camera(alt=1800, off_nadir_deg=35, heading_deg=20)
    gc = O.ground_center(cam)
    oblique = O.render_oblique(cam, gc)
    ortho, truth, valid, origin, res = O.orthorectify(cam, oblique, gc)
    score = O.validation_score(ortho, truth, valid)
    print(f"camera: alt 1800 m, 35 deg off-nadir | validation r={score:.3f} "
          f"| coverage {100*valid.mean():.0f}%")

    ob_img = Image.fromarray(colorize(oblique), "RGB")
    or_img = Image.fromarray(colorize(ortho), "RGB")
    ob_img.save(OUT / "oblique.png")
    or_img.save(OUT / "orthorectified.png")

    # side-by-side comparison with labels + an arrow
    pad, gap, labelh = 16, 60, 34
    w = ob_img.width + or_img.width + gap + 2 * pad
    h = max(ob_img.height, or_img.height) + labelh + 2 * pad
    canvas = Image.new("RGB", (w, h), (14, 17, 23))
    canvas.paste(ob_img, (pad, labelh + pad))
    canvas.paste(or_img, (pad + ob_img.width + gap, labelh + pad))
    d = ImageDraw.Draw(canvas)
    d.text((pad + 6, 10), "Oblique sensor frame (raw)", fill=(230, 120, 60))
    d.text((pad + ob_img.width + gap + 6, 10),
           "Orthorectified  (north-up, georeferenced)", fill=(90, 210, 120))
    ay = labelh + pad + ob_img.height // 2
    ax = pad + ob_img.width + gap // 2
    d.line([(ax - 16, ay), (ax + 16, ay)], fill=(200, 200, 200), width=3)
    d.polygon([(ax + 16, ay - 7), (ax + 16, ay + 7), (ax + 26, ay)], fill=(200, 200, 200))
    canvas.save(OUT / "comparison.png")

    # georeference + write GeoTIFF + bounds
    transform, crs, bounds = O.georeference(origin, res, ortho.shape)
    with rasterio.open(OUT / "ortho.tif", "w", driver="GTiff", height=ortho.shape[0],
                       width=ortho.shape[1], count=1, dtype="float32", crs=crs,
                       transform=transform, compress="deflate") as dst:
        dst.write(ortho, 1)
    (OUT / "bounds.json").write_text(json.dumps(bounds, indent=2))

    # --- full airborne chain: oblique thermal frame -> ortho -> detections
    #     -> cluster -> perimeter (the same downstream pipeline) ---
    from fireperim.processing import build_events, cluster_detections
    dets, _ortho_k, _tf, _crs, _b = O.ortho_thermal_to_detections()
    events = build_events(
        cluster_detections(dets, eps_m=40, min_samples=4), alpha_per_m=0.05)
    from fireperim.export import events_to_geojson
    (OUT / "chain_perimeter.geojson").write_text(events_to_geojson(events))
    print(f"full airborne chain: oblique thermal frame -> {len(dets)} detections "
          f"-> {len(events)} fire event(s) -> perimeter.geojson")
    print(f"wrote artifacts to {OUT} | bounds {bounds}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
