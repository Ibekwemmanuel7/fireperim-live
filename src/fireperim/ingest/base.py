"""The ingestion contract.

This is the seam in the architecture. ORBIT ingests airborne IR scanner frames;
FirePerim ingests satellite thermal detections. Both produce a GeoDataFrame with
exactly these columns, so the rest of the pipeline never knows or cares which
sensor produced the heat.
"""
from __future__ import annotations

import abc

import geopandas as gpd

# The standardized detection schema. A "detection" is one georeferenced thermal
# anomaly (a hot pixel from a satellite, or a hot patch from an IR frame).
DETECTION_COLUMNS: dict[str, str] = {
    "latitude": "float64",
    "longitude": "float64",
    "acq_datetime": "datetime64[ns, UTC]",  # acquisition time, UTC
    "frp_mw": "float64",        # fire radiative power (MW) — energy proxy
    "brightness_k": "float64",  # channel brightness temperature (Kelvin)
    "confidence": "float64",    # normalized 0–100
    "confidence_class": "object",  # low | nominal | high
    "daynight": "object",       # D | N
    "sensor": "object",         # source label, e.g. VIIRS_SNPP_NRT
    "satellite": "object",      # platform code
    "scan_km": "float64",       # along-scan footprint (km)
    "track_km": "float64",      # along-track footprint (km)
    # geometry: shapely Point(longitude, latitude), CRS EPSG:4326
}


class DetectionSource(abc.ABC):
    """Abstract source of thermal detections.

    Implement `fetch()` to return a GeoDataFrame conforming to
    `DETECTION_COLUMNS` (+ a `geometry` column in EPSG:4326). That is the entire
    contract. Subclass this for FIRMS, for an airborne IR feed, for a replayed
    incident archive — the pipeline downstream is identical.
    """

    name: str = "abstract"

    @abc.abstractmethod
    def fetch(self) -> gpd.GeoDataFrame:
        """Return standardized detections for the configured area/time."""
        raise NotImplementedError

    @staticmethod
    def empty() -> gpd.GeoDataFrame:
        """An empty, correctly-typed detection frame (used when no fires found)."""
        gdf = gpd.GeoDataFrame(
            {col: [] for col in DETECTION_COLUMNS},
            geometry=[],
            crs="EPSG:4326",
        )
        return gdf

    @staticmethod
    def validate(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Assert the frame honors the contract. Cheap insurance at the seam."""
        missing = set(DETECTION_COLUMNS) - set(gdf.columns)
        if missing:
            raise ValueError(f"Detection frame missing columns: {sorted(missing)}")
        if gdf.crs is None or gdf.crs.to_epsg() != 4326:
            raise ValueError("Detection frame must be in EPSG:4326")
        return gdf
