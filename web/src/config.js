export const API_BASE = import.meta.env.VITE_API_URL || 'https://fireperim-api.onrender.com'
export const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN || ''

export const RISK_COLORS = {
  Low: '#2E9E5B', Moderate: '#E0B43A', High: '#E8552B', Extreme: '#B71C1C', Unknown: '#8A8F98',
}

export const BASEMAPS = {
  Satellite: 'mapbox://styles/mapbox/satellite-streets-v12',
  Dark: 'mapbox://styles/mapbox/dark-v11',
}

export const REGIONS = {
  california: 'California / US West',
  us_west: 'US West',
  conus: 'Continental US',
  sycan: 'Sycan Marsh (demo)',
}

export const REGION_VIEW = {
  california: { center: [-119.5, 37.3], zoom: 5.2 },
  us_west: { center: [-116.5, 42.0], zoom: 4.4 },
  conus: { center: [-98.0, 39.5], zoom: 3.4 },
  sycan: { center: [-121.154, 42.8525], zoom: 13.4 },
}
