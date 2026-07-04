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
