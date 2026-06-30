# 🔥 FirePerim Live

**A satellite-data analog of the ORBIT Data Engine.**

ORBIT (EmberWorks / Coulson Aviation) ingests thermal imagery from airborne IR
scanners on firefighting aircraft, extracts fire perimeters, and publishes
georeferenced outputs to agency GIS systems (ICS, CAL FIRE, NIFC). **FirePerim
Live implements the same downstream architecture** — cluster → perimeter →
weather → risk → agency export — fed by free satellite thermal detections
(NASA VIIRS/FIRMS) instead of an airborne scanner.

> The pitch: *"ORBIT ingests from airborne IR scanners. I built the same
> architecture using satellite thermal data. Swap the ingestion layer and you
> have ORBIT."*

The architecture is deliberately built around that swap. Every detection source
emits one **standardized schema** (`src/fireperim/ingest/base.py`), so nothing
downstream knows or cares whether the heat came from a satellite or an aircraft.

---

## Pipeline

| Stage | Module | Status |
|-------|--------|--------|
| 1. Ingest — VIIRS/FIRMS active fire | `ingest/firms.py` | ✅ Day 1 |
| 2. Cluster detections into events (DBSCAN) | `processing/cluster.py` | ✅ Day 2 |
| 3. Extract perimeters (alpha shapes) | `processing/perimeter.py` | ✅ Day 2 |
| 4. Fire weather (Open-Meteo) | `weather/open_meteo.py` | ⏳ Day 3 |
| 5. Spread-risk score | `processing/risk.py` | ⏳ Day 3 |
| 6. Export GeoJSON + KMZ | `export/` | ⏳ Day 4 |
| 7. Interactive map (Folium/Leaflet) | `viz/maps.py` | ✅ Day 1 |

---

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Add your free FIRMS key (request at https://firms.modaps.eosdis.nasa.gov/api/area/)
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
#   -> edit FIRMS_MAP_KEY

streamlit run app.py
```

No key yet? The app runs against a cached VIIRS sample — toggle **Use cached
sample** in the sidebar. Everything downstream behaves identically.

---

## Deploy to Streamlit Cloud

1. Push this repo to GitHub.
2. On [share.streamlit.io](https://share.streamlit.io), point a new app at
   `app.py`.
3. In **App → Settings → Secrets**, paste:
   ```toml
   FIRMS_MAP_KEY = "your_key"
   ```
4. Share the public URL during the interview.

---

## Project layout

```
app.py                     Streamlit entrypoint (Day 1: ingest + map)
src/fireperim/
  config.py                Regions, sensors, processing params
  ingest/
    base.py                DetectionSource ABC + standardized schema  <- the swap seam
    firms.py               NASA FIRMS / VIIRS client
  processing/              DBSCAN, alpha shapes, risk (Days 2–3)
  weather/                 Open-Meteo enrichment (Day 3)
  export/                  GeoJSON / KMZ (Day 4)
  viz/maps.py              Folium map builder
data/sample/               Cached VIIRS snapshot for offline demo
scripts/fetch_sample.py    Refresh the sample from live FIRMS
tests/                     Ingestion-contract tests
.github/workflows/ci.yml   Lint + test on every push
```

## Data sources

- **NASA FIRMS** active fire data — VIIRS (375 m) S-NPP / NOAA-20 / NOAA-21,
  MODIS (1 km). Near Real-Time. Free MAP_KEY, 5000 transactions / 10 min.
- **Open-Meteo** fire weather (Day 3) — no key required.

## Tech

Python · GeoPandas · Shapely · scikit-learn (DBSCAN) · alphashape ·
Streamlit · Folium/Leaflet · GitHub Actions. Raster libs (Rasterio, xarray)
are scaffolded for the imagery/COG extension that mirrors ORBIT's raw IR input.
