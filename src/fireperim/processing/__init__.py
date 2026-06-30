"""Processing pipeline: clustering, perimeter extraction, risk scoring.

Day 2: `cluster.py` (DBSCAN) and `perimeter.py` (alpha shapes).
Day 3 fills in `risk.py` (weather-driven spread risk score).
"""
from fireperim.processing.cluster import cluster_detections, cluster_summary
from fireperim.processing.perimeter import build_events

__all__ = ["cluster_detections", "cluster_summary", "build_events"]
