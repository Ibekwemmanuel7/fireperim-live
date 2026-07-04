# FirePerim Live — Web (React + Mapbox GL JS)

Operator console for the FirePerim Live API. Full-screen Mapbox map with
risk-colored fire perimeters, VIIRS detection points, wind arrows, a risk-sorted
event sidebar, and GeoJSON/KMZ export.

## Stack
Vite · React 18 · Mapbox GL JS · Tailwind CSS. Talks to the FastAPI backend
(`/api`, deployed on Render).

## Local dev
```bash
cd web
npm install
cp .env.example .env      # set VITE_API_URL and VITE_MAPBOX_TOKEN
npm run dev               # http://localhost:5173
```

## Environment variables
| Var | Purpose |
|-----|---------|
| `VITE_API_URL` | FastAPI base URL, e.g. `https://fireperim-api.onrender.com` |
| `VITE_MAPBOX_TOKEN` | Mapbox public token (`pk.…`) from account.mapbox.com |

Defaults: if `VITE_API_URL` is unset it falls back to the Render URL. The map
shows a "token missing" message until `VITE_MAPBOX_TOKEN` is set.

## Deploy to Vercel
1. vercel.com → **Add New → Project** → import `fireperim-live`.
2. **Root Directory:** `web`. Framework preset: **Vite** (auto-detected).
3. **Environment Variables:** add `VITE_API_URL` and `VITE_MAPBOX_TOKEN`.
4. **Deploy.** Build: `npm run build`, output: `dist`.

After deploy, set the backend's `CORS_ORIGINS` (Render env) to your Vercel URL.

## Features
- Basemap toggle (satellite / dark)
- Perimeter fill + outline colored by spread-risk score
- Detection points sized/colored by FRP
- Downwind spread-direction arrows per event
- Click a perimeter → stats popup; click a sidebar card → fly to + popup
- Region + look-back selectors; auto-refresh every 5 minutes
- GeoJSON / KMZ download buttons (call the API export endpoints)
- Responsive (sidebar stacks under the map on narrow screens)
