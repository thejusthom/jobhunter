import { useState, useEffect } from 'react'
import { api } from '../api'

const RESUME_LABELS = {
  ai: 'AI/ML',
  frontend: 'Frontend',
  backend: 'Backend',
  sre: 'SRE/DevOps',
  fullstack: 'Full Stack',
}

export default function Evaluations() {
  const [evals, setEvals] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.getEvaluations().then(setEvals).finally(() => setLoading(false))
  }, [])

  if (loading) return <p className="text-text-muted animate-pulse">Loading evaluations...</p>

  return (
    <div>
      <div className="flex items-center gap-3 mb-5">
        <h1 className="text-xl font-semibold text-text-primary">AI Evaluations</h1>
        <span className="text-sm text-text-muted">{evals.length} evaluated</span>
      </div>

      {evals.length === 0 ? (
        <p className="text-text-muted">No evaluations yet. Use "Match %" on a job in the queue to evaluate it.</p>
      ) : (
        <div className="space-y-3">
          {evals.map(ev => (
            <div key={ev.id} className="bg-surface-raised border border-border rounded-xl p-5 transition-all duration-150 hover:border-border-hover">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-text-primary font-semibold text-sm truncate">{ev.title}</div>
                  <div className="text-sm text-text-tertiary">{ev.company}</div>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  {ev.match_pct != null && (
                    <span className={`text-2xl font-bold ${
                      ev.match_pct >= 70 ? 'text-accent' :
                      ev.match_pct >= 40 ? 'text-warning' : 'text-danger'
                    }`}>{ev.match_pct}%</span>
                  )}
                </div>
              </div>

              <div className="flex gap-2 mt-3 text-xs flex-wrap">
                {ev.recommended_resume && (
                  <span className="bg-accent-muted text-accent px-2.5 py-1 rounded-md font-medium">
                    Resume: {RESUME_LABELS[ev.recommended_resume] || ev.recommended_resume}
                  </span>
                )}
                <span className={`px-2.5 py-1 rounded-md ${ev.team ? 'bg-accent-muted text-accent' : 'bg-surface-overlay text-text-muted'}`}>
                  {ev.team ? `Team: ${ev.team}` : 'No team found'}
                </span>
                {ev.project && (
                  <span className="bg-surface-overlay text-text-secondary px-2.5 py-1 rounded-md">
                    Project: {ev.project}
                  </span>
                )}
                {ev.acted_at && (
                  <span className="text-text-muted px-2.5 py-1">{new Date(ev.acted_at).toLocaleString()}</span>
                )}
              </div>

              {ev.match_summary && (
                <p className="text-sm text-text-secondary mt-3 leading-relaxed">{ev.match_summary}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
