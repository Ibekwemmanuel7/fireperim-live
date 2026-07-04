import { RISK_COLORS } from '../config'
import { exportUrl } from '../api'

function Badge({ cls }) {
  const c = RISK_COLORS[cls] || RISK_COLORS.Unknown
  return <span className="text-xs font-bold px-2 py-0.5 rounded-full"
    style={{ background: c + '33', color: c, border: `1px solid ${c}` }}>{cls || '—'}</span>
}

export default function Sidebar({ events, region, days, onSelect, selectedId, loading, error }) {
  const feats = (events?.features || []).slice().sort(
    (a, b) => (b.properties.risk_score ?? -1) - (a.properties.risk_score ?? -1)
  )
  const meta = events?.metadata

  return (
    <aside className="w-full sm:w-80 shrink-0 bg-panel border-r border-[#242a35] flex flex-col h-full">
      <div className="p-4 border-b border-[#242a35]">
        <div className="flex items-center gap-2">
          <span className="text-xl">🔥</span>
          <h1 className="text-lg font-bold text-white">FirePerim Live</h1>
        </div>
        <p className="text-xs text-gray-400 mt-1">Operator console · satellite fire perimeters</p>
      </div>

      <div className="p-3 flex gap-2">
        <a href={exportUrl('geojson', region, days)}
          className="flex-1 text-center text-xs font-semibold py-2 rounded-md bg-[#1E2430] hover:bg-[#28303d] text-gray-100 border border-[#2c3543]">
          ↓ GeoJSON</a>
        <a href={exportUrl('kmz', region, days)}
          className="flex-1 text-center text-xs font-semibold py-2 rounded-md bg-[#1E2430] hover:bg-[#28303d] text-gray-100 border border-[#2c3543]">
          ↓ KMZ</a>
      </div>

      <div className="px-4 pb-2 flex items-center justify-between">
        <span className="text-xs uppercase tracking-wide text-gray-500">
          {feats.length} events {meta ? `· ${meta.mode}` : ''}
        </span>
      </div>

      <div className="flex-1 overflow-y-auto px-3 pb-4 space-y-2">
        {loading && <div className="text-gray-400 text-sm p-3">Loading live data…</div>}
        {error && <div className="text-red-300 text-sm p-3 bg-red-900/20 rounded-md">
          {String(error)}<br /><span className="text-gray-400">The API may be waking up (free tier); retry in ~30s.</span>
        </div>}
        {!loading && !error && feats.length === 0 &&
          <div className="text-gray-400 text-sm p-3">No fire events in this region/window.</div>}
        {feats.map((f) => {
          const p = f.properties
          const c = RISK_COLORS[p.risk_class] || RISK_COLORS.Unknown
          const active = selectedId === p.event_id
          return (
            <button key={p.event_id} onClick={() => onSelect(f)}
              className={`w-full text-left rounded-lg p-3 border transition ${active ? 'bg-[#232b38] border-ember' : 'bg-panel2 border-[#242a35] hover:border-[#3a4453]'}`}
              style={{ borderLeft: `4px solid ${c}` }}>
              <div className="flex items-center justify-between">
                <span className="font-semibold text-sm text-white">{p.label || `Event ${p.event_id}`}</span>
                <Badge cls={p.risk_class} />
              </div>
              <div className="mt-1 grid grid-cols-2 gap-x-2 text-xs text-gray-400">
                <span>Area: {fmt(p.area_ha)} ha</span>
                <span>Wind: {fmt(p.wind_speed_ms)} m/s</span>
                <span>FRP: {fmt(p.total_frp_mw)} MW</span>
                <span>RH: {fmt(p.rh_pct)}%</span>
              </div>
            </button>
          )
        })}
      </div>
    </aside>
  )
}

const fmt = (v) => (v == null || Number.isNaN(Number(v))) ? '—' : Number(v).toFixed(1)
