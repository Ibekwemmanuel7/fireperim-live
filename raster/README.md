# Airborne IR raster track

The imagery-side analog of ORBIT's ingestion. Where the FIRMS client receives
pre-processed **point detections**, an airborne IR scanner produces raw thermal
**imagery**. This module demonstrates that upstream half with real geospatial
techniques (the input frame is synthesized and clearly labelled *simulated*, but
the processing would run unchanged on a true scanner frame):

1. **Synthesize** a georeferenced thermal frame (UTM, 5 m pixels) — a wind-driven
   fire front + spot fires, values in Kelvin brightness temperature.
2. **Reproject** it to EPSG:4326 (`rasterio.warp`).
3. **Threshold** hot pixels and **polygonize** (raster → vector) into a fire
   perimeter (`rasterio.features.shapes` + Shapely).
4. **Write a Cloud-Optimized GeoTIFF** (internal tiling + overviews).
5. **Render** a heat-ramp PNG overlay + bounds for the map UI.
6. **Swap-seam proof:** emit the frame's hot pixels as the *same standardized
   detection schema* the satellite pipeline consumes, and run them through the
   identical clustering + perimeter stages.

## Regenerate artifacts

```bash
pip install -r raster/requirements.txt
python scripts/build_raster_demo.py     # writes web/public/ir/{thermal_overlay.png,
                                        # bounds.json, perimeter.geojson, thermal_cog.tif}
```

The React app loads those artifacts and overlays the thermal frame + its
raster-derived perimeter on the Mapbox map ("Airborne IR" toggle).

## Why this matters for the role

It exercises the airborne-specific skills the satellite demo doesn't:
reprojection, thermal thresholding, **COG generation**, raster→vector, and
serving processed imagery to a map UI — i.e. the "tiling, reprojection, COG
generation, serving imagery to map-based UIs" line in the job description. In
production the COG lands on object storage behind a dynamic tiler (e.g. TiTiler)
serving XYZ tiles; the same processing runs in a cloud worker per scanner frame.

---

## Orthorectification (direct georeferencing) — `ortho.py`

An airborne scanner sees the ground **obliquely**, distorted by the aircraft's
position and attitude. Orthorectification removes that distortion by projecting
each pixel to true ground coordinates using the sensor pose (+ terrain). For a
line/frame sensor this is **direct georeferencing** (project with the GNSS/IMU
pose) — *not* structure-from-motion / bundle adjustment (OpenDroneMap, Pix4D),
which is for overlapping frame photography. Knowing which one ORBIT's scanner
needs is the point.

`ortho.py` is a **self-validating concept demo** of that core operation:

1. Define a camera pose (position + attitude) and an analytic ground scene.
2. Render the **oblique** sensor image (what the scanner sees).
3. **Orthorectify** it to a north-up, georeferenced grid via the collinearity
   equations + indirect resampling.
4. **Validate:** the orthophoto reconstructs the ground truth — correlation
   ~0.96 (see `tests/test_ortho.py`).

```bash
python scripts/build_ortho_demo.py   # -> web/public/ir/ortho/{comparison.png,
                                      # oblique.png, orthorectified.png, ortho.tif, bounds.json}
```

`comparison.png` is the before/after: a keystoned oblique grid vs the corrected
square grid. The terrain is a flat plane here for clarity; swapping it for a DEM
(`Z = DEM(X, Y)`) makes it full terrain orthorectification with the same maths.
**Honest framing:** this demonstrates the geometry of the core operation; a
production pipeline also needs real GNSS/IMU telemetry, sensor/boresight
calibration, and a DEM (via GDAL `gdalwarp`, geolocation arrays, or RPCs).
