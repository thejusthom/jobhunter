import { useState, useEffect, useRef } from 'react'
import { api } from '../api'

const RESUME_LABELS = {
  ai: 'AI/ML', frontend: 'Frontend', backend: 'Backend',
  sre: 'SRE/DevOps', fullstack: 'Full Stack',
}

export default function AutoApply() {
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)
  const [minScore, setMinScore] = useState(60)
  const [extWait, setExtWait] = useState(8)
  const [limit, setLimit] = useState(50)

  // Engine state (polled)
  const [engine, setEngine] = useState(null)
  const pollRef = useRef(null)
  const logsEndRef = useRef(null)

  // Outreach
  const [outreach, setOutreach] = useState(null)
  const [outreachLoading, setOutreachLoading] = useState(false)
  const [copied, setCopied] = useState(null)

  const loadJobs = () => {
    setLoading(true)
    api.getJobs({ status: 'pending', min_score: minScore, limit: 200 }).then(data => {
      const scored = (data.jobs || []).filter(j => j.match_pct != null && j.apply_link)
        .sort((a, b) => (b.match_pct || 0) - (a.match_pct || 0))
      setJobs(scored)
    }).finally(() => setLoading(false))
  }

  useEffect(() => { loadJobs() }, [minScore])

  // Poll engine status when running/paused
  useEffect(() => {
    const poll = () => {
      api.autoApplyStatus().then(s => {
        setEngine(s)
        // Generate outreach when paused on a new job
        if (s.status === 'paused' && s.current_job && s.current_job.match_pct > 60) {
          setOutreach(prev => {
            // Only generate if job changed
            if (!prev || prev._jobId !== s.current_job.id) {
              generateOutreach(s.current_job)
            }
            return prev
          })
        }
      }).catch(() => {})
    }
    poll()
    pollRef.current = setInterval(poll, 1500)
    return () => clearInterval(pollRef.current)
  }, [])

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [engine?.logs?.length])

  const generateOutreach = async (job) => {
    setOutreachLoading(true)
    try {
      const msg = await api.generateOutreach(job.id, {})
      setOutreach({ ...msg, _jobId: job.id })
    } catch (_) {}
    setOutreachLoading(false)
  }

  const handleCopy = (text, label) => {
    navigator.clipboard.writeText(text)
    setCopied(label)
    setTimeout(() => setCopied(null), 2000)
  }

  const handleStart = async () => {
    try {
      await api.autoApplyStart({ min_score: minScore, limit, ext_wait: extWait })
      setOutreach(null)
    } catch (e) {
      alert(e.message)
    }
  }

  const handleStop = () => api.autoApplyStop()

  const handleAction = (action) => {
    setOutreach(null)
    api.autoApplyAction(action)
  }

  const isActive = engine && (engine.status === 'running' || engine.status === 'paused')
  const isDone = engine?.status === 'done'
  const isError = engine?.status === 'error'
  const isPaused = engine?.status === 'paused'
  const job = engine?.current_job

  // -------------------------------------------------------------------------
  // ERROR screen
  // -------------------------------------------------------------------------
  if (isError) {
    return (
      <div className="max-w-2xl mx-auto">
        <div className="bg-red-900/15 border border-red-500/30 rounded-xl p-6 mt-8">
          <h2 className="text-lg font-semibold text-red-400 mb-2">Auto-Apply Failed</h2>
          <p className="text-sm text-red-300/80 mb-4">{engine.error}</p>
          {engine.logs?.length > 0 && (
            <div className="bg-[#0a0a0a] rounded-lg p-3 mb-4 max-h-40 overflow-y-auto font-mono">
              {engine.logs.map((l, i) => (
                <div key={i} className="text-[11px] text-text-muted/70 leading-relaxed">{l}</div>
              ))}
            </div>
          )}
          <button
            onClick={() => setEngine(null)}
            className="bg-surface-overlay hover:bg-border text-text-secondary px-5 py-2 rounded-lg border border-border transition-all text-sm"
          >
            Back to Setup
          </button>
        </div>
      </div>
    )
  }

  // -------------------------------------------------------------------------
  // DONE screen
  // -------------------------------------------------------------------------
  if (isDone && engine.applied + engine.skipped > 0) {
    return (
      <div className="max-w-2xl mx-auto">
        <div className="text-center py-12">
          <div className="text-5xl mb-4">&#127881;</div>
          <h2 className="text-xl font-semibold text-text-primary mb-2">Session Complete</h2>
          <p className="text-text-secondary mb-6">
            Applied to <span className="text-accent font-bold">{engine.applied}</span> jobs,
            skipped <span className="text-text-muted">{engine.skipped}</span>
          </p>
          <button
            onClick={() => { setEngine(null); loadJobs() }}
            className="bg-surface-overlay hover:bg-border text-text-secondary px-6 py-2.5 rounded-lg border border-border transition-all"
          >
            Back to Setup
          </button>
        </div>

        {/* Logs */}
        {engine.logs?.length > 0 && (
          <div className="bg-surface border border-border rounded-lg p-4 mt-4 max-h-48 overflow-y-auto">
            <h3 className="text-xs font-medium text-text-muted mb-2">Session Log</h3>
            {engine.logs.map((l, i) => (
              <div key={i} className="text-[11px] text-text-muted font-mono leading-relaxed">{l}</div>
            ))}
          </div>
        )}
      </div>
    )
  }

  // -------------------------------------------------------------------------
  // ACTIVE screen (running or paused)
  // -------------------------------------------------------------------------
  if (isActive) {
    return (
      <div className="max-w-3xl mx-auto">
        {/* Progress bar */}
        <div className="flex items-center gap-4 mb-5">
          <div className="flex-1 bg-surface rounded-full h-2 overflow-hidden">
            <div
              className="bg-accent h-full rounded-full transition-all duration-500"
              style={{ width: `${((engine.current_idx) / Math.max(engine.total, 1)) * 100}%` }}
            />
          </div>
          <span className="text-sm text-text-muted whitespace-nowrap">
            {engine.current_idx + 1} / {engine.total}
          </span>
          <span className="text-xs text-emerald-400">{engine.applied} applied</span>
          <span className="text-xs text-text-muted">{engine.skipped} skipped</span>
          <button
            onClick={handleStop}
            className="text-xs text-danger/60 hover:text-danger transition-colors"
          >
            Stop
          </button>
        </div>

        {/* Status badge */}
        <div className="flex items-center gap-2 mb-4">
          {engine.status === 'running' && (
            <span className="inline-flex items-center gap-1.5 text-xs text-accent">
              <span className="w-2 h-2 bg-accent rounded-full animate-pulse" />
              Automating...
            </span>
          )}
          {isPaused && (
            <span className="inline-flex items-center gap-1.5 text-xs text-amber-400">
              <span className="w-2 h-2 bg-amber-400 rounded-full animate-pulse" />
              Needs your attention
            </span>
          )}
        </div>

        {/* Current job card */}
        {job && (
          <div className={`bg-surface-raised border rounded-xl p-6 mb-4 ${
            isPaused ? 'border-amber-500/40' : 'border-border'
          }`}>
            <div className="flex items-start justify-between mb-3">
              <div>
                <h2 className="text-lg font-semibold text-text-primary">{job.title}</h2>
                <p className="text-text-tertiary">{job.company} · {job.location}</p>
              </div>
              <span className={`text-2xl font-bold ${
                job.match_pct >= 70 ? 'text-accent' : job.match_pct >= 40 ? 'text-amber-400' : 'text-red-400'
              }`}>{job.match_pct}%</span>
            </div>

            {job.match_summary && (
              <p className="text-sm text-text-secondary mb-3 leading-relaxed">{job.match_summary}</p>
            )}

            {job.recommended_resume && (
              <div className="text-xs text-text-muted mb-4">
                Resume: <span className="text-accent font-medium">{RESUME_LABELS[job.recommended_resume] || job.recommended_resume}</span>
              </div>
            )}

            {/* When paused — action buttons */}
            {isPaused && (
              <>
                <div className="bg-amber-900/10 border border-amber-500/20 rounded-lg p-3 mb-4 text-sm text-amber-300">
                  {engine.pause_reason || 'Complete the application manually, then tell me what happened.'}
                </div>

                {/* Open the apply page */}
                {job.apply_link && (
                  <button
                    onClick={() => window.open(job.apply_link, '_blank')}
                    className="w-full bg-surface-overlay hover:bg-border text-text-secondary font-medium py-2.5 rounded-lg transition-all mb-3 text-sm border border-border"
                  >
                    Open Application Page
                  </button>
                )}

                <div className="grid grid-cols-2 gap-2 mb-3">
                  <button
                    onClick={() => handleAction('applied')}
                    className="bg-emerald-900/20 hover:bg-emerald-900/30 text-emerald-400 font-medium py-2.5 rounded-lg transition-all text-sm"
                  >
                    Applied
                  </button>
                  <button
                    onClick={() => handleAction('applied_recruiter')}
                    className="bg-emerald-900/10 hover:bg-emerald-900/20 text-emerald-400/80 font-medium py-2.5 rounded-lg transition-all text-sm border border-emerald-500/15"
                  >
                    Applied + Recruiter
                  </button>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleAction('skip')}
                    className="flex-1 bg-surface-overlay hover:bg-border text-text-muted text-xs py-2 rounded-lg border border-border transition-all"
                  >
                    Skip
                  </button>
                  <button
                    onClick={() => handleAction('no_sponsorship')}
                    className="flex-1 bg-red-900/10 hover:bg-red-900/20 text-danger/60 text-xs py-2 rounded-lg transition-all"
                  >
                    No Sponsorship
                  </button>
                  <button
                    onClick={() => handleAction('stop')}
                    className="flex-1 bg-red-900/15 hover:bg-red-900/25 text-danger text-xs py-2 rounded-lg transition-all"
                  >
                    Stop Session
                  </button>
                </div>
              </>
            )}

            {/* When running — just show a waiting state */}
            {engine.status === 'running' && (
              <div className="bg-accent/5 border border-accent/15 rounded-lg p-4 text-center">
                <div className="text-sm text-accent animate-pulse mb-1">Automating application...</div>
                <div className="text-xs text-text-muted">Extension fills fields, engine clicks Next/Submit</div>
              </div>
            )}
          </div>
        )}

        {/* Outreach messages (show when paused) */}
        {isPaused && outreachLoading && !outreach && (
          <div className="bg-purple-900/10 border border-purple-500/20 rounded-xl p-4 mb-4">
            <p className="text-xs text-purple-400 animate-pulse">Drafting outreach messages...</p>
          </div>
        )}

        {isPaused && outreach && (
          <div className="bg-purple-900/10 border border-purple-500/20 rounded-xl p-5 mb-4">
            <h3 className="text-sm font-medium text-purple-400 mb-3">Outreach Messages</h3>
            <div className="mb-3">
              <div className="flex justify-between items-center mb-1.5">
                <span className="text-xs text-text-tertiary font-medium">Full Version</span>
                <button
                  onClick={() => handleCopy(outreach.full, 'full')}
                  className="text-xs px-2 py-0.5 rounded bg-purple-900/30 text-purple-400 hover:bg-purple-900/50 transition-all"
                >
                  {copied === 'full' ? 'Copied!' : 'Copy'}
                </button>
              </div>
              <p className="text-xs text-text-secondary leading-relaxed bg-surface rounded-md p-3 border border-border whitespace-pre-wrap">{outreach.full}</p>
            </div>
            <div>
              <div className="flex justify-between items-center mb-1.5">
                <span className="text-xs text-text-tertiary font-medium">Short Version <span className="text-text-muted">({outreach.short?.length} chars)</span></span>
                <button
                  onClick={() => handleCopy(outreach.short, 'short')}
                  className="text-xs px-2 py-0.5 rounded bg-purple-900/30 text-purple-400 hover:bg-purple-900/50 transition-all"
                >
                  {copied === 'short' ? 'Copied!' : 'Copy'}
                </button>
              </div>
              <p className="text-xs text-text-secondary leading-relaxed bg-surface rounded-md p-3 border border-border whitespace-pre-wrap">{outreach.short}</p>
            </div>
          </div>
        )}

        {/* Live logs */}
        {engine.logs?.length > 0 && (
          <div className="bg-[#0a0a0a] border border-border rounded-lg p-3 max-h-40 overflow-y-auto font-mono">
            {engine.logs.map((l, i) => (
              <div key={i} className="text-[11px] text-text-muted/70 leading-relaxed">{l}</div>
            ))}
            <div ref={logsEndRef} />
          </div>
        )}
      </div>
    )
  }

  // -------------------------------------------------------------------------
  // SETUP screen (idle / not started)
  // -------------------------------------------------------------------------
  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-xl font-semibold text-text-primary mb-5">Auto Apply</h1>

      <div className="bg-surface-raised border border-border rounded-xl p-6 mb-5">
        {/* Min Score */}
        <div className="flex items-center gap-4 mb-4">
          <label className="text-sm text-text-secondary w-28">Min Match</label>
          <input
            type="range" min={0} max={100} step={5} value={minScore}
            onChange={e => setMinScore(Number(e.target.value))}
            className="flex-1 accent-accent"
          />
          <span className="text-accent font-bold text-lg w-12 text-right">{minScore}%</span>
        </div>

        {/* Extension wait */}
        <div className="flex items-center gap-4 mb-4">
          <label className="text-sm text-text-secondary w-28">Ext. Wait</label>
          <input
            type="range" min={3} max={20} step={1} value={extWait}
            onChange={e => setExtWait(Number(e.target.value))}
            className="flex-1 accent-accent"
          />
          <span className="text-text-primary font-medium text-lg w-12 text-right">{extWait}s</span>
        </div>

        {/* Limit */}
        <div className="flex items-center gap-4 mb-5">
          <label className="text-sm text-text-secondary w-28">Max Jobs</label>
          <input
            type="range" min={5} max={100} step={5} value={limit}
            onChange={e => setLimit(Number(e.target.value))}
            className="flex-1 accent-accent"
          />
          <span className="text-text-primary font-medium text-lg w-12 text-right">{limit}</span>
        </div>

        {loading ? (
          <p className="text-text-muted animate-pulse">Loading jobs...</p>
        ) : (
          <>
            <p className="text-text-secondary mb-4">
              <span className="text-accent font-bold text-2xl">{jobs.length}</span>
              <span className="ml-2">scored jobs ready to apply</span>
            </p>

            {jobs.length > 0 && (
              <>
                <div className="max-h-64 overflow-y-auto space-y-1 mb-5 border border-border rounded-lg p-2">
                  {jobs.slice(0, limit).map((j) => (
                    <div key={j.id} className="flex items-center justify-between text-xs py-1.5 px-2 rounded hover:bg-surface-overlay">
                      <div className="flex-1 min-w-0">
                        <span className="text-text-primary truncate block">{j.title}</span>
                        <span className="text-text-muted">{j.company}</span>
                      </div>
                      <span className={`font-medium ml-3 ${
                        j.match_pct >= 70 ? 'text-accent' : j.match_pct >= 40 ? 'text-amber-400' : 'text-red-400'
                      }`}>{j.match_pct}%</span>
                    </div>
                  ))}
                </div>

                <button
                  onClick={handleStart}
                  className="w-full bg-accent hover:bg-accent-hover text-white font-semibold text-base py-3 rounded-lg transition-all duration-150"
                >
                  Start Auto-Apply ({Math.min(jobs.length, limit)} jobs)
                </button>

                <p className="text-xs text-text-muted mt-3 text-center">
                  Chrome will restart automatically with your profile + extensions
                </p>
              </>
            )}
          </>
        )}
      </div>

      <div className="bg-surface border border-border rounded-lg p-4 text-xs text-text-muted space-y-1.5">
        <p><span className="text-text-secondary font-medium">How it works:</span></p>
        <p>1. Click Start — engine restarts Chrome with remote debugging (auto-closes existing Chrome)</p>
        <p>2. Connects to YOUR Chrome (with your profile, extensions, saved logins)</p>
        <p>3. Opens each job's apply page, waits for your extension to fill fields</p>
        <p>4. Automatically clicks Next/Continue/Submit through each step</p>
        <p>5. If it hits a CAPTCHA, file upload, or error — pauses for you to handle it</p>
        <p>6. Outreach messages are auto-generated while you're reviewing</p>
      </div>
    </div>
  )
}
