import { useState, useEffect, useCallback } from 'react'
import { api } from '../api'

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
  const [followUp, setFollowUp] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    const params = { limit: PAGE_SIZE, offset: page * PAGE_SIZE }
    if (filter) params.status = filter
    api.getJobs(params).then(data => {
      setJobs(data.jobs || [])
      setTotal(data.total || 0)
    }).finally(() => setLoading(false))
  }, [filter, page])

  useEffect(() => { load() }, [load])

  const changeFilter = (f) => {
    setFilter(f)
    setPage(0)
  }

  const totalPages = Math.ceil(total / PAGE_SIZE)

  const handleApplyClick = (job) => {
    window.open(job.apply_link, '_blank')
    setFollowUp(job)
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
    if (applied && selected?.id === target.id) {
      setSelected(null)
      setMatchResult(null)
    }
    load()
  }

  const handleSkipJob = async (reason, job = null) => {
    const target = job || followUp
    if (!target) return
    await api.updateJob(target.id, { status: 'skipped', notes: reason })
    setFollowUp(null)
    if (selected?.id === target.id) {
      setSelected(null)
      setMatchResult(null)
    }
    load()
  }

  const handleBlockCompany = async (reason, job = null) => {
    const target = job || followUp
    if (!target) return
    await api.blockCompany(target.company, reason)
    setFollowUp(null)
    if (selected?.id === target.id) {
      setSelected(null)
      setMatchResult(null)
    }
    load()
  }

  const handleMatch = async (job) => {
    setMatching(job.id)
    try {
      const result = await api.matchJob(job.id)
      setMatchResult(result)
      setSelected({
        ...job,
        match_pct: result.match_pct,
        match_summary: result.summary,
        team: result.team,
        project: result.project,
      })
      load()
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

  const handleClearQueue = async () => {
    if (!confirm('Skip all pending jobs in the queue?')) return
    await api.clearQueue()
    setSelected(null)
    setMatchResult(null)
    load()
  }

  return (
    <div className="flex gap-5">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-3 mb-5">
          <h1 className="text-xl font-semibold text-text-primary">Job Queue</h1>
          {filter === 'pending' && jobs.length > 0 && (
            <button
              onClick={handleClearQueue}
              className="text-xs text-danger/60 hover:text-danger transition-all duration-150"
            >
              Clear queue
            </button>
          )}
          <div className="flex gap-1 ml-auto bg-surface rounded-lg p-1 border border-border">
            {['pending', 'applied', 'skipped', ''].map(s => (
              <button
                key={s}
                onClick={() => changeFilter(s)}
                className={`text-xs px-3 py-1.5 rounded-md transition-all duration-150 ${
                  filter === s
                    ? 'bg-accent/15 text-accent font-medium'
                    : 'text-text-muted hover:text-text-secondary'
                }`}
              >
                {s || 'All'}
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <p className="text-text-muted animate-pulse">Loading...</p>
        ) : jobs.length === 0 ? (
          <p className="text-text-muted">No jobs found. Run discovery from the dashboard.</p>
        ) : (
          <>
            <div className="text-xs text-text-muted mb-3">{total} jobs</div>
            <div className="space-y-1.5">
              {jobs.map(job => (
                <div
                  key={job.id}
                  onClick={() => { setSelected(job); setMatchResult(null) }}
                  className={`bg-surface-raised border rounded-lg p-3.5 cursor-pointer transition-all duration-150 ${
                    selected?.id === job.id
                      ? 'border-accent/40 bg-accent/[0.03]'
                      : 'border-border hover:border-border-hover hover:bg-surface-overlay/50'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="font-medium text-text-primary text-sm truncate">{job.title}</div>
                      <div className="text-sm text-text-tertiary mt-0.5">{job.company} {job.location && `· ${job.location}`}</div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {job.match_pct != null && (
                        <span className={`text-xs px-2 py-0.5 rounded-md font-medium ${
                          job.match_pct >= 70 ? 'bg-accent-muted text-accent' :
                          job.match_pct >= 40 ? 'bg-amber-900/20 text-amber-400' :
                          'bg-red-900/20 text-red-400'
                        }`}>
                          {job.match_pct}%
                        </span>
                      )}
                      <span className="text-xs text-text-muted font-mono tabular-nums">{(job.score || 0).toFixed(2)}</span>
                      <span className={`text-xs px-2 py-0.5 rounded-md capitalize ${STATUS_COLORS[job.status] || 'bg-surface-overlay text-text-muted'}`}>
                        {job.status}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 mt-2 text-xs text-text-muted">
                    <span>{job.ats}</span>
                    <span>{job.source}</span>
                    {job.posted_at && <span>Posted {new Date(job.posted_at).toLocaleDateString()}</span>}
                  </div>
                </div>
              ))}
            </div>

            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-4 pt-3 border-t border-border">
                <button
                  onClick={() => setPage(p => Math.max(0, p - 1))}
                  disabled={page === 0}
                  className="text-sm text-text-secondary hover:text-text-primary disabled:text-text-muted disabled:cursor-default transition-colors"
                >
                  Previous
                </button>
                <span className="text-xs text-text-muted">
                  Page {page + 1} of {totalPages}
                </span>
                <button
                  onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                  disabled={page >= totalPages - 1}
                  className="text-sm text-text-secondary hover:text-text-primary disabled:text-text-muted disabled:cursor-default transition-colors"
                >
                  Next
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {selected && (
        <div className="w-96 shrink-0 bg-surface-raised border border-border rounded-xl p-5 sticky top-20 self-start max-h-[calc(100vh-6rem)] overflow-y-auto">
          <h2 className="text-text-primary font-semibold text-lg leading-tight">{selected.title}</h2>
          <p className="text-text-tertiary text-sm mt-1 mb-4">{selected.company} · {selected.location}</p>

          <div className="flex gap-2 mb-3 flex-wrap">
            <button
              onClick={() => handleApplyClick(selected)}
              className="bg-accent hover:bg-accent-hover text-white font-medium text-sm px-4 py-2 rounded-lg transition-all duration-150"
            >
              Apply
            </button>
            {selected.match_pct == null && (
              <button
                onClick={() => handleMatch(selected)}
                disabled={matching === selected.id}
                className="bg-surface-overlay hover:bg-border disabled:opacity-50 text-accent text-sm px-4 py-2 rounded-lg transition-all duration-150 border border-accent/25"
              >
                {matching === selected.id ? 'Matching...' : 'Match %'}
              </button>
            )}
            <button
              onClick={() => handleLinkedIn(selected)}
              className="bg-surface-overlay hover:bg-border text-text-secondary text-sm px-4 py-2 rounded-lg transition-all duration-150 border border-border"
            >
              Find Recruiters
            </button>
            {selected.apply_link && (
              <a
                href={selected.apply_link}
                target="_blank"
                rel="noopener noreferrer"
                className="bg-surface-overlay hover:bg-border text-text-secondary text-sm px-4 py-2 rounded-lg transition-all duration-150 border border-border inline-block"
              >
                Open Link
              </a>
            )}
          </div>

          <div className="flex flex-wrap gap-1.5 mb-5">
            <button
              onClick={() => handleFollowUpConfirm(true, false, selected)}
              className="text-xs px-3 py-1.5 rounded-md bg-emerald-900/20 text-emerald-400 hover:bg-emerald-900/30 transition-all duration-150"
            >
              Mark Applied
            </button>
            <button
              onClick={() => handleFollowUpConfirm(true, true, selected)}
              className="text-xs px-3 py-1.5 rounded-md bg-surface-overlay text-accent hover:bg-border transition-all duration-150 border border-accent/15"
            >
              Applied + Recruiter
            </button>
            <button
              onClick={() => handleFollowUpConfirm(false, true, selected)}
              className="text-xs px-3 py-1.5 rounded-md bg-surface-overlay text-text-secondary hover:bg-border transition-all duration-150 border border-border"
            >
              Contacted Recruiter
            </button>
            <button
              onClick={() => handleSkipJob('Not interested', selected)}
              className="text-xs px-3 py-1.5 rounded-md bg-surface-overlay text-text-muted hover:text-text-tertiary hover:bg-border transition-all duration-150 border border-border"
            >
              Skip
            </button>
            <button
              onClick={() => handleSkipJob('No sponsorship', selected)}
              className="text-xs px-3 py-1.5 rounded-md text-danger/60 hover:text-danger bg-red-900/10 hover:bg-red-900/20 transition-all duration-150"
            >
              No Sponsorship
            </button>
            <button
              onClick={() => handleBlockCompany('no sponsorship', selected)}
              className="text-xs px-3 py-1.5 rounded-md text-danger/60 hover:text-danger bg-red-900/10 hover:bg-red-900/20 transition-all duration-150"
            >
              Block {selected.company}
            </button>
          </div>

          {(matchResult?.recommended_resume || selected.recommended_resume) && (
            <div className="bg-accent/[0.05] border border-accent/15 rounded-lg p-4 mb-4">
              <div className="flex justify-between items-center mb-1">
                <span className="text-sm text-text-tertiary">Recommended Resume</span>
                <span className="text-accent font-semibold text-sm">{RESUME_LABELS[matchResult?.recommended_resume || selected.recommended_resume] || matchResult?.recommended_resume || selected.recommended_resume}</span>
              </div>
              {matchResult?.resume_scores && Object.keys(matchResult.resume_scores).length > 0 && (
                <div className="flex gap-2 mt-2.5 flex-wrap">
                  {Object.entries(matchResult.resume_scores)
                    .sort(([,a], [,b]) => b - a)
                    .map(([type, score]) => (
                      <span key={type} className={`text-xs px-2 py-1 rounded-md ${
                        type === matchResult?.recommended_resume
                          ? 'bg-accent/15 text-accent font-medium'
                          : 'bg-surface-overlay text-text-muted'
                      }`}>
                        {RESUME_LABELS[type] || type}: {score}
                      </span>
                    ))}
                </div>
              )}
              {matchResult?.matched_keywords?.[matchResult.recommended_resume] && (
                <div className="text-xs text-text-muted mt-2">
                  Matched: {matchResult.matched_keywords[matchResult.recommended_resume].join(', ')}
                </div>
              )}
            </div>
          )}

          {selected.match_pct != null && (
            <div className="bg-surface rounded-lg p-4 mb-4 border border-border">
              <div className="flex justify-between items-center mb-2">
                <span className="text-sm text-text-tertiary">AI Match</span>
                <span className={`text-lg font-bold ${
                  selected.match_pct >= 70 ? 'text-accent' :
                  selected.match_pct >= 40 ? 'text-warning' : 'text-danger'
                }`}>{selected.match_pct}%</span>
              </div>
              {selected.match_summary && <p className="text-sm text-text-secondary leading-relaxed">{selected.match_summary}</p>}
              {selected.team && <p className="text-xs text-text-muted mt-2">Team: {selected.team}</p>}
              {selected.project && <p className="text-xs text-text-muted">Project: {selected.project}</p>}
            </div>
          )}

          <div className="text-sm text-text-tertiary space-y-1.5 mb-4">
            <div>Score: <span className="text-text-primary font-medium">{(selected.score || 0).toFixed(2)}</span></div>
            <div>ATS: <span className="text-text-secondary">{selected.ats}</span></div>
            <div>Source: <span className="text-text-secondary">{selected.source}</span></div>
            {selected.posted_at && <div>Posted: <span className="text-text-secondary">{new Date(selected.posted_at).toLocaleDateString()}</span></div>}
          </div>

          {selected.description && (
            <div className="border-t border-border pt-4">
              <h3 className="text-sm font-medium text-text-secondary mb-2">Description</h3>
              <p className="text-xs text-text-tertiary whitespace-pre-wrap max-h-64 overflow-y-auto leading-relaxed">{selected.description}</p>
            </div>
          )}
        </div>
      )}

      {followUp && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50" onClick={() => setFollowUp(null)}>
          <div className="bg-surface-raised border border-border rounded-xl p-6 w-96 shadow-2xl" onClick={e => e.stopPropagation()}>
            <h3 className="text-text-primary font-semibold text-lg mb-1">Follow-up</h3>
            <p className="text-text-tertiary text-sm mb-5">{followUp.title} at {followUp.company}</p>

            <div className="space-y-2.5">
              <button
                onClick={() => handleFollowUpConfirm(true, false)}
                className="w-full bg-accent hover:bg-accent-hover text-white font-medium text-sm px-4 py-2.5 rounded-lg transition-all duration-150"
              >
                Yes, I applied
              </button>
              <button
                onClick={() => handleFollowUpConfirm(true, true)}
                className="w-full bg-surface-overlay hover:bg-border text-accent text-sm px-4 py-2.5 rounded-lg transition-all duration-150 border border-accent/25"
              >
                Applied + contacted recruiter
              </button>
              <button
                onClick={() => handleFollowUpConfirm(false, true)}
                className="w-full bg-surface-overlay hover:bg-border text-text-secondary text-sm px-4 py-2.5 rounded-lg transition-all duration-150 border border-border"
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
