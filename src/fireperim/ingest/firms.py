"""NASA FIRMS ingestion — the satellite-thermal source for FirePerim Live.

Pulls active-fire detections from the FIRMS Area API (CSV), normalizes the
sensor-specific columns (VIIRS vs MODIS differ) into the standardized schema
defined in `base.py`, and returns a GeoDataFrame in EPSG:4326.

API shape:
  /api/area/csv/{MAP_KEY}/{SOURCE}/{west,south,east,north}/{DAY_RANGE}[/{DATE}]
"""
from __future__ import annotations

import io
import logging
from datetime import date

import pandas as pd
import requests
import geopandas as gpd

from fireperim.config import FIRMS_API_BASE, FIRMS_KEY_STATUS, MAX_DAY_RANGE
from fireperim.ingest.base import DETECTION_COLUMNS, DetectionSource

log = logging.getLogger(__name__)

# VIIRS confidence is categorical (l/n/h); MODIS is 0–100. Normalize to 0–100.
_VIIRS_CONF_MAP = {"l": 25.0, "n": 60.0, "h": 90.0}


class FirmsAuthError(RuntimeError):
    """MAP_KEY is missing, invalid, or out of transactions."""


class FirmsSource(DetectionSource):
    name = "FIRMS"

    def __init__(
        self,
        map_key: str,
        bbox: tuple[float, float, float, float],
        sensors: tuple[str, ...],
        day_range: int = 1,
        on_date: date | None = None,
        timeout: int = 30,
        session: requests.Session | None = None,
    ) -> None:
        if not map_key or map_key == "your_firms_map_key_here":
            raise FirmsAuthError(
                "No FIRMS MAP_KEY configured. Add FIRMS_MAP_KEY to "
                ".streamlit/secrets.toml (request a free key at "
                "https://firms.modaps.eosdis.nasa.gov/api/area/)."
            )
        self.map_key = map_key.strip()
        self.bbox = bbox
        self.sensors = tuple(sensors)
        self.day_range = max(1, min(int(day_range), MAX_DAY_RANGE))
        self.on_date = on_date
        self.timeout = timeout
        self._session = session or requests.Session()

    # ------------------------------------------------------------------ public
    def fetch(self) -> gpd.GeoDataFrame:
        """Fetch + merge all configured sensors into one standardized frame."""
        frames: list[pd.DataFrame] = []
        for sensor in self.sensors:
            raw = self._fetch_sensor(sensor)
            if raw is not None and not raw.empty:
                frames.append(self._normalize(raw, sensor))

        if not frames:
            return self.empty()

        merged = pd.concat(frames, ignore_index=True)
        gdf = gpd.GeoDataFrame(
            merged,
            geometry=gpd.points_from_xy(merged["longitude"], merged["latitude"]),
            crs="EPSG:4326",
        )
        return self.validate(gdf)

    def key_status(self) -> dict:
        """Return MAP_KEY transaction usage — handy as a sidebar health check."""
        try:
            r = self._session.get(
                FIRMS_KEY_STATUS,
                params={"MAP_KEY": self.map_key},
                timeout=self.timeout,
            )
            r.raise_for_status()
            return r.json()
        except Exception as exc:  # noqa: BLE001 — surface as a soft status
            log.warning("key_status failed: %s", exc)
            return {"error": str(exc)}

    # ----------------------------------------------------------------- private
    def _build_url(self, sensor: str) -> str:
        west, south, east, north = self.bbox
        area = f"{west},{south},{east},{north}"
        parts = [FIRMS_API_BASE, self.map_key, sensor, area, str(self.day_range)]
        if self.on_date is not None:
            parts.append(self.on_date.isoformat())
        return "/".join(parts)

    def _fetch_sensor(self, sensor: str) -> pd.DataFrame | None:
        url = self._build_url(sensor)
        try:
            r = self._session.get(url, timeout=self.timeout)
        except requests.RequestException as exc:
            log.warning("FIRMS request failed for %s: %s", sensor, exc)
            return None

        text = r.text or ""
        # FIRMS returns a plain-text error (not JSON, not CSV) on auth/limit issues.
        low = text.lower()
        if "invalid" in low and "map_key" in low:
            raise FirmsAuthError("FIRMS rejected the MAP_KEY (invalid).")
        if "transaction limit" in low or "exceeded" in low:
            raise FirmsAuthError("FIRMS MAP_KEY transaction limit reached.")
        if r.status_code != 200:
            log.warning("FIRMS %s returned HTTP %s", sensor, r.status_code)
            return None

        try:
            df = pd.read_csv(io.StringIO(text))
        except (pd.errors.EmptyDataError, pd.errors.ParserError):
            return None
        # A valid-but-empty response still has a header row -> df may be empty.
        if df.empty or "latitude" not in df.columns:
            return None
        return df

    @staticmethod
    def _normalize(df: pd.DataFrame, sensor: str) -> pd.DataFrame:
        """Map sensor-specific FIRMS columns onto the standardized schema."""
        out = pd.DataFrame()
        out["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
        out["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")

        # Acquisition time: acq_date (YYYY-MM-DD) + acq_time (HHMM, UTC).
        acq_time = df.get("acq_time", 0)
        time_str = acq_time.astype(str).str.zfill(4) if hasattr(acq_time, "astype") else "0000"
        out["acq_datetime"] = pd.to_datetime(
            df["acq_date"].astype(str) + time_str,
            format="%Y-%m-%d%H%M",
            utc=True,
            errors="coerce",
        )

        out["frp_mw"] = pd.to_numeric(df.get("frp"), errors="coerce")

        # Brightness: VIIRS uses bright_ti4 (4 µm channel); MODIS uses brightness.
        bright_col = "bright_ti4" if "bright_ti4" in df.columns else "brightness"
        out["brightness_k"] = pd.to_numeric(df.get(bright_col), errors="coerce")

        # Confidence: normalize categorical (VIIRS) and numeric (MODIS) to 0–100.
        conf_raw = df.get("confidence")
        out["confidence"], out["confidence_class"] = FirmsSource._normalize_confidence(conf_raw)

        out["daynight"] = df.get("daynight", pd.Series(["U"] * len(df))).astype(str)
        out["sensor"] = sensor
        out["satellite"] = df.get("satellite", pd.Series(["?"] * len(df))).astype(str)
        out["scan_km"] = pd.to_numeric(df.get("scan"), errors="coerce")
        out["track_km"] = pd.to_numeric(df.get("track"), errors="coerce")

        out = out.dropna(subset=["latitude", "longitude"])
        # Keep only the contract columns, in order.
        return out[list(DETECTION_COLUMNS)]

    @staticmethod
    def _normalize_confidence(conf_raw) -> tuple[pd.Series, pd.Series]:
        if conf_raw is None:
            n = 0
            return pd.Series([60.0] * n), pd.Series(["nominal"] * n)

        s = conf_raw.astype(str).str.strip().str.lower()
        # Categorical (VIIRS): l/n/h
        if s.isin(list(_VIIRS_CONF_MAP)).any():
            numeric = s.map(_VIIRS_CONF_MAP).fillna(60.0)
            cls = s.map({"l": "low", "n": "nominal", "h": "high"}).fillna("nominal")
            return numeric, cls
        # Numeric (MODIS): 0–100
        numeric = pd.to_numeric(conf_raw, errors="coerce").fillna(60.0)
        cls = pd.cut(
            numeric, bins=[-1, 30, 80, 101], labels=["low", "nominal", "high"]
        ).astype(str)
        return numeric, cls
