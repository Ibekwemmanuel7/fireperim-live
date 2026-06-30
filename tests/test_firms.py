"""Tests for the FIRMS ingestion layer — the contract everything depends on."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from fireperim.ingest.base import DETECTION_COLUMNS, DetectionSource
from fireperim.ingest.firms import FirmsAuthError, FirmsSource

SAMPLE = Path(__file__).parents[1] / "data" / "sample" / "viirs_california_sample.csv"


def test_missing_key_raises():
    with pytest.raises(FirmsAuthError):
        FirmsSource(map_key="", bbox=(-1, -1, 1, 1), sensors=("VIIRS_SNPP_NRT",))
    with pytest.raises(FirmsAuthError):
        FirmsSource(
            map_key="your_firms_map_key_here",
            bbox=(-1, -1, 1, 1),
            sensors=("VIIRS_SNPP_NRT",),
        )


def test_url_build():
    src = FirmsSource(
        map_key="ABC123",
        bbox=(-124.48, 32.53, -114.13, 42.01),
        sensors=("VIIRS_SNPP_NRT",),
        day_range=2,
    )
    url = src._build_url("VIIRS_SNPP_NRT")
    assert url.endswith("/VIIRS_SNPP_NRT/-124.48,32.53,-114.13,42.01/2")
    assert "ABC123" in url


def test_day_range_clamped():
    src = FirmsSource(map_key="k", bbox=(0, 0, 1, 1), sensors=("MODIS_NRT",), day_range=99)
    assert src.day_range == 5  # FIRMS hard limit


def test_normalize_viirs_sample_conforms_to_contract():
    raw = pd.read_csv(SAMPLE)
    out = FirmsSource._normalize(raw, "VIIRS_SNPP_NRT")
    # Exactly the contract columns, in order.
    assert list(out.columns) == list(DETECTION_COLUMNS)
    # Confidence normalized to 0–100 with a valid class.
    assert out["confidence"].between(0, 100).all()
    assert set(out["confidence_class"]).issubset({"low", "nominal", "high"})
    # Acquisition time parsed to tz-aware UTC.
    assert str(out["acq_datetime"].dt.tz) == "UTC"
    assert out["acq_datetime"].notna().all()


def test_empty_frame_is_valid():
    empty = DetectionSource.empty()
    assert list(empty.columns)[:-1] == list(DETECTION_COLUMNS) or "geometry" in empty.columns
    assert empty.crs.to_epsg() == 4326


def test_modis_numeric_confidence_normalizes():
    raw = pd.DataFrame(
        {
            "latitude": [34.0],
            "longitude": [-118.0],
            "acq_date": ["2026-06-30"],
            "acq_time": [1200],
            "brightness": [320.0],
            "confidence": [85],  # MODIS numeric
            "frp": [42.0],
            "scan": [1.0],
            "track": [1.0],
            "satellite": ["Terra"],
            "daynight": ["D"],
        }
    )
    out = FirmsSource._normalize(raw, "MODIS_NRT")
    assert out.loc[0, "confidence_class"] == "high"
    assert out.loc[0, "brightness_k"] == 320.0
