import { useCallback, useEffect, useRef, useState } from 'react'
import MapView from './components/MapView'
import Sidebar from './components/Sidebar'
import Header from './components/Header'
import { fetchEvents, fetchDetections } from './api'

const REFRESH_MS = 5 * 60 * 1000

export default function App() {
  const [region, setRegion] = useState('california')
  const [days, setDays] = useState(3)
  const [basemap, setBasemap] = useState('Dark')
  const [airborne, setAirborne] = useState(false)
  const [events, setEvents] = useState(null)
  const [detections, setDetections] = useState(null)
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [updated, setUpdated] = useState(null)
  const timer = useRef(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const [ev, det] = await Promise.all([fetchEvents(region, days), fetchDetections(region, days)])
      setEvents(ev); setDetections(det); setUpdated(new Date())
    } catch (e) { setError(e.message || String(e)) }
    finally { setLoading(false) }
  }, [region, days])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (timer.current) clearInterval(timer.current)
    timer.current = setInterval(load, REFRESH_MS)
    return () => clearInterval(timer.current)
  }, [load])

  const mode = events?.metadata?.mode || 'sample'

  return (
    <div className="h-full w-full flex flex-col bg-[#0E1117]">
      <Header region={region} setRegion={setRegion} days={days} setDays={setDays}
        basemap={basemap} setBasemap={setBasemap} mode={mode} updated={updated}
        onRefresh={load} loading={loading} airborne={airborne} setAirborne={setAirborne} />
      <div className="flex-1 flex overflow-hidden flex-col-reverse sm:flex-row">
        <Sidebar events={events} region={region} days={days} loading={loading} error={error}
          selectedId={selected?.properties?.event_id}
          onSelect={(f) => setSelected({ ...f })} />
        <main className="flex-1 relative min-h-[50vh]">
          <MapView events={events} detections={detections} basemap={basemap}
            region={region} selected={selected} airborne={airborne} />
        </main>
      </div>
    </div>
  )
}
