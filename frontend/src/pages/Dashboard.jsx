import { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'

const FRESHNESS_OPTIONS = [
  { value: 24, label: '24 hours' },
  { value: 48, label: '48 hours' },
  { value: 72, label: '3 days' },
  { value: 168, label: '1 week' },
]

const SOURCES = [
  { key: 'jsearch',  label: 'JSearch' },
  { key: 'adzuna',  label: 'Adzuna' },
  { key: 'simplify', label: 'Simplify' },
  { key: 'ats',      label: 'ATS Companies' },
  { key: 'sponsors', label: 'H-1B Sponsors' },
]

const ALL_KEYS = SOURCES.map(s => s.key)

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [freshness, setFreshness] = useState(24)
  const [selected, setSelected] = useState(new Set(ALL_KEYS))
  const [sourceStatuses, setSourceStatuses] = useState({})
  const pollRef = useRef(null)

  const load = () => api.getDashboard().then(setData).finally(() => setLoading(false))

  useEffect(() => { load() }, [])

  const anyRunning = Object.values(sourceStatuses).some(s => s.running)

  const startPolling = () => {
    if (pollRef.current) return
    pollRef.current = setInterval(async () => {
      try {
        const s = await api.getSourcesStatus()
        setSourceStatuses(s)
        if (!Object.values(s).some(v => v.running)) {
          clearInterval(pollRef.current)
          pollRef.current = null
          load()
        }
      } catch (_) { /* transient */ }
    }, 2000)
  }

  // Restore in-progress after refresh
  useEffect(() => {
    api.getSourcesStatus().then(s => {
      setSourceStatuses(s)
      if (Object.values(s).some(v => v.running)) startPolling()
    }).catch(() => {})
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  const toggleSource = (key) => {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  const runDiscovery = async () => {
    if (!selected.size) return
    const params = { freshness_hours: freshness }
    const toRun = [...selected]
    await Promise.allSettled(toRun.map(src => api.triggerSourceDiscovery(src, params)))
    const fresh = await api.getSourcesStatus()
    setSourceStatuses(fresh)
    startPolling()
  }

  if (loading) return <p className="text-text-muted animate-pulse">Loading dashboard...</p>
  if (!data) return <p className="text-danger">Failed to load dashboard</p>

  const { job_stats, app_stats, due_reminders, discovery, coverage } = data

  return (
    <div className="space-y-6">
      {due_reminders.length > 0 && (
        <div className="bg-accent-muted border border-accent/20 rounded-xl p-5">
          <h2 className="text-accent font-semibold mb-3">Follow-ups Due</h2>
          <div className="space-y-1">
            {due_reminders.map(r => (
              <div key={r.id} className="flex justify-between items-center py-1.5">
                <div>
                  <span className="text-text-primary text-sm">{r.title} {(r.job_company || r.app_company) && <span className="text-text-tertiary">- {r.job_company || r.app_company}</span>}</span>
                  {r.job_id && <Link to={`/jobs?select=${r.job_id}`} className="text-xs text-accent hover:underline ml-2">View Job</Link>}
                </div>
                <span className="text-accent text-sm font-medium shrink-0 ml-3">{new Date(r.due_date).toLocaleDateString()}</span>
              </div>
            ))}
          </div>
          <Link to="/reminders" className="text-accent text-sm hover:underline mt-3 inline-block">View all reminders</Link>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Pending Jobs" value={job_stats.pending || 0} />
        <StatCard label="Applied" value={(app_stats.applied || 0) + (job_stats.applied || 0)} />
        <StatCard label="Interviews" value={app_stats.interview || 0} />
        <StatCard label="This Week" value={app_stats.this_week || 0} />
      </div>

      {coverage && (
        <div className="bg-surface-raised border border-border rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-text-primary font-semibold">Search Coverage</h3>
            <Link to="/sponsors" className="text-accent text-sm hover:underline">Manage sponsors</Link>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
            <StatCard label="Company boards" value={coverage.total_boards} />
            <StatCard label="ATS platforms" value={coverage.platforms} />
            <StatCard label="Curated companies" value={coverage.curated_companies} />
            <StatCard label="Sponsor boards" value={coverage.sponsor_boards} />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
            <div>
              <div className="text-text-tertiary text-xs uppercase tracking-wide mb-2">Curated by ATS</div>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(coverage.curated_by_ats).map(([ats, n]) => (
                  <span key={ats} className="px-2 py-0.5 rounded-md bg-surface-overlay border border-border text-text-secondary text-xs">
                    {ats} <span className="text-text-primary font-medium">{n}</span>
                  </span>
                ))}
              </div>
            </div>
            <div>
              <div className="text-text-tertiary text-xs uppercase tracking-wide mb-2">Sponsor boards by ATS</div>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(coverage.sponsor_by_ats).map(([ats, n]) => (
                  <span key={ats} className="px-2 py-0.5 rounded-md bg-emerald-900/15 border border-emerald-500/20 text-emerald-300 text-xs">
                    {ats} <span className="font-medium">{n}</span>
                  </span>
                ))}
              </div>
            </div>
          </div>
          <div className="text-xs text-text-muted mt-4 pt-3 border-t border-border/50">
            H-1B sponsor probe: {coverage.sponsor_probe.resolved} boards found from {coverage.sponsor_probe.checked} checked
            {' '}({coverage.sponsor_probe.with_h1b} sponsors with H-1B history in dataset)
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-surface-raised border border-border rounded-xl p-5">
          <h3 className="text-text-primary font-semibold mb-4">Job Queue</h3>
          <div className="space-y-2 text-sm">
            {Object.entries(job_stats).map(([status, count]) => (
              <div key={status} className="flex justify-between items-center">
                <span className="text-text-tertiary capitalize">{status}</span>
                <span className="text-text-primary font-medium">{count}</span>
              </div>
            ))}
          </div>
          <Link to="/jobs" className="text-accent text-sm hover:underline mt-4 inline-block">View queue</Link>
        </div>

        <div className="bg-surface-raised border border-border rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-text-primary font-semibold">Discovery</h3>
            <div className="flex items-center gap-2">
              <span className="text-sm text-text-tertiary">Freshness:</span>
              <select
                value={freshness}
                onChange={e => setFreshness(Number(e.target.value))}
                className="bg-surface border border-border rounded-lg text-sm text-text-primary px-2.5 py-1.5 outline-none cursor-pointer"
              >
                {FRESHNESS_OPTIONS.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="space-y-2 mb-4">
            {SOURCES.map(({ key, label }) => {
              const st = sourceStatuses[key] || {}
              const isRunning = !!st.running
              return (
                <label key={key} className="flex items-center gap-3 cursor-pointer group">
                  <input
                    type="checkbox"
                    checked={selected.has(key)}
                    onChange={() => toggleSource(key)}
                    disabled={isRunning}
                    className="accent-accent w-4 h-4 cursor-pointer"
                  />
                  <span className="text-sm text-text-secondary group-hover:text-text-primary transition-colors select-none flex-1">{label}</span>
                  {isRunning
                    ? <span className="text-xs text-accent animate-pulse">{st.phase || 'Running...'}</span>
                    : st.last_run
                      ? <span className="text-xs text-text-muted">{st.new_jobs ?? 0} new · {new Date(st.last_run).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                      : <span className="text-xs text-text-muted">never run</span>
                  }
                </label>
              )
            })}
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={runDiscovery}
              disabled={anyRunning || !selected.size}
              className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-medium text-sm px-4 py-2 rounded-lg transition-all duration-150"
            >
              {anyRunning ? 'Running...' : `Run${selected.size < ALL_KEYS.length ? ` (${selected.size})` : ' All'}`}
            </button>
            <button
              onClick={() => setSelected(new Set(ALL_KEYS))}
              className="text-xs text-text-muted hover:text-text-tertiary transition-colors"
            >
              All
            </button>
            <button
              onClick={() => setSelected(new Set())}
              className="text-xs text-text-muted hover:text-text-tertiary transition-colors"
            >
              None
            </button>
          </div>
        </div>
      </div>

      <div className="bg-surface-raised border border-border rounded-xl p-5">
        <h3 className="text-text-primary font-semibold mb-4">Applications by Status</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          {Object.entries(app_stats).filter(([k]) => k !== 'this_week').map(([status, count]) => (
            <div key={status} className="flex justify-between items-center bg-surface rounded-lg p-3 border border-border">
              <span className="text-text-tertiary capitalize">{status}</span>
              <span className="text-text-primary font-medium">{count}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function StatCard({ label, value }) {
  return (
    <div className="bg-surface-raised border border-border rounded-xl p-5 text-center">
      <div className="text-3xl font-bold text-text-primary">{value}</div>
      <div className="text-text-tertiary text-sm mt-1">{label}</div>
    </div>
  )
}
