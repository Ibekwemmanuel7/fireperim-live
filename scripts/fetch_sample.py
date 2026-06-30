"""Refresh the cached sample with a real FIRMS pull.

Usage:
    FIRMS_MAP_KEY=xxxx python scripts/fetch_sample.py

Writes data/sample/viirs_california_sample.csv from live VIIRS data so the
offline demo reflects current fire activity. Requires a valid MAP_KEY.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import requests

from fireperim.config import FIRMS_API_BASE, REGIONS

OUT = Path(__file__).parents[1] / "data" / "sample" / "viirs_california_sample.csv"


def main() -> int:
    key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    if not key:
        print("Set FIRMS_MAP_KEY in the environment first.", file=sys.stderr)
        return 1
    w, s, e, n = REGIONS["california"].bbox
    url = f"{FIRMS_API_BASE}/{key}/VIIRS_SNPP_NRT/{w},{s},{e},{n}/2"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    if "latitude" not in r.text:
        print("Unexpected response:\n" + r.text[:400], file=sys.stderr)
        return 2
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(r.text)
    print(f"Wrote {OUT} ({len(r.text.splitlines()) - 1} detections)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
