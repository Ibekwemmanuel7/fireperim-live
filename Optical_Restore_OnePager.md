# Seeing Through Smoke — single-frame image-quality restoration

**A working solution to the poor-image-quality problem you showed me, run on real FLAME 3 airborne fire imagery.**

---

## The problem (as you framed it)

The optical frames coming off the aircraft over an active fire are often **washed out by smoke and haze** — low contrast, no colour, the fire front and the ground underneath barely visible. A crew looking at that frame can't see where the fire actually is. The screenshot you showed me was exactly this: a grey, smoke-veiled image with the signal buried.

## The core idea

This is a **single-frame restoration** problem, not a better-camera problem. Smoke/haze follows a physical model — each pixel is the true scene attenuated by transmission through the smoke plus scattered "airlight." If you estimate that transmission, you can invert the model and pull the true scene back out. No second pass, no extra hardware — **one image in, one clean image out**, in a fraction of a second.

## What I built

`raster/optical_restore.py` — two restoration chains, every step a standard, citable technique:

- **Standard:** gray-world white balance → CLAHE adaptive contrast → edge-preserving denoise → unsharp detail recovery.
- **SOTA:** the above **plus dark-channel-prior (DCP) dehazing** with guided-filter transmission refinement (He, Sun & Tang, CVPR 2009 — the reference method for haze removal), which physically strips the smoke veil before contrast/detail recovery.

It ships with **no-reference quality metrics** (no clean ground truth needed): contrast, sharpness, entropy, colourfulness, haze density, and the Hautiere "newly-visible-edge" ratio used to score dehazing.

## Results — on the real smoke-degraded frame (FLAME 3, Sycan Marsh, frame 00271)

| Metric | Degraded frame | SOTA restore | Change |
|---|---|---|---|
| Haze density (dark channel) | 0.59 | 0.21 | **−64%** |
| Sharpness (Laplacian var) | 36 | ~620 | **~17× sharper** |
| Newly-visible edges | 1.0× | 8.0× | **8× more visible structure** |
| Contrast | 40 | 41 | +3.5% |

More importantly than the numbers: in the restored frame you can now **see the active fire line, individual trees, the burn scar and the ridgeline** — all of which were invisible under the smoke. See `Optical_Restore_Demo.png`.

## Why this maps onto ORBIT

- It's a **pre-processing stage** that sits in front of everything else: restore the frame first, then detect / cluster / perimeter / export — cleaner input, better perimeters.
- It pairs directly with the thermal side of the platform: **thermal sees through smoke to locate heat; this makes the *optical* frame usable for the human-readable visual context** the crews actually look at. Two sensors, both cleaned.
- Pure CPU, single frame, sub-second — it runs **in-flight on the same edge box** that streams the imagery, no cloud round-trip.
- Same modular pattern as the multi-pass fusion track: a `standard` and a `sota` chain behind one call, swappable.

## Honest scope

The physics-based dehaze can only recover detail that's **still present under the smoke** — where the plume is optically thick (top-left of the frame), there's no signal to bring back and the method correctly leaves it hazy rather than inventing detail. The gains are measured with no-reference metrics on one real frame; the obvious next step is to batch it across a burn sequence and, if you want the last increment, fine-tune a learned dehazer (e.g. a lightweight DehazeFormer) on your own smoke imagery. The classical DCP chain here needs **zero training data** and already does most of the work.

---

*Artifacts: `Optical_Restore_Demo.png` (before / standard / SOTA), `Optical_Restore_metrics.json` (scores). Code: `raster/optical_restore.py`. Runs on any RGB frame: `restore(image, method="sota")`.*
