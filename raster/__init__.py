"""Airborne IR raster track — the imagery-side analog of ORBIT's ingestion.

Where the FIRMS client receives pre-processed point detections, an airborne IR
scanner produces raw thermal imagery. This module demonstrates that upstream
half: synthesize a georeferenced thermal frame, reproject it, threshold
hotspots, extract a perimeter from the raster (raster -> vector), write a
Cloud-Optimized GeoTIFF, and emit the SAME standardized detection schema the
rest of the pipeline already consumes.
"""
from raster.airborne import (
    extract_perimeter,
    frame_to_detections,
    render_overlay_png,
    reproject_to_4326,
    synthesize_thermal_frame,
    write_cog,
)

__all__ = [
    "synthesize_thermal_frame", "reproject_to_4326", "extract_perimeter",
    "frame_to_detections", "write_cog", "render_overlay_png",
]
