# FirePerim Live — API (FastAPI)

REST wrapper around the FirePerim pipeline. Serves GeoJSON / KMZ to the React +
Mapbox front end (`/web`). The processing modules in `../src/fireperim` are
unchanged — this layer only orchestrates and serializes.

## Endpoints

| Method | Path | Returns |
|--------|------|---------|
| GET | `/api/health` | Service status + whether live data is configured |
| GET | `/api/events` | Fire events as GeoJSON (perimeters + weather + risk) |
| GET | `/api/detections` | Raw VIIRS detections as GeoJSON points |
| GET | `/api/export/geojson` | Events GeoJSON as a file download |
| GET | `/api/export/kmz` | Events KMZ as a file download |
| GET | `/docs` | Interactive OpenAPI docs |

**Query params** (events/detections): `region` (california\|us_west\|conus),
`days` (1–5), `sensors` (comma list), `sample` (true\|false).

## Run locally

```bash
pip install -r api/requirements.txt
# optional: live data
export FIRMS_MAP_KEY=your_key          # PowerShell: $env:FIRMS_MAP_KEY="your_key"
uvicorn api.main:app --reload --port 8000
# -> http://localhost:8000/api/health   and   /docs
```

No key → the API serves the cached VIIRS sample automatically.

## Test

```bash
pip install httpx
pytest api/test_api.py -q
```

## Deploy to Render (free tier)

The repo includes `render.yaml` (a Blueprint). Two ways:

**Blueprint (recommended):** Render dashboard → **New → Blueprint** → pick this
repo. It reads `render.yaml`. Then set env vars when prompted:
- `FIRMS_MAP_KEY` = your NASA FIRMS key (omit to run in sample mode)
- `CORS_ORIGINS` = your Vercel URL (e.g. `https://fireperim.vercel.app`) or `*`

**Manual:** New → Web Service → this repo →
- Build: `pip install -r api/requirements.txt`
- Start: `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
- Health check path: `/api/health`

First request after idle may take ~30–50s (free tier cold start). Responses are
cached for 5 minutes.
