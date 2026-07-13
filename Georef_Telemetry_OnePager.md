# Direct georeferencing from real telemetry — the alignment front-end for fusion

**Closing the "frames assume they're already aligned" gap with real onboard pose, not simulation.**

---

## The gap this addresses

The multi-pass fusion demo assumed the passes were already co-registered. In the real world they aren't — each pass has to be *georeferenced* (put onto real ground coordinates) before it can be stacked. That needs camera pose (GNSS/IMU) plus a ground model. This is the front-end that was missing.

## What I built

`raster/georef.py` — direct georeferencing that takes each frame's **real onboard telemetry** and projects the image onto the ground, with **no ground-control points and no image-based matching**:

- **Camera position** — GPS latitude/longitude + altitude, straight from the frame.
- **Boresight (the clever part)** — the DJI M30T's **laser rangefinder** records the lat/lon/altitude of the exact ground point it's aimed at. The camera-to-target vector *is* the measured optical axis, so it carries the heading that isn't in the metadata — no guessing at yaw.
- **Roll** — the gimbal is roll-stabilized, so image "up" is world-up projected onto the image plane (standard gimballed-camera assumption).
- **Ground** — a local plane at the rangefinder's measured altitude. A DEM drops straight into the same hook for terrain-aware ortho.

From that it projects any pixel to ground coordinates, produces a north-up orthorectified frame, and computes each pass's ground footprint.

## The result (real FLAME 3 data, Sycan Marsh burn)

I took **8 oblique passes** over the same burn — cameras spread across **413 m**, slant ranges 150–220 m — and georeferenced each from telemetry alone. They **co-locate on the burn to roughly 10 m** (range 2–23 m) with zero image alignment. The footprint panel shows all eight independently-projected frames landing on the common target. See `Georef_Telemetry_Demo.png`.

## The honest limitation — and why it points somewhere useful

These are **low-altitude, grazing oblique** drone frames (≈17° depression) over 3-D forest. A flat-ground projection aligns the *ground plane* but can't remove the **height-driven parallax** of trees seen from a 413 m baseline — which is exactly why the orthorectified frame smears in the far field, and why pixel-level fusion of these particular frames blurs rather than sharpens. That residual parallax is the precise reason the next increment is a **DEM (or SfM bundle adjustment)** — the flat-plane assumption is the thing to replace.

Here's the part that matters for ORBIT: **that parallax shrinks dramatically at ORBIT's geometry.** An airborne IR line-scanner flying high and near-nadir sees far less relief displacement than a 55 m-AGL drone shooting at 17°. So the same telemetry-ortho front-end that's parallax-limited on this consumer drone data would align *cleanly* on ORBIT's operational passes — and then feed directly into the multi-pass fusion.

## Where it slots in

```
telemetry (GPS + IMU/LRF)  ->  georef.py (direct georeferencing)  ->  common ground grid
   ->  [DEM / light image refinement]  ->  multi-pass fusion  ->  clean composite  ->  perimeter -> export
```

The georeferencing is the missing front-end; the fusion is the back-end you've already seen. Together they're the real pipeline, and every stage now runs on real data.

## Honest scope

Real pose, real projection, real accuracy number — no simulation. The flat-plane ground model is first-order (DEM-ready), the roll is assumed gimbal-stabilized, and clean multi-view pixel fusion on this wide-baseline oblique set needs the DEM/SfM step. The method and the telemetry are proven; the terrain model is the next build.

---

*Artifacts: `Georef_Telemetry_Demo.png`, `Georef_Telemetry_metrics.json`. Code: `raster/georef.py` (read_pose · camera_basis · ground_from_pixel · orthorectify · footprint_quad · reprojection check).*
