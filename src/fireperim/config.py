"""Central configuration: regions, sensors, and processing defaults.

Bounding boxes are (west, south, east, north) in EPSG:4326 degrees — the order
the FIRMS Area API expects.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# Projected CRS used for distance-based work (clustering, alpha shapes, buffers).
# US National Atlas Equal Area (meters). Good enough CONUS-wide; for a single
# incident you would reproject to the local UTM zone.
WORKING_CRS = "EPSG:5070"
GEOGRAPHIC_CRS = "EPSG:4326"


@dataclass(frozen=True)
class Region:
    key: str
    label: str
    bbox: tuple[float, float, float, float]  # west, south, east, north
    center: tuple[float, float]               # lat, lon — for map default view
    zoom: int


REGIONS: dict[str, Region] = {
    "california": Region(
        key="california",
        label="California / US West",
        bbox=(-124.48, 32.53, -114.13, 42.01),
        center=(37.5, -119.5),
        zoom=6,
    ),
    "us_west": Region(
        key="us_west",
        label="US West (CA/OR/WA/NV/ID/AZ)",
        bbox=(-124.85, 31.3, -108.0, 49.1),
        center=(42.0, -116.5),
        zoom=5,
    ),
    "conus": Region(
        key="conus",
        label="Continental US",
        bbox=(-125.0, 24.4, -66.9, 49.4),
        center=(39.5, -98.0),
        zoom=4,
    ),
}

DEFAULT_REGION = "california"


# FIRMS active-fire products. VIIRS at 375 m is the closest free analog to an
# airborne IR scanner's resolution, so it is the default. NRT = Near Real-Time.
SENSORS: dict[str, str] = {
    "VIIRS_SNPP_NRT": "VIIRS Suomi-NPP (375 m, NRT)",
    "VIIRS_NOAA20_NRT": "VIIRS NOAA-20 (375 m, NRT)",
    "VIIRS_NOAA21_NRT": "VIIRS NOAA-21 (375 m, NRT)",
    "MODIS_NRT": "MODIS (1 km, NRT)",
}

DEFAULT_SENSORS: tuple[str, ...] = ("VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT")


@dataclass
class ProcessingParams:
    """Tunable knobs surfaced in the Streamlit sidebar on later days."""
    # DBSCAN (Day 2)
    cluster_eps_m: float = 1500.0      # neighborhood radius in meters
    cluster_min_samples: int = 4       # min detections to seed a fire event
    # Alpha shape (Day 2). Larger alpha -> tighter, more concave hull.
    alpha: float = 0.0008
    # Risk scoring (Day 3)
    min_event_detections: int = 3
    params: dict = field(default_factory=dict)


FIRMS_API_BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
FIRMS_KEY_STATUS = "https://firms.modaps.eosdis.nasa.gov/mapserver/mapkey_status/"
MAX_DAY_RANGE = 5  # FIRMS Area API hard limit
