import { API_BASE } from './config'

async function getJSON(path) {
  const r = await fetch(`${API_BASE}${path}`)
  if (!r.ok) throw new Error(`${path} → HTTP ${r.status}`)
  return r.json()
}

export const fetchEvents = (region = 'california', days = 3) =>
  getJSON(`/api/events?region=${region}&days=${days}`)

export const fetchDetections = (region = 'california', days = 3) =>
  getJSON(`/api/detections?region=${region}&days=${days}`)

export const fetchHealth = () => getJSON('/api/health')

export const exportUrl = (fmt, region = 'california', days = 3) =>
  `${API_BASE}/api/export/${fmt}?region=${region}&days=${days}`
