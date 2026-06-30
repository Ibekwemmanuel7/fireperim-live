# FirePerim Live — 2-Minute Demo Script

**Live URL:** https://fireperim-live.streamlit.app
**Repo:** https://github.com/Ibekwemmanuel7/fireperim-live

> Goal: in ~2 minutes, land one idea — *"I built ORBIT's downstream architecture
> against satellite data; swap the ingestion layer and you have ORBIT."*

---

## Before you start (the morning of)

- Open the live URL once to warm it up (first load wakes the app + fetches weather).
- Have the **GitHub repo** open in a second tab.
- If fire activity is low, set the **Look-back window to 5 days**, or flip
  **Use cached sample** so perimeters are guaranteed on screen.
- Optional: download the **KMZ** ahead of time and have Google Earth open.

---

## The walkthrough (≈2 min)

**0:00 — The one-liner.**
> "This is FirePerim Live. ORBIT ingests thermal imagery from airborne IR
> scanners and turns it into agency-ready fire perimeters. I built that same
> pipeline — clustering, perimeters, weather, risk, export — using free NASA
> satellite thermal data. The ingestion layer is the only thing you'd swap."

**0:20 — Live ingestion.**
Point at the 🟢 LIVE badge and the detection points.
> "These are live VIIRS active-fire detections from NASA FIRMS, pulled through a
> client that normalizes VIIRS and MODIS into one standardized schema."

**0:40 — Events + perimeters.**
Point at the colored polygons and labels.
> "DBSCAN clusters raw detections into distinct fire events, then alpha shapes
> trace a perimeter around each. I cluster in a projected CRS so the radius is a
> real ground distance, not degrees."

Open the **⚙️ Clustering & perimeters** expander; nudge a slider.
> "Sensitivity is tunable — on a quiet day the pipeline correctly reports zero
> events instead of inventing fires."

**1:05 — Weather + risk.**
Point at the blue arrows and risk colors; click a perimeter popup.
> "Each event is enriched with live wind, humidity, and temperature from
> Open-Meteo, and scored for spread risk — wind-dominant, dry and hot amplify.
> Perimeters are colored by risk; arrows show where the wind would push the fire."

**1:30 — Agency export.**
Scroll to **Agency-ready export**; click **KMZ** (open in Google Earth if ready).
> "Same as ORBIT's last step — georeferenced outputs for agency GIS. GeoJSON for
> ArcGIS/QGIS/web, KMZ for Google Earth and field tools. Perimeters carry their
> stats, weather, and risk as properties."

**1:50 — The close.**
Switch to the GitHub tab.
> "It's tested, in CI, and deployed on a public URL. The architecture is built
> around one seam — replace the FIRMS client with an airborne IR feed emitting
> the same schema, and the rest of the pipeline is unchanged. That's the bridge
> from this to ORBIT."

---

## If asked: likely questions

- **"How is risk computed?"** — Transparent weighted score (wind 55%, dryness
  30%, heat 15%), normalized 0–100, binned Low/Moderate/High/Extreme. An
  operational triage signal, not a calibrated fire-danger index — and easy to
  recalibrate.
- **"Why DBSCAN?"** — Density-based, no preset cluster count, and it labels
  scatter as noise — exactly right when you don't know how many fires there are.
- **"Why alpha shapes over convex hull?"** — Concave hull hugs the real
  footprint; convex hull over-claims unburned area. Fallbacks: convex hull, then
  point-buffer for tiny clusters.
- **"How would this scale / move to ORBIT?"** — Swap the ingestion layer for the
  airborne feed; push perimeter/COG generation into cloud workers; serve tiles +
  vectors to a Mapbox GL / Leaflet operator UI. The processing core is reusable.
- **"What are the limits?"** — VIIRS is 375 m and a few passes/day; an airborne
  scanner is higher-res and continuous. Risk model is heuristic. No persistence
  yet (no perimeter-growth history).

---

## Fallbacks if something breaks

- App slow / won't load → it may be asleep; reload and wait ~20s.
- Live data empty → widen look-back, switch region to Continental US, or toggle
  the cached sample.
- Weather/risk blank → Open-Meteo hiccup; perimeters still render. Reload.
