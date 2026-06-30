"""Ingestion layer — the one piece you swap to turn FirePerim into ORBIT.

Every source emits the same standardized detection schema (see `base.py`), so
everything downstream (clustering, perimeters, weather, risk, export) is
source-agnostic. FIRMS satellite detections today; airborne IR scanner frames
tomorrow.
"""
from fireperim.ingest.base import DETECTION_COLUMNS, DetectionSource
from fireperim.ingest.firms import FirmsSource

__all__ = ["DetectionSource", "DETECTION_COLUMNS", "FirmsSource"]
