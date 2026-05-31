import { useState, useEffect, useCallback } from 'react'
import { api } from '../api'
import LinkedInIdEditor from '../components/LinkedInIdEditor'

const STATUS_COLORS = {
  pending: 'bg-accent-muted text-accent',
  applied: 'bg-emerald-900/30 text-emerald-400',
  skipped: 'bg-surface-overlay text-text-muted',
  rejected: 'bg-red-900/20 text-red-400',
}

const RESUME_LABELS = {
  ai: 'AI/ML',
  frontend: 'Frontend',
  backend: 'Backend',
  sre: 'SRE/DevOps',
  fullstack: 'Full Stack',
}

const SOURCE_COLORS = {
  simplify: { bg: '#7c3aed22', text: '#a78bfa', border: '#7c3aed44' },   // purple
  jsearch: { bg: '#2563eb22', text: '#60a5fa', border: '#2563eb44' },     // blue
  adzuna: { bg: '#0d948822', text: '#2dd4bf', border: '#0d948844' },      // teal
  manual_url: { bg: '#d9770622', text: '#fbbf24', border: '#d9770644' },  // amber
  linkedin: { bg: '#0a66c222', text: '#38bdf8', border: '#0a66c244' },    // sky
}

const ATS_COLORS = {
  greenhouse: { bg: '#16a34a22', text: '#4ade80', border: '#16a34a44' },  // green
  lever: { bg: '#0ea5e922', text: '#38bdf8', border: '#0ea5e944' },       // sky
  ashby: { bg: '#6366f122', text: '#a5b4fc', border: '#6366f144' },       // indigo
  workday: { bg: '#ea580c22', text: '#fb923c', border: '#ea580c44' },     // orange
  smartrecruiters: { bg: '#db277722', text: '#f472b6', border: '#db277744' }, // pink
  linkedin: { bg: '#0a66c222', text: '#38bdf8', border: '#0a66c244' },    // sky
  oracle_hcm: { bg: '#dc262622', text: '#f87171', border: '#dc262644' }, // red
  amazon: { bg: '#ca8a0422', text: '#facc15', border: '#ca8a0444' },      // yellow
  apple: { bg: '#52525b22', text: '#a1a1aa', border: '#52525b44' },       // zinc
  pinpoint: { bg: '#06b6d422', text: '#22d3ee', border: '#06b6d444' },    // cyan
  simplify: { bg: '#7c3aed22', text: '#a78bfa', border: '#7c3aed44' },    // purple
}

// Merged lookup: check SOURCE_COLORS first, fall back to ATS_COLORS
const _badgeColor = (key) => SOURCE_COLORS[key] || ATS_COLORS[key] || null

const _badgeStyle = (colorObj) => colorObj ? {
  backgroundColor: colorObj.bg,
  color: colorObj.text,
  borderColor: colorObj.border,
  borderWidth: '1px',
} : {}

const PAGE_SIZE = 25

export default function JobQueue() {
  const [jobs, setJobs] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [filter, setFilter] = useState('pending')
  const [selected, setSelected] = useState(null)
  const [matching, setMatching] = useState(null)
  const [matchResult, setMatchResult] = useState(null)
  const [loading, setLoading] = useState(true)
  const [addUrl, setAddUrl] = useState('')
  const [addingUrl, setAddingUrl] = useState(false)
  const [followUp, setFollowUp] = useState(null)
  const [search, setSearch] = useState('')
  const [searchDebounced, setSearchDebounced] = useState('')

  // Debounce search input
  useEffect(() => {
    const t = setTimeout(() => {
      setSearchDebounced(search)
      setPage(0)
    }, 300)
    return () => clearTimeout(t)
  }, [search])

  const load = useCallback(() => {
    setLoading(true)
    const params = { limit: PAGE_SIZE, offset: page * PAGE_SIZE }
    if (filter) params.status = filter
    if (searchDebounced.trim()) params.search = searchDebounced.trim()
    api.getJobs(params).then(data => {
      setJobs(data.jobs || [])
      setTotal(data.total || 0)
    }).finally(() => setLoading(false))
  }, [filter, page, searchDebounced])

  useEffect(() => { load() }, [load])

  const changeFilter = (f) => {
    setFilter(f)
    setPage(0)
  }

  const totalPages = Math.ceil(total / PAGE_SIZE)

  // After an action (applied/skipped/blocked), advance to the next job in the list
  const selectNextJob = (currentId) => {
    const idx = jobs.findIndex(j => j.id === currentId)
    if (idx >= 0 && idx < jobs.length - 1) {
      setSelected(jobs[idx + 1])
    } else if (idx > 0) {
      setSelected(jobs[idx - 1])
    } else {
      setSelected(null)
    }
    setMatchResult(null)
    setOutreach(null)
  }

  const handleFollowUpConfirm = async (applied, contactedRecruiter, job = null) => {
    const target = job || followUp
    if (!target) return

    if (applied) {
      await api.updateJob(target.id, { status: 'applied' })
      await api.createApplication({
        job_id: target.id,
        title: target.title,
        company: target.company,
        location: target.location,
        apply_link: target.apply_link,
        source: target.source || 'jobhunter',
        resume_used: matchResult?.recommended_resume || selected?.recommended_resume || '',
      })
    }

    if (contactedRecruiter) {
      await api.createRecruiter({
        name: '',
        company: target.company,
        application_id: null,
        notes: `Contacted via LinkedIn for ${target.title}`,
      })
    }

    setFollowUp(null)
    if (selected?.id === target.id) {
      selectNextJob(target.id)
    }
    load()
  }

  const handleSkipJob = async (reason, job = null) => {
    const target = job || followUp
    if (!target) return
    await api.updateJob(target.id, { status: 'skipped', notes: reason })
    setFollowUp(null)
    if (selected?.id === target.id) {
      selectNextJob(target.id)
    }
    load()
  }

  const handleBlockCompany = async (reason, job = null) => {
    const target = job || followUp
    if (!target) return
    await api.blockCompany(target.company, reason)
    setFollowUp(null)
    if (selected?.id === target.id) {
      selectNextJob(target.id)
    }
    load()
  }

  const handleMatch = async (job) => {
    setMatching(job.id)
    setOutreach(null)
    try {
      const result = await api.matchJob(job.id)
      setMatchResult(result)
      setSelected({
        ...job,
        match_pct: result.match_pct,
        match_summary: result.summary,
        team: result.team,
        project: result.project,
        min_years_required: result.min_years_required,
        sponsorship_available: result.sponsorship_available,
        salary_min: result.salary_min,
        salary_max: result.salary_max,
      })
      load()
      // Auto-generate outreach messages after match
      // Re-fetch job to get server-side updates (e.g. JD fetched for Simplify jobs)
      const updatedJob = await api.getJob(job.id)
      if (updatedJob.description) {
        setSelected(prev => ({ ...prev, description: updatedJob.description }))
      }
      if (result.match_pct >= 50) {
        setOutreachLoading(true)
        try {
          const msg = await api.generateOutreach(job.id, {})
          setOutreach(msg)
        } catch (_) { /* silent — outreach is bonus */ }
        setOutreachLoading(false)
      }
    } catch (e) {
      alert(e.message)
    } finally {
      setMatching(null)
    }
  }

  const handleLinkedIn = async (job) => {
    try {
      const result = await api.linkedinSearch(job.id)
      window.open(result.url, '_blank')
    } catch (e) {
      alert(e.message)
    }
  }

  const handleLinkedInLeaders = async (job, role = 'hiring') => {
    try {
      const result = await api.linkedinLeaders(job.id, role)
      window.open(result.url, '_blank')
    } catch (e) {
      alert(e.message)
    }
  }

  const [emailResults, setEmailResults] = useState(null)
  const [emailLoading, setEmailLoading] = useState(false)
  const [outreach, setOutreach] = useState(null)
  const [outreachLoading, setOutreachLoading] = useState(false)
  const [outreachForm, setOutreachForm] = useState({ recruiter_name: '', linkedin_post: '' })
  const [copied, setCopied] = useState(null)

  const handleFindEmails = async (job) => {
    setEmailLoading(true)
    setEmailResults(null)
    try {
      const result = await api.findEmails(job.id)
      setEmailResults(result)
    } catch (e) {
      alert(e.message)
    } finally {
      setEmailLoading(false)
    }
  }

  const handleOutreach = async (job) => {
    setOutreachLoading(true)
    setOutreach(null)
    try {
      const result = await api.generateOutreach(job.id, {
        recruiter_name: outreachForm.recruiter_name || null,
        linkedin_post: outreachForm.linkedin_post || null,
      })
      setOutreach(result)
    } catch (e) {
      alert(e.message)
    } finally {
      setOutreachLoading(false)
    }
  }

  const handleCopy = (text, label) => {
    navigator.clipboard.writeText(text)
    setCopied(label)
    setTimeout(() => setCopied(null), 2000)
  }

  const handleClearQueue = async () => {
    if (!confirm('Skip all pending jobs in the queue?')) return
    await api.clearQueue()
    setSelected(null)
    setMatchResult(null)
    load()
  }

  const [batchMatching, setBatchMatching] = useState(false)
  const [batchProgress, setBatchProgress] = useState({ done: 0, total: 0 })

  const handleMatchAll = async () => {
    const unmatched = jobs.filter(j => j.match_pct == null)
    if (unmatched.length === 0) return alert('All jobs on this page are already matched')
    if (!confirm(`Run AI match + outreach on ${unmatched.length} unmatched jobs?`)) return

    setBatchMatching(true)
    setBatchProgress({ done: 0, total: unmatched.length })

    for (let i = 0; i < unmatched.length; i++) {
      const job = unmatched[i]
      try {
        const result = await api.matchJob(job.id)
        // Auto-generate outreach for decent matches (same as single match)
        if (result.match_pct >= 50) {
          try {
            await api.generateOutreach(job.id, {})
          } catch (_) { /* outreach is bonus */ }
        }
      } catch (_) { /* continue on error */ }
      setBatchProgress({ done: i + 1, total: unmatched.length })
    }

    setBatchMatching(false)
    load()
  }

  const closeDetail = () => {
    setSelected(null)
    setOutreach(null)
    setMatchResult(null)
  }

  return (
    <div className="flex flex-col md:flex-row gap-4 h-[calc(100vh-5rem)]">
      {/* Job list — full width on mobile, fixed width on desktop */}
      <div className={`w-full md:w-[480px] shrink-0 min-w-0 flex flex-col overflow-hidden transition-all duration-300 ${selected ? 'hidden md:flex' : 'flex'}`}>
        {/* Header row */}
        <div className="flex items-center gap-2 mb-2 animate-fade-in">
          <h1 className="text-lg font-semibold text-text-primary">Job Queue</h1>
          {jobs.length > 0 && (
            <button
              onClick={handleMatchAll}
              disabled={batchMatching}
              className="text-xs text-accent/70 hover:text-accent disabled:opacity-50 transition-all duration-150 btn-press"
            >
              {batchMatching ? `Matching ${batchProgress.done}/${batchProgress.total}...` : 'Match All'}
            </button>
          )}
          {filter === 'pending' && jobs.length > 0 && (
            <button
              onClick={handleClearQueue}
              className="text-xs text-danger/60 hover:text-danger transition-all duration-150 btn-press"
            >
              Clear
            </button>
          )}
          <form
            className="flex gap-1.5 ml-auto"
            onSubmit={async (e) => {
              e.preventDefault()
              if (!addUrl.trim() || addingUrl) return
              setAddingUrl(true)
              try {
                const job = await api.addJobByUrl(addUrl.trim())
                setAddUrl('')
                load()
                setSelected(job)
                setOutreach(null)
              } catch (err) {
                alert(err.message)
              }
              setAddingUrl(false)
            }}
          >
            <input
              type="text"
              value={addUrl}
              onChange={e => setAddUrl(e.target.value)}
              placeholder="Paste job URL..."
              className="bg-surface border border-border rounded-md px-2.5 py-1 text-xs text-text-primary placeholder-text-muted w-40 sm:w-56 focus:outline-none focus:border-accent/40 transition-all duration-200"
            />
            <button
              type="submit"
              disabled={!addUrl.trim() || addingUrl}
              className="bg-accent/15 hover:bg-accent/25 disabled:opacity-40 text-accent text-xs px-3 py-1 rounded-md transition-all btn-press"
            >
              {addingUrl ? 'Adding...' : 'Add'}
            </button>
          </form>
        </div>

        {/* Filter tabs */}
        <div className="flex gap-1 bg-surface rounded-lg p-1 border border-border mb-3 animate-fade-in-up" style={{ animationDelay: '50ms' }}>
          {['pending', 'applied', 'skipped', ''].map(s => (
            <button
              key={s}
              onClick={() => changeFilter(s)}
              className={`text-xs px-3 py-1.5 rounded-md flex-1 transition-all duration-200 btn-press ${
                filter === s
                  ? 'bg-accent/15 text-accent font-medium shadow-sm'
                  : 'text-text-muted hover:text-text-secondary'
              }`}
            >
              {s || 'All'}
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="relative mb-4 animate-fade-in-up" style={{ animationDelay: '100ms' }}>
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search by job title or company..."
            className="w-full bg-surface border border-border rounded-lg px-3 py-2 pl-9 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent/40 focus:ring-1 focus:ring-accent/20 transition-all duration-200"
          />
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          {search && (
            <button
              onClick={() => setSearch('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary text-xs transition-colors"
            >
              Clear
            </button>
          )}
        </div>

        {/* Job list content */}
        {loading ? (
          <div className="space-y-2 animate-pulse">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="bg-surface-raised border border-border rounded-lg p-3.5 animate-shimmer">
                <div className="h-4 bg-surface-overlay rounded w-3/4 mb-2" />
                <div className="h-3 bg-surface-overlay rounded w-1/2" />
              </div>
            ))}
          </div>
        ) : jobs.length === 0 ? (
          <div className="text-center py-12 animate-fade-in-up">
            <div className="text-3xl mb-3 opacity-30">&#128269;</div>
            <p className="text-text-muted">No jobs found. Run discovery from the dashboard.</p>
          </div>
        ) : (
          <>
            <div className="text-xs text-text-muted mb-2 animate-fade-in">{total} jobs</div>
            <div className="space-y-1.5 overflow-y-auto flex-1 min-h-0 pr-1 stagger-children">
              {jobs.map(job => (
                <div
                  key={job.id}
                  onClick={() => {
                    setSelected(job)
                    setMatchResult(null)
                    if (job.outreach_full && job.outreach_short) {
                      setOutreach({ full: job.outreach_full, short: job.outreach_short })
                    } else {
                      setOutreach(null)
                    }
                  }}
                  className={`bg-surface-raised border rounded-lg p-3.5 cursor-pointer transition-all duration-200 hover:translate-x-0.5 group ${
                    selected?.id === job.id
                      ? 'border-accent/40 bg-accent/[0.03] shadow-[0_0_12px_-4px_rgba(16,185,129,0.15)]'
                      : 'border-border hover:border-border-hover hover:bg-surface-overlay/50 hover:shadow-md hover:shadow-black/20'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="font-medium text-text-primary text-sm truncate group-hover:text-accent transition-colors duration-200">{job.title}</div>
                      <div className="text-sm text-text-tertiary mt-0.5 truncate">{job.company} {job.location && `· ${job.location}`}</div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {job.match_pct != null && (
                        <span className={`text-xs px-2 py-0.5 rounded-md font-medium transition-all ${
                          job.match_pct >= 70 ? 'bg-accent-muted text-accent' :
                          job.match_pct >= 40 ? 'bg-amber-900/20 text-amber-400' :
                          'bg-red-900/20 text-red-400'
                        }`}>
                          {job.match_pct}%
                        </span>
                      )}
                      <span className="text-xs text-text-muted font-mono tabular-nums">{job.score || 0}</span>
                      <span className={`text-xs px-2 py-0.5 rounded-md capitalize ${STATUS_COLORS[job.status] || 'bg-surface-overlay text-text-muted'}`}>
                        {job.status}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 mt-2 text-xs flex-wrap" style={{ color: '#525252' }}>
                    <span
                      className="px-1.5 py-0.5 rounded text-[10px] font-medium uppercase tracking-wide"
                      style={_badgeStyle(_badgeColor(job.source))}
                    >{job.source || 'unknown'}</span>
                    {job.ats && job.ats !== job.source && (
                      <span
                        className="px-1.5 py-0.5 rounded text-[10px] font-medium uppercase tracking-wide"
                        style={_badgeStyle(_badgeColor(job.ats))}
                      >{job.ats}</span>
                    )}
                    {(job.salary_min || job.salary_max) && (
                      <span className="text-emerald-400 font-medium">
                        {(() => {
                          const fmt = (n) => n >= 1000 ? `$${Math.round(n / 1000)}K` : `$${n}`
                          if (job.salary_min && job.salary_max) return `${fmt(job.salary_min)}–${fmt(job.salary_max)}`
                          if (job.salary_min) return `${fmt(job.salary_min)}+`
                          return `≤${fmt(job.salary_max)}`
                        })()}
                      </span>
                    )}
                    {job.posted_at && <span className="ml-1">Posted {new Date(job.posted_at).toLocaleDateString()}</span>}
                  </div>
                </div>
              ))}
            </div>

            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-4 pt-3 border-t border-border animate-fade-in">
                <button
                  onClick={() => setPage(p => Math.max(0, p - 1))}
                  disabled={page === 0}
                  className="text-sm text-text-secondary hover:text-text-primary disabled:text-text-muted disabled:cursor-default transition-colors btn-press"
                >
                  Previous
                </button>
                <span className="text-xs text-text-muted">
                  Page {page + 1} of {totalPages}
                </span>
                <button
                  onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                  disabled={page >= totalPages - 1}
                  className="text-sm text-text-secondary hover:text-text-primary disabled:text-text-muted disabled:cursor-default transition-colors btn-press"
                >
                  Next
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {/* Detail panel */}
      {selected && (
        <>
          {/* Mobile overlay backdrop */}
          <div className="md:hidden mobile-detail-overlay" onClick={closeDetail} />

          <div className="mobile-detail-panel md:relative md:flex-1 md:min-w-0 bg-surface-raised border border-border rounded-xl flex flex-col overflow-hidden animate-slide-in-right md:animate-scale-in">
            {/* Sticky header */}
            <div className="px-4 sm:px-5 pt-4 pb-3 border-b border-border shrink-0 space-y-2.5">
              {/* Mobile back button + title */}
              <div>
                <button onClick={closeDetail} className="md:hidden flex items-center gap-1.5 text-text-tertiary hover:text-text-primary transition-colors mb-2 -ml-1 px-1 py-0.5">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
                  </svg>
                  <span className="text-sm font-medium">Back to jobs</span>
                </button>
                <div className="min-w-0">
                  <h2 className="text-text-primary font-semibold text-base sm:text-lg leading-tight">{selected.title}</h2>
                  <div className="flex items-center gap-2 mt-1 flex-wrap">
                    <p className="text-text-tertiary text-sm">{selected.company} · {selected.location}</p>
                    <LinkedInIdEditor company={selected.company} compact />
                  </div>
                </div>
              </div>

              {/* Row 1: Primary actions */}
              <div className="flex gap-1.5 sm:gap-2 flex-wrap items-center animate-fade-in" style={{ animationDelay: '100ms' }}>
                {selected.apply_link && (
                  <a href={selected.apply_link} target="_blank" rel="noopener noreferrer"
                    className="bg-accent hover:bg-accent-hover text-white font-medium text-xs sm:text-sm px-3 sm:px-4 py-1.5 rounded-lg transition-all duration-200 inline-block btn-press animate-pulse-glow">
                    Apply ↗
                  </a>
                )}
                {selected.match_pct == null && (
                  <button onClick={() => handleMatch(selected)} disabled={matching === selected.id}
                    className="bg-surface-overlay hover:bg-border disabled:opacity-50 text-accent text-xs sm:text-sm px-2.5 sm:px-3 py-1.5 rounded-lg border border-accent/25 transition-all duration-200 btn-press">
                    {matching === selected.id ? 'Matching...' : 'Match %'}
                  </button>
                )}
                {selected.match_pct != null && (
                  <button onClick={() => handleMatch(selected)} disabled={matching === selected.id}
                    className="bg-surface-overlay hover:bg-border disabled:opacity-50 text-text-tertiary text-xs sm:text-sm px-2 sm:px-2.5 py-1.5 rounded-lg border border-border transition-all duration-200 btn-press" title="Re-run AI matching">
                    {matching === selected.id ? '...' : '↻ Re-match'}
                  </button>
                )}
                {selected.match_pct != null && (
                  <>
                    <button onClick={() => handleLinkedIn(selected)}
                      className="bg-surface-overlay hover:bg-border text-text-secondary text-xs sm:text-sm px-2.5 sm:px-3 py-1.5 rounded-lg border border-border transition-all duration-200 btn-press">Recruiters</button>
                    <button onClick={() => handleLinkedInLeaders(selected, 'hiring')}
                      className="bg-surface-overlay hover:bg-border text-text-secondary text-xs sm:text-sm px-2.5 sm:px-3 py-1.5 rounded-lg border border-border transition-all duration-200 btn-press">Hiring Mgr</button>
                    <button onClick={() => handleLinkedInLeaders(selected, 'team')}
                      className="bg-surface-overlay hover:bg-border text-text-secondary text-xs sm:text-sm px-2.5 sm:px-3 py-1.5 rounded-lg border border-border transition-all duration-200 btn-press">Referral</button>
                    <button onClick={() => handleFindEmails(selected)} disabled={emailLoading}
                      className="bg-surface-overlay hover:bg-border disabled:opacity-50 text-text-secondary text-xs sm:text-sm px-2.5 sm:px-3 py-1.5 rounded-lg border border-border transition-all duration-200 btn-press">
                      {emailLoading ? 'Finding...' : 'Emails'}
                    </button>
                  </>
                )}
              </div>

              {/* Row 2: Status actions */}
              <div className="flex flex-wrap gap-1 sm:gap-1.5 items-center animate-fade-in" style={{ animationDelay: '150ms' }}>
                <button onClick={() => handleFollowUpConfirm(true, false, selected)}
                  className="text-[11px] sm:text-xs px-2 sm:px-2.5 py-1 rounded-md bg-emerald-900/20 text-emerald-400 hover:bg-emerald-900/30 transition-all duration-200 btn-press">Applied</button>
                <button onClick={() => handleFollowUpConfirm(true, true, selected)}
                  className="text-[11px] sm:text-xs px-2 sm:px-2.5 py-1 rounded-md bg-surface-overlay text-accent hover:bg-border border border-accent/15 transition-all duration-200 btn-press">Applied + Recruiter</button>
                <button onClick={() => handleFollowUpConfirm(false, true, selected)}
                  className="text-[11px] sm:text-xs px-2 sm:px-2.5 py-1 rounded-md bg-surface-overlay text-text-secondary hover:bg-border border border-border transition-all duration-200 btn-press">Contacted</button>
                <button onClick={() => handleSkipJob('Not interested', selected)}
                  className="text-[11px] sm:text-xs px-2 sm:px-2.5 py-1 rounded-md bg-surface-overlay text-text-muted hover:bg-border border border-border transition-all duration-200 btn-press">Skip</button>
                <button onClick={() => handleSkipJob('No sponsorship', selected)}
                  className="text-[11px] sm:text-xs px-2 sm:px-2.5 py-1 rounded-md text-danger/60 hover:text-danger bg-red-900/10 transition-all duration-200 btn-press">No Visa</button>
                <button onClick={() => handleSkipJob('Expired / closed', selected)}
                  className="text-[11px] sm:text-xs px-2 sm:px-2.5 py-1 rounded-md text-amber-500/60 hover:text-amber-400 bg-amber-900/10 transition-all duration-200 btn-press">Expired</button>
                <button onClick={() => handleSkipJob('Bad / incorrect link', selected)}
                  className="text-[11px] sm:text-xs px-2 sm:px-2.5 py-1 rounded-md text-amber-500/60 hover:text-amber-400 bg-amber-900/10 transition-all duration-200 btn-press">Bad Link</button>
                <button onClick={() => handleSkipJob('Not US location', selected)}
                  className="text-[11px] sm:text-xs px-2 sm:px-2.5 py-1 rounded-md text-amber-500/60 hover:text-amber-400 bg-amber-900/10 transition-all duration-200 btn-press">Not US</button>
                <button onClick={() => handleBlockCompany('no sponsorship', selected)}
                  className="text-[11px] sm:text-xs px-2 sm:px-2.5 py-1 rounded-md text-danger/60 hover:text-danger bg-red-900/10 transition-all duration-200 btn-press">Block Co.</button>
              </div>

              {/* Row 3: Copy buttons */}
              <div className="flex gap-1.5 sm:gap-2 items-center animate-fade-in" style={{ animationDelay: '200ms' }}>
                {selected.description && (
                  <button onClick={() => {
                      const tmp = document.createElement('div')
                      tmp.innerHTML = selected.description
                      navigator.clipboard.writeText(tmp.textContent || tmp.innerText || '')
                      setCopied('jd')
                      setTimeout(() => setCopied(null), 2000)
                    }}
                    className={`text-[11px] sm:text-xs px-2.5 sm:px-3 py-1.5 rounded-md transition-all duration-300 border btn-press ${
                      copied === 'jd' ? 'bg-emerald-900/20 text-emerald-400 border-emerald-500/20 scale-105' : 'bg-surface-overlay text-text-muted hover:text-text-secondary border-border'
                    }`}>
                    {copied === 'jd' ? '✓ JD Copied' : 'Copy JD'}
                  </button>
                )}
                {outreach?.full && (
                  <button onClick={() => handleCopy(outreach.full, 'full')}
                    className={`text-[11px] sm:text-xs px-2.5 sm:px-3 py-1.5 rounded-md transition-all duration-300 border btn-press ${
                      copied === 'full' ? 'bg-purple-900/20 text-purple-400 border-purple-500/20 scale-105' : 'bg-purple-900/10 text-purple-400/70 hover:text-purple-400 border-purple-500/15'
                    }`}>
                    {copied === 'full' ? '✓ Full Copied' : 'Copy Full Outreach'}
                  </button>
                )}
                {outreach?.short && (
                  <button onClick={() => handleCopy(outreach.short, 'short')}
                    className={`text-[11px] sm:text-xs px-2.5 sm:px-3 py-1.5 rounded-md transition-all duration-300 border btn-press ${
                      copied === 'short' ? 'bg-purple-900/20 text-purple-400 border-purple-500/20 scale-105' : 'bg-purple-900/10 text-purple-400/70 hover:text-purple-400 border-purple-500/15'
                    }`}>
                    {copied === 'short' ? '✓ Short Copied' : 'Copy Short Outreach'}
                  </button>
                )}
              </div>
            </div>

            {/* Scrollable content */}
            <div className="overflow-y-auto px-4 sm:px-5 pt-3 pb-5 flex-1 min-h-0">

            {(matchResult?.recommended_resume || selected.recommended_resume) && (() => {
              const recResume = matchResult?.recommended_resume || selected.recommended_resume
              const resScores = matchResult?.resume_scores || selected.resume_scores
              const matchedKw = matchResult?.matched_keywords || selected.matched_keywords
              return (
              <div className="bg-accent/[0.05] border border-accent/15 rounded-lg p-3 sm:p-4 mb-4 animate-fade-in-up">
                <div className="flex justify-between items-center mb-1">
                  <span className="text-sm text-text-tertiary">Recommended Resume</span>
                  <span className="text-accent font-semibold text-sm">{RESUME_LABELS[recResume] || recResume}</span>
                </div>
                {resScores && Object.keys(resScores).length > 0 && (
                  <div className="flex gap-2 mt-2.5 flex-wrap">
                    {Object.entries(resScores)
                      .sort(([,a], [,b]) => b - a)
                      .map(([type, score]) => (
                        <span key={type} className={`text-xs px-2 py-1 rounded-md transition-all ${
                          type === recResume
                            ? 'bg-accent/15 text-accent font-medium'
                            : 'bg-surface-overlay text-text-muted'
                        }`}>
                          {RESUME_LABELS[type] || type}: {score}
                        </span>
                      ))}
                  </div>
                )}
                {matchedKw?.[recResume] && (
                  <div className="text-xs text-text-muted mt-2">
                    Matched: {matchedKw[recResume].join(', ')}
                  </div>
                )}
              </div>
              )
            })()}

            {selected.match_pct != null && (
              <div className="bg-surface rounded-lg p-3 sm:p-4 mb-4 border border-border animate-fade-in-up" style={{ animationDelay: '50ms' }}>
                <div className="flex justify-between items-center mb-2">
                  <span className="text-sm text-text-tertiary">AI Match</span>
                  <span className={`text-lg font-bold ${
                    selected.match_pct >= 70 ? 'text-accent' :
                    selected.match_pct >= 40 ? 'text-warning' : 'text-danger'
                  }`}>{selected.match_pct}%</span>
                </div>

                {(selected.sponsorship_available === false || (matchResult?.sponsorship_available === false)) && (
                  <div className="bg-red-900/20 text-red-400 text-xs px-3 py-1.5 rounded-md mb-2 font-medium animate-fade-in">
                    No Visa Sponsorship
                  </div>
                )}
                {(selected.min_years_required || matchResult?.min_years_required) && (
                  <div className={`text-xs px-3 py-1.5 rounded-md mb-2 font-medium animate-fade-in ${
                    (selected.min_years_required || matchResult?.min_years_required) >= 5
                      ? 'bg-red-900/20 text-red-400'
                      : 'bg-amber-900/20 text-amber-400'
                  }`}>
                    Requires {selected.min_years_required || matchResult?.min_years_required}+ years experience
                  </div>
                )}

                {(selected.salary_min || selected.salary_max || matchResult?.salary_min || matchResult?.salary_max) && (
                  <div className="text-xs px-3 py-1.5 rounded-md mb-2 font-medium animate-fade-in bg-emerald-900/20 text-emerald-400">
                    💰 {(() => {
                      const min = selected.salary_min || matchResult?.salary_min
                      const max = selected.salary_max || matchResult?.salary_max
                      const fmt = (n) => n >= 1000 ? `$${Math.round(n / 1000)}K` : `$${n}`
                      if (min && max) return `${fmt(min)} – ${fmt(max)}`
                      if (min) return `${fmt(min)}+`
                      return `Up to ${fmt(max)}`
                    })()}
                  </div>
                )}

                {(selected.team || selected.project) && (
                  <div className="flex flex-wrap gap-2 mb-2">
                    {selected.team && (
                      <span className="text-xs px-2.5 py-1 rounded-md bg-blue-900/20 text-blue-400 font-medium">
                        Team: {selected.team}
                      </span>
                    )}
                    {selected.project && (
                      <span className="text-xs px-2.5 py-1 rounded-md bg-purple-900/20 text-purple-400 font-medium">
                        Project: {selected.project}
                      </span>
                    )}
                  </div>
                )}

                {selected.match_summary && <p className="text-sm text-text-secondary leading-relaxed">{selected.match_summary}</p>}
              </div>
            )}

            <div className="text-sm text-text-tertiary space-y-1.5 mb-4 animate-fade-in-up" style={{ animationDelay: '100ms' }}>
              <div>Score: <span className="text-text-primary font-medium">{selected.score || 0}</span></div>
              <div>ATS: <span className="px-1.5 py-0.5 rounded text-[10px] font-medium uppercase tracking-wide" style={_badgeStyle(_badgeColor(selected.ats))}>{selected.ats || 'unknown'}</span></div>
              <div>Source: <span className="px-1.5 py-0.5 rounded text-[10px] font-medium uppercase tracking-wide" style={_badgeStyle(_badgeColor(selected.source))}>{selected.source || 'unknown'}</span></div>
              {selected.posted_at && <div>Posted: <span className="text-text-secondary">{new Date(selected.posted_at).toLocaleDateString()}</span></div>}
            </div>

            {emailResults && emailResults.company === selected.company && (
              <div className="bg-surface border border-border rounded-lg p-3 sm:p-4 mb-4 animate-scale-in">
                <div className="flex justify-between items-center mb-2">
                  <h3 className="text-sm font-medium text-text-secondary">Emails — {emailResults.company}</h3>
                  <button onClick={() => setEmailResults(null)} className="text-text-muted hover:text-text-tertiary text-xs transition-colors">✕</button>
                </div>
                {emailResults.domain && (
                  <p className="text-xs text-text-muted mb-1">Domain: <span className="text-text-secondary">{emailResults.domain}</span></p>
                )}
                {emailResults.pattern && (
                  <p className="text-xs text-text-muted mb-2">Pattern: <span className="text-accent">{emailResults.pattern}</span> (e.g. {emailResults.pattern.replace('{first}', 'jane').replace('{last}', 'doe').replace('{f}', 'j').replace('{l}', 'd')}@{emailResults.domain})</p>
                )}
                {emailResults.people.length > 0 ? (
                  <div className="space-y-2 max-h-48 overflow-y-auto">
                    {emailResults.people.map((p, i) => (
                      <div key={i} className="text-xs border-t border-border/50 pt-1.5">
                        <div className="flex justify-between">
                          <span className="text-text-primary font-medium">{p.first_name} {p.last_name}</span>
                          <span className="text-text-muted">{p.confidence}%</span>
                        </div>
                        {p.position && <div className="text-text-tertiary">{p.position}</div>}
                        <div className="flex gap-2 mt-0.5">
                          <a href={`mailto:${p.email}`} className="text-accent hover:underline">{p.email}</a>
                          {p.linkedin && <a href={p.linkedin} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline">LinkedIn</a>}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-text-muted">No engineering emails found. Try the email pattern above with a name from LinkedIn.</p>
                )}
              </div>
            )}

            {selected.description && (
              <div className="border-t border-border pt-4 animate-fade-in-up" style={{ animationDelay: '150ms' }}>
                <h3 className="text-sm font-medium text-text-secondary mb-2">Description</h3>
                <div
                  className="text-xs text-text-tertiary leading-relaxed prose prose-invert prose-xs prose-p:my-1 prose-li:my-0.5 prose-ul:my-1 prose-ol:my-1"
                  dangerouslySetInnerHTML={{ __html: selected.description }}
                />
              </div>
            )}

            {outreachLoading && !outreach && (
              <div className="bg-purple-900/10 border border-purple-500/20 rounded-lg p-4 mt-4 animate-fade-in">
                <p className="text-xs text-purple-400 animate-pulse">Drafting outreach messages...</p>
              </div>
            )}

            {outreach && (
              <div className="bg-purple-900/10 border border-purple-500/20 rounded-lg p-3 sm:p-4 mt-4 animate-scale-in">
                <div className="flex justify-between items-center mb-3">
                  <h3 className="text-sm font-medium text-purple-400">Outreach Messages</h3>
                  <button onClick={() => setOutreach(null)} className="text-text-muted hover:text-text-tertiary text-xs transition-colors">✕</button>
                </div>

                <div className="mb-3">
                  <div className="flex justify-between items-center mb-1.5">
                    <span className="text-xs text-text-tertiary font-medium">Full Version</span>
                    <button
                      onClick={() => handleCopy(outreach.full, 'full')}
                      className="text-xs px-2 py-0.5 rounded bg-purple-900/30 text-purple-400 hover:bg-purple-900/50 transition-all btn-press"
                    >
                      {copied === 'full' ? 'Copied!' : 'Copy'}
                    </button>
                  </div>
                  <p className="text-xs text-text-secondary leading-relaxed bg-surface rounded-md p-3 border border-border whitespace-pre-wrap">{outreach.full}</p>
                </div>

                <div className="mb-3">
                  <div className="flex justify-between items-center mb-1.5">
                    <span className="text-xs text-text-tertiary font-medium">Short Version <span className="text-text-muted">({outreach.short.length} chars)</span></span>
                    <button
                      onClick={() => handleCopy(outreach.short, 'short')}
                      className="text-xs px-2 py-0.5 rounded bg-purple-900/30 text-purple-400 hover:bg-purple-900/50 transition-all btn-press"
                    >
                      {copied === 'short' ? 'Copied!' : 'Copy'}
                    </button>
                  </div>
                  <p className="text-xs text-text-secondary leading-relaxed bg-surface rounded-md p-3 border border-border whitespace-pre-wrap">{outreach.short}</p>
                </div>

                <details className="text-xs">
                  <summary className="text-text-muted cursor-pointer hover:text-text-tertiary transition-colors">Regenerate with context</summary>
                  <div className="mt-2 space-y-2 animate-fade-in-up">
                    <input
                      placeholder="Recruiter name (optional)"
                      value={outreachForm.recruiter_name}
                      onChange={e => setOutreachForm({ ...outreachForm, recruiter_name: e.target.value })}
                      className="w-full bg-surface border border-border rounded px-2.5 py-1.5 text-xs text-text-primary placeholder-text-muted focus:border-purple-500/50 outline-none transition-all"
                    />
                    <textarea
                      placeholder="Paste recruiter's LinkedIn post (optional)"
                      value={outreachForm.linkedin_post}
                      onChange={e => setOutreachForm({ ...outreachForm, linkedin_post: e.target.value })}
                      className="w-full bg-surface border border-border rounded px-2.5 py-1.5 text-xs text-text-primary placeholder-text-muted focus:border-purple-500/50 outline-none transition-all"
                      rows={3}
                    />
                    <button
                      onClick={() => handleOutreach(selected)}
                      disabled={outreachLoading}
                      className="w-full bg-purple-900/30 hover:bg-purple-900/50 disabled:opacity-50 text-purple-400 text-xs py-1.5 rounded transition-all btn-press"
                    >
                      {outreachLoading ? 'Regenerating...' : 'Regenerate'}
                    </button>
                  </div>
                </details>
              </div>
            )}
            </div>{/* end scrollable content */}
          </div>
        </>
      )}

      {/* Follow-up modal */}
      {followUp && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 animate-fade-in" onClick={() => setFollowUp(null)}>
          <div className="bg-surface-raised border border-border rounded-xl p-5 sm:p-6 w-[calc(100%-2rem)] sm:w-96 shadow-2xl animate-scale-in mx-4" onClick={e => e.stopPropagation()}>
            <h3 className="text-text-primary font-semibold text-lg mb-1">Follow-up</h3>
            <p className="text-text-tertiary text-sm mb-5">{followUp.title} at {followUp.company}</p>

            <div className="space-y-2.5">
              <button
                onClick={() => handleFollowUpConfirm(true, false)}
                className="w-full bg-accent hover:bg-accent-hover text-white font-medium text-sm px-4 py-2.5 rounded-lg transition-all duration-200 btn-press"
              >
                Yes, I applied
              </button>
              <button
                onClick={() => handleFollowUpConfirm(true, true)}
                className="w-full bg-surface-overlay hover:bg-border text-accent text-sm px-4 py-2.5 rounded-lg transition-all duration-200 border border-accent/25 btn-press"
              >
                Applied + contacted recruiter
              </button>
              <button
                onClick={() => handleFollowUpConfirm(false, true)}
                className="w-full bg-surface-overlay hover:bg-border text-text-secondary text-sm px-4 py-2.5 rounded-lg transition-all duration-200 border border-border btn-press"
              >
                Only contacted recruiter
              </button>
              <button
                onClick={() => setFollowUp(null)}
                className="w-full text-text-muted hover:text-text-tertiary text-sm px-4 py-2 transition-all duration-150"
              >
                Not yet, just browsing
              </button>

              <div className="border-t border-border pt-2.5 mt-1 space-y-1">
                <button
                  onClick={() => handleSkipJob('Not interested')}
                  className="w-full text-text-muted hover:text-text-tertiary text-xs px-4 py-2 transition-all duration-150"
                >
                  Skip — not worth applying
                </button>
                <button
                  onClick={() => handleSkipJob('No sponsorship')}
                  className="w-full text-danger/70 hover:text-danger text-xs px-4 py-2 transition-all duration-150"
                >
                  No sponsorship — skip this role
                </button>
                <button
                  onClick={() => handleBlockCompany('no sponsorship')}
                  className="w-full text-danger/70 hover:text-danger text-xs px-4 py-2 transition-all duration-150"
                >
                  Block {followUp.company} — skip all roles
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
