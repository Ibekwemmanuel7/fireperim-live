// Client-side fire weather + spread risk.
// Fetches Open-Meteo directly from the browser so it uses the user's IP (fresh
// quota), bypassing the shared-IP rate limit on the free backend host.
const OM = 'https://api.open-meteo.com/v1/forecast'
const CURRENT = 'temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,wind_gusts_10m'
const _cache = new Map()
const TTL = 6 * 3600 * 1000

const key = (lat, lon) => `${lat.toFixed(2)},${lon.toFixed(2)}`
const clamp = (x) => Math.max(0, Math.min(1, x))

export function spreadRisk(temp, rh, wind) {
  if (temp == null && rh == null && wind == null) return null
  const w = wind ?? 0, h = rh ?? 50, t = temp ?? 20
  const s = 100 * (0.55 * clamp(w / 15) + 0.30 * clamp((45 - h) / 45) + 0.15 * clamp((t - 15) / 25))
  return Math.round(s * 10) / 10
}

export function riskClass(s) {
  if (s == null) return 'Unknown'
  if (s >= 75) return 'Extreme'
  if (s >= 50) return 'High'
  if (s >= 25) return 'Moderate'
  return 'Low'
}

export async function fetchWeatherPoint(lat, lon) {
  const k = key(lat, lon)
  const hit = _cache.get(k)
  if (hit && Date.now() - hit.t < TTL) return hit.w
  try {
    const url = `${OM}?latitude=${lat.toFixed(4)}&longitude=${lon.toFixed(4)}` +
      `&current=${CURRENT}&wind_speed_unit=ms&timezone=UTC`
    const r = await fetch(url)
    if (!r.ok) throw new Error('open-meteo ' + r.status)
    const c = (await r.json()).current || {}
    const w = {
      temp_c: c.temperature_2m, rh_pct: c.relative_humidity_2m,
      wind_speed_ms: c.wind_speed_10m, wind_dir_deg: c.wind_direction_10m,
      wind_gust_ms: c.wind_gusts_10m,
    }
    _cache.set(k, { t: Date.now(), w })
    return w
  } catch (e) {
    return null
  }
}

// Enrich an events FeatureCollection with weather + risk, in the browser.
export async function enrichEventsWithWeather(events) {
  if (!events || !events.features) return events
  const features = await Promise.all(events.features.map(async (f) => {
    const p = f.properties || {}
    if (p.centroid_lat == null || p.centroid_lon == null) return f
    const w = await fetchWeatherPoint(Number(p.centroid_lat), Number(p.centroid_lon))
    if (!w) return f
    const score = spreadRisk(w.temp_c, w.rh_pct, w.wind_speed_ms)
    return { ...f, properties: { ...p, ...w, risk_score: score, risk_class: riskClass(score) } }
  }))
  return { ...events, features }
}
