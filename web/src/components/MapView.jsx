import { useEffect, useRef } from 'react'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { MAPBOX_TOKEN, BASEMAPS, REGION_VIEW } from '../config'

mapboxgl.accessToken = MAPBOX_TOKEN

// Downwind spread-direction points built from event centroids.
function centroidsFC(events) {
  return {
    type: 'FeatureCollection',
    features: (events?.features || [])
      .filter((f) => f.properties && f.properties.wind_dir_deg != null)
      .map((f) => ({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [f.properties.centroid_lon, f.properties.centroid_lat] },
        properties: {
          bearing: (Number(f.properties.wind_dir_deg) + 180) % 360,
          wind: Number(f.properties.wind_speed_ms) || 0,
        },
      })),
  }
}

const RISK_FILL = ['interpolate', ['linear'], ['coalesce', ['get', 'risk_score'], 0],
  0, '#2E9E5B', 25, '#E0B43A', 50, '#E8552B', 75, '#B71C1C']
const FRP_COLOR = ['interpolate', ['linear'], ['coalesce', ['get', 'frp_mw'], 0],
  0, '#FFE08A', 20, '#FF7A33', 100, '#B71C1C']
const FRP_RADIUS = ['interpolate', ['linear'], ['coalesce', ['get', 'frp_mw'], 0],
  0, 3, 50, 8, 200, 14]

function popupHTML(p) {
  const f = (v, d = '—') => (v == null || Number.isNaN(v)) ? d : v
  const n = (v) => (v == null || Number.isNaN(Number(v))) ? '—' : Number(v).toFixed(1)
  return `<div style="font-size:12px;line-height:1.5;min-width:200px">
    <div style="font-weight:700;font-size:14px;margin-bottom:4px">🔥 ${f(p.label, 'Fire event')}</div>
    <div><b>Spread risk:</b> ${f(p.risk_class)} (${n(p.risk_score)})</div>
    <div><b>Area:</b> ${n(p.area_ha)} ha &nbsp; <b>Perimeter:</b> ${n(p.perimeter_km)} km</div>
    <div><b>Detections:</b> ${f(p.n_detections)} &nbsp; <b>Total FRP:</b> ${n(p.total_frp_mw)} MW</div>
    <div><b>Wind:</b> ${n(p.wind_speed_ms)} m/s @ ${n(p.wind_dir_deg)}° </div>
    <div><b>RH:</b> ${n(p.rh_pct)}% &nbsp; <b>Temp:</b> ${n(p.temp_c)}°C</div>
  </div>`
}

export default function MapView({ events, detections, basemap, region, selected }) {
  const ref = useRef(null)
  const map = useRef(null)
  const popup = useRef(null)

  function addLayers() {
    const m = map.current
    if (!m || m.getSource('events')) return
    m.addSource('events', { type: 'geojson', data: events || empty() })
    m.addSource('detections', { type: 'geojson', data: detections || empty() })
    m.addSource('winds', { type: 'geojson', data: centroidsFC(events) })

    m.addLayer({ id: 'events-fill', type: 'fill', source: 'events',
      paint: { 'fill-color': RISK_FILL, 'fill-opacity': 0.35 } })
    m.addLayer({ id: 'events-line', type: 'line', source: 'events',
      paint: { 'line-color': RISK_FILL, 'line-width': 2 } })
    m.addLayer({ id: 'detections-pt', type: 'circle', source: 'detections',
      paint: { 'circle-radius': FRP_RADIUS, 'circle-color': FRP_COLOR,
        'circle-opacity': 0.85, 'circle-stroke-color': '#00000055', 'circle-stroke-width': 0.5 } })
    m.addLayer({ id: 'wind-arrows', type: 'symbol', source: 'winds',
      layout: { 'text-field': '↑', 'text-rotate': ['get', 'bearing'], 'text-allow-overlap': true,
        'text-size': ['interpolate', ['linear'], ['get', 'wind'], 0, 16, 15, 30] },
      paint: { 'text-color': '#4FC3F7', 'text-halo-color': '#000', 'text-halo-width': 1.2 } })

    m.on('click', 'events-fill', (e) => {
      const f = e.features[0]
      if (popup.current) popup.current.remove()
      popup.current = new mapboxgl.Popup({ closeButton: true })
        .setLngLat(e.lngLat).setHTML(popupHTML(f.properties)).addTo(m)
    })
    m.on('mouseenter', 'events-fill', () => { m.getCanvas().style.cursor = 'pointer' })
    m.on('mouseleave', 'events-fill', () => { m.getCanvas().style.cursor = '' })
  }

  // init map once
  useEffect(() => {
    if (map.current || !MAPBOX_TOKEN) return
    const v = REGION_VIEW[region] || REGION_VIEW.california
    map.current = new mapboxgl.Map({
      container: ref.current, style: BASEMAPS[basemap] || BASEMAPS.Dark,
      center: v.center, zoom: v.zoom, attributionControl: true,
    })
    map.current.addControl(new mapboxgl.NavigationControl(), 'bottom-right')
    map.current.on('load', addLayers)
  }, [])

  // basemap switch: setStyle then re-add layers
  useEffect(() => {
    const m = map.current
    if (!m) return
    m.setStyle(BASEMAPS[basemap] || BASEMAPS.Dark)
    m.once('style.load', addLayers)
  }, [basemap])

  // update data
  useEffect(() => {
    const m = map.current
    if (!m || !m.getSource('events')) return
    m.getSource('events').setData(events || empty())
    m.getSource('winds').setData(centroidsFC(events))
  }, [events])

  useEffect(() => {
    const m = map.current
    if (!m || !m.getSource('detections')) return
    m.getSource('detections').setData(detections || empty())
  }, [detections])

  // fly to region
  useEffect(() => {
    const m = map.current, v = REGION_VIEW[region]
    if (m && v) m.flyTo({ center: v.center, zoom: v.zoom })
  }, [region])

  // fly to selected event + open popup
  useEffect(() => {
    const m = map.current
    if (!m || !selected) return
    const p = selected.properties
    m.flyTo({ center: [p.centroid_lon, p.centroid_lat], zoom: 9 })
    if (popup.current) popup.current.remove()
    popup.current = new mapboxgl.Popup({ closeButton: true })
      .setLngLat([p.centroid_lon, p.centroid_lat]).setHTML(popupHTML(p)).addTo(m)
  }, [selected])

  if (!MAPBOX_TOKEN) {
    return <div className="h-full w-full flex items-center justify-center text-center text-gray-300 p-8">
      <div>
        <div className="text-2xl mb-2">🗺️ Mapbox token missing</div>
        <div className="text-sm text-gray-400">Set <code>VITE_MAPBOX_TOKEN</code> in your environment
          (Vercel → Settings → Environment Variables) and redeploy.</div>
      </div>
    </div>
  }
  return <div ref={ref} className="h-full w-full" />
}

const empty = () => ({ type: 'FeatureCollection', features: [] })
