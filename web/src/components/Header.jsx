import { REGIONS, BASEMAPS } from '../config'

export default function Header({ region, setRegion, days, setDays, basemap, setBasemap,
  mode, updated, onRefresh, loading }) {
  return (
    <header className="h-14 shrink-0 bg-panel2/95 backdrop-blur border-b border-[#242a35]
      flex items-center gap-3 px-4 z-10">
      <div className="hidden sm:flex items-center gap-2 mr-2">
        <span className={`h-2.5 w-2.5 rounded-full ${mode === 'live' ? 'bg-green-400' : 'bg-yellow-400'}`} />
        <span className="text-xs font-semibold text-gray-200">{mode === 'live' ? 'LIVE' : 'SAMPLE'}</span>
      </div>

      <Select label="Region" value={region} onChange={setRegion}
        options={Object.entries(REGIONS).map(([k, v]) => [k, v])} />
      <Select label="Days" value={String(days)} onChange={(v) => setDays(Number(v))}
        options={[1, 2, 3, 4, 5].map((d) => [String(d), String(d)])} />
      <Select label="Basemap" value={basemap} onChange={setBasemap}
        options={Object.keys(BASEMAPS).map((k) => [k, k])} />

      <div className="ml-auto flex items-center gap-3">
        {updated && <span className="hidden md:inline text-xs text-gray-500">
          updated {updated.toLocaleTimeString()}</span>}
        <button onClick={onRefresh} disabled={loading}
          className="text-xs font-semibold px-3 py-1.5 rounded-md bg-ember/90 hover:bg-ember text-white disabled:opacity-50">
          {loading ? 'Refreshing…' : '↻ Refresh'}
        </button>
      </div>
    </header>
  )
}

function Select({ label, value, onChange, options }) {
  return (
    <label className="flex items-center gap-1.5 text-xs text-gray-400">
      <span className="hidden sm:inline">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}
        className="bg-[#12151C] border border-[#2c3543] rounded-md px-2 py-1 text-gray-100 text-xs">
        {options.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </select>
    </label>
  )
}
