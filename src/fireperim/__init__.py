"""FirePerim Live — a satellite-data analog of the ORBIT Data Engine.

ORBIT ingests thermal imagery from airborne IR scanners on firefighting
aircraft, extracts fire perimeters, and publishes georeferenced outputs to
agency GIS systems. FirePerim Live implements the same downstream architecture
(cluster -> perimeter -> weather -> risk -> agency export) against free
satellite thermal detections (NASA VIIRS/FIRMS).

Swap the ingestion layer (`fireperim.ingest`) and you have ORBIT.
"""

__version__ = "0.1.0"
