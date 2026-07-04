"""Generate the airborne-IR raster demo artifacts.

Runs the raster track end-to-end and writes web-servable outputs into
web/public/airborne/:  thermal_overlay.png, bounds.json, perimeter.geojson,
detections.geojson, and thermal_cog.tif (a downloadable Cloud-Optimized GeoTIFF).

It also proves the swap seam: the synthetic frame's hot pixels are emitted as the
standardized detection schema and pushed through the SAME clustering + perimeter
pipeline used for satellite data.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from raster import airborne as A  # noqa: E402
from fireperim.processing import build_events, cluster_detections  # noqa: E402

OUT = ROOT / "web" / "public" / "ir"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> int:
    # 1. Synthesize a simulated airborne IR frame (UTM, 5 m pixels).
    bt, transform, crs = A.synthesize_thermal_frame()
    print(f"frame: {bt.shape} px, CRS {crs.to_epsg()}, "
          f"BT range {bt.min():.0f}-{bt.max():.0f} K")

    # 2. Write a Cloud-Optimized GeoTIFF (the processed-imagery artifact).
    cog = A.write_cog(bt, transform, crs, OUT / "thermal_cog.tif")
    print(f"COG: {Path(cog).name} ({Path(cog).stat().st_size//1024} KB)")

    # 3. Reproject to EPSG:4326 for web display; render heat-ramp PNG + bounds.
    bt_geo, geo_transform, bounds = A.reproject_to_4326(bt, transform, crs)
    A.render_overlay_png(bt_geo, OUT / "thermal_overlay.png")
    A.write_bounds_json(bounds, OUT / "bounds.json")
    print(f"overlay PNG + bounds: {bounds}")

    # 4. Raster -> vector: extract a perimeter directly from the imagery.
    perim, stats = A.extract_perimeter(bt, transform, crs)
    (OUT / "perimeter.geojson").write_text(perim.to_json(drop_id=True))
    print(f"raster-derived perimeter: {stats}")

    # 5. Swap-seam proof: emit standardized detections, run the SAME pipeline.
    dets = A.frame_to_detections(bt, transform, crs)
    events = build_events(cluster_detections(dets, eps_m=200, min_samples=4),
                          alpha_per_m=0.02)
    print(f"swap-seam: {len(dets)} airborne detections -> "
          f"{len(events)} fire event(s) via the satellite pipeline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
