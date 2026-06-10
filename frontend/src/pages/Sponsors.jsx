import { useState, useEffect } from 'react'
import { api } from '../api'

const PAGE_SIZE = 25

const fmtMoney = (n) => n ? `$${Math.round(n / 1000)}K` : '—'

export default function Sponsors() {
  const [data, setData] = useState({ sponsors: [], total: 0 })
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [searchDebounced, setSearchDebounced] = useState('')
  const [engOnly, setEngOnly] = useState(true)
  const [minApprovals, setMinApprovals] = useState('')
  const [minRate, setMinRate] = useState('')
  const [sort, setSort] = useState('approvals')
  const [page, setPage] = useState(0)
  const [expanded, setExpanded] = useState(null)

  useEffect(() => {
    const t = setTimeout(() => { setSearchDebounced(search); setPage(0) }, 300)
    return () => clearTimeout(t)
  }, [search])

  useEffect(() => {
    setLoading(true)
    const params = { sort, limit: PAGE_SIZE, offset: page * PAGE_SIZE }
    if (searchDebounced.trim()) params.search = searchDebounced.trim()
    if (engOnly) params.eng_only = true
    if (minApprovals) params.min_approvals = minApprovals
    if (minRate) params.min_rate = minRate
    api.getSponsors(params).then(setData).finally(() => setLoading(false))
  }, [searchDebounced, engOnly, minApprovals, minRate, sort, page])

  const totalPages = Math.ceil(data.total / PAGE_SIZE)

  const linkedinPeopleUrl = (name) => {
    const clean = name.replace(/\b(INC|CORP|LLC|LTD|CO|CORPORATION|INCORPORATED)\b\.?/gi, '').trim()
    return `https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(`"${clean}" recruiter OR "talent acquisition"`)}`
  }
  const jobsSearchUrl = (name) => {
    const clean = name.replace(/\b(INC|CORP|LLC|LTD|CO|CORPORATION|INCORPORATED)\b\.?/gi, '').trim()
    return `https://www.google.com/search?q=${encodeURIComponent(`${clean} careers software engineer`)}`
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-xl font-semibold text-text-primary">H-1B Sponsors</h1>
          <p className="text-text-tertiary text-xs mt-0.5">Companies with proven H-1B sponsorship history (80-Days-to-Stay dataset) — target these for outreach</p>
        </div>
        <span className="text-xs text-text-muted">{data.total} sponsors</span>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 items-center">
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search company, role, city..."
          className="bg-surface-raised border border-border rounded-lg px-3 py-1.5 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-accent/40 transition-all w-64"
        />
        <button
          onClick={() => { setEngOnly(!engOnly); setPage(0) }}
          className={`text-xs px-2.5 py-1.5 rounded-lg border transition-all btn-press ${
            engOnly ? 'bg-accent/15 text-accent border-accent/30' : 'bg-surface-raised text-text-tertiary border-border hover:text-text-secondary'
          }`}
        >
          Eng roles only
        </button>
        <select value={minApprovals} onChange={e => { setMinApprovals(e.target.value); setPage(0) }}
          className="text-xs bg-surface-raised border border-border rounded-lg px-2 py-1.5 text-text-secondary outline-none cursor-pointer">
          <option value="">Any approvals</option>
          <option value="5">5+ approvals</option>
          <option value="20">20+ approvals</option>
          <option value="100">100+ approvals</option>
          <option value="500">500+ approvals</option>
        </select>
        <select value={minRate} onChange={e => { setMinRate(e.target.value); setPage(0) }}
          className="text-xs bg-surface-raised border border-border rounded-lg px-2 py-1.5 text-text-secondary outline-none cursor-pointer">
          <option value="">Any rate</option>
          <option value="90">90%+ approval</option>
          <option value="95">95%+ approval</option>
          <option value="99">99%+ approval</option>
        </select>
        <select value={sort} onChange={e => { setSort(e.target.value); setPage(0) }}
          className="text-xs bg-surface-raised border border-border rounded-lg px-2 py-1.5 text-text-secondary outline-none cursor-pointer">
          <option value="approvals">Most approvals</option>
          <option value="rate">Best approval rate</option>
          <option value="salary">Highest salary</option>
          <option value="name">Name A–Z</option>
        </select>
      </div>

      {loading ? (
        <p className="text-text-muted text-sm animate-pulse">Loading...</p>
      ) : data.sponsors.length === 0 ? (
        <p className="text-text-muted text-sm">No sponsors match these filters. Run <code className="text-text-tertiary">python import_sponsors.py</code> if the table is empty.</p>
      ) : (
        <div className="space-y-1.5">
          {data.sponsors.map(s => (
            <div key={s.id} className="bg-surface-raised border border-border rounded-lg transition-all hover:border-border-hover">
              <div className="px-4 py-3 cursor-pointer" onClick={() => setExpanded(expanded === s.id ? null : s.id)}>
                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <div className="min-w-0 flex-1">
                    <span className="text-sm font-medium text-text-primary">{s.name}</span>
                    <span className="text-xs text-text-muted ml-2">{s.city}{s.state && `, ${s.state}`}</span>
                  </div>
                  <div className="flex items-center gap-3 text-xs shrink-0">
                    <span className="text-emerald-400 font-medium">{Math.round(s.total_approvals)} approvals</span>
                    <span className={s.approval_rate >= 95 ? 'text-emerald-400' : s.approval_rate >= 85 ? 'text-amber-400' : 'text-red-400'}>
                      {Math.round(s.approval_rate)}%
                    </span>
                    <span className="text-text-secondary">{fmtMoney(s.median_salary)} median</span>
                  </div>
                </div>
                {s.top_titles?.length > 0 && (
                  <div className="text-xs text-text-tertiary mt-1 truncate">
                    {s.top_titles.slice(0, 4).join(' · ')}
                  </div>
                )}
              </div>
              {expanded === s.id && (
                <div className="px-4 pb-3 pt-1 border-t border-border/50 space-y-2 animate-fade-in">
                  <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-text-tertiary">
                    {s.industry && <span>Industry: <span className="text-text-secondary">{s.industry}</span></span>}
                    {s.total_denials > 0 && <span>Denials: <span className="text-text-secondary">{Math.round(s.total_denials)}</span></span>}
                    {s.latest_funding_stage && <span>Funding: <span className="text-text-secondary">{s.latest_funding_stage}</span></span>}
                    {s.website && (
                      <a href={`https://${s.website.replace(/^https?:\/\//, '')}`} target="_blank" rel="noopener noreferrer"
                        className="text-accent hover:underline" onClick={e => e.stopPropagation()}>{s.website}</a>
                    )}
                  </div>
                  {s.executives && (
                    <div className="text-xs text-text-tertiary">
                      Executives: <span className="text-text-secondary">{s.executives}</span>
                    </div>
                  )}
                  {s.top_titles?.length > 4 && (
                    <div className="text-xs text-text-tertiary">
                      All sponsored roles: <span className="text-text-secondary">{s.top_titles.join(', ')}</span>
                    </div>
                  )}
                  <div className="flex gap-2 pt-1">
                    <a href={linkedinPeopleUrl(s.name)} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()}
                      className="text-xs px-2.5 py-1 rounded-md bg-sky-900/20 text-sky-400 hover:bg-sky-900/30 transition-all btn-press">
                      Find Recruiters ↗
                    </a>
                    <a href={jobsSearchUrl(s.name)} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()}
                      className="text-xs px-2.5 py-1 rounded-md bg-surface-overlay text-text-secondary hover:bg-border transition-all btn-press border border-border">
                      Find Open Roles ↗
                    </a>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-between pt-2">
          <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
            className="text-sm text-text-secondary hover:text-text-primary disabled:text-text-muted disabled:cursor-default transition-colors btn-press">
            Previous
          </button>
          <span className="text-xs text-text-muted">Page {page + 1} of {totalPages}</span>
          <button onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1}
            className="text-sm text-text-secondary hover:text-text-primary disabled:text-text-muted disabled:cursor-default transition-colors btn-press">
            Next
          </button>
        </div>
      )}
    </div>
  )
}
