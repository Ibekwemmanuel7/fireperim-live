import { REGIONS, BASEMAPS } from '../config'

export default function Header({ region, setRegion, days, setDays, basemap, setBasemap,
  mode, updated, onRefresh, loading, airborne, setAirborne, ortho, setOrtho,
  multipass, setMultipass }) {
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

      <button onClick={() => setAirborne(!airborne)}
        title="Overlay a simulated airborne IR scanner frame (raster → COG → perimeter)"
        className={`text-xs font-semibold px-3 py-1.5 rounded-md border transition ${
          airborne ? 'bg-cyan-500/20 border-cyan-400 text-cyan-200'
                   : 'bg-[#12151C] border-[#2c3543] text-gray-300 hover:border-[#3a4453]'}`}>
        {airborne ? '● Airborne IR' : '○ Airborne IR'}
      </button>

      <button onClick={() => setOrtho(!ortho)}
        title="Overlay an orthorectified (direct-georeferencing) frame — oblique corrected to north-up"
        className={`text-xs font-semibold px-3 py-1.5 rounded-md border transition ${
          ortho ? 'bg-emerald-500/20 border-emerald-400 text-emerald-200'
                : 'bg-[#12151C] border-[#2c3543] text-gray-300 hover:border-[#3a4453]'}`}>
        {ortho ? '● Ortho' : '○ Ortho'}
      </button>

      <button onClick={() => setMultipass(!multipass)}
        title="Fuse multiple noisy scanner passes into one clean image (destripe → register → time-aware stack). +10 dB PSNR, −48% noise, gaps filled"
        className={`text-xs font-semibold px-3 py-1.5 rounded-md border transition ${
          multipass ? 'bg-amber-500/20 border-amber-400 text-amber-200'
                    : 'bg-[#12151C] border-[#2c3543] text-gray-300 hover:border-[#3a4453]'}`}>
        {multipass ? '● Multi-pass fusion' : '○ Multi-pass fusion'}
      </button>

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
