import { useState, useRef, useEffect } from 'react'
import { useActivity } from '../ActivityContext'

const kindColor = (k) => ({
  discovery: 'text-accent',
  matching: 'text-purple-400',
  backup: 'text-emerald-400',
}[k] || 'text-text-tertiary')

const kindDot = (k) => ({
  discovery: 'bg-accent',
  matching: 'bg-purple-400',
  backup: 'bg-emerald-400',
}[k] || 'bg-text-muted')

function elapsed(since) {
  if (!since) return ''
  const s = Math.max(0, Math.floor((Date.now() - new Date(since).getTime()) / 1000))
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  return `${m}m ${s % 60}s`
}

export default function ActivityPanel() {
  const { tasks = [], recent = [], events = [] } = useActivity()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  const [, force] = useState(0)

  // Re-render every second while open so elapsed timers tick.
  useEffect(() => {
    if (!open) return
    const i = setInterval(() => force(n => n + 1), 1000)
    return () => clearInterval(i)
  }, [open])

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const active = tasks.length > 0

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="relative p-2 text-text-tertiary hover:text-text-primary transition-colors"
        title="Background activity"
      >
        <svg className={`w-5 h-5 ${active ? 'animate-spin text-accent' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
        {active && (
          <span className="absolute top-1 right-1 w-2.5 h-2.5 bg-accent rounded-full animate-pulse" />
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 w-[26rem] max-w-[90vw] bg-surface-raised border border-border rounded-xl shadow-2xl shadow-black/40 z-50 animate-fade-in overflow-hidden">
          <div className="px-4 py-3 border-b border-border flex items-center justify-between">
            <span className="text-sm font-semibold text-text-primary">Activity</span>
            <span className="text-xs text-text-muted">{active ? `${tasks.length} running` : 'Idle'}</span>
          </div>

          <div className="max-h-[28rem] overflow-y-auto">
            {/* Active tasks */}
            {tasks.length > 0 && (
              <div className="px-4 py-3 space-y-3 border-b border-border/60">
                {tasks.map(t => {
                  const pct = t.total ? Math.min(100, Math.round((t.current / t.total) * 100)) : null
                  return (
                    <div key={t.id}>
                      <div className="flex items-center justify-between gap-2">
                        <span className="flex items-center gap-2 text-sm text-text-primary min-w-0">
                          <span className={`w-2 h-2 rounded-full ${kindDot(t.kind)} animate-pulse shrink-0`} />
                          <span className="font-medium truncate">{t.label}</span>
                        </span>
                        <span className="text-[11px] text-text-muted shrink-0">{elapsed(t.started_at)}</span>
                      </div>
                      {t.detail && <div className="text-xs text-text-tertiary mt-1 truncate pl-4">{t.detail}</div>}
                      {pct !== null && (
                        <div className="flex items-center gap-2 mt-1.5 pl-4">
                          <div className="flex-1 bg-surface rounded-full h-1.5 overflow-hidden">
                            <div className={`h-full rounded-full ${kindDot(t.kind)} transition-all duration-300`} style={{ width: `${pct}%` }} />
                          </div>
                          <span className="text-[11px] text-text-muted shrink-0">{t.current}/{t.total}</span>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}

            {/* Recently finished */}
            {recent.length > 0 && (
              <div className="px-4 pt-2.5 pb-1">
                <span className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">Recent</span>
                {recent.map(t => (
                  <div key={t.id} className="flex items-center justify-between gap-2 py-1">
                    <span className="flex items-center gap-2 text-xs text-text-secondary min-w-0">
                      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${t.status === 'error' ? 'bg-red-400' : 'bg-text-muted'}`} />
                      <span className="truncate">{t.label}</span>
                    </span>
                    <span className="text-[11px] text-text-muted truncate max-w-[45%]">{t.detail}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Event log */}
            <div className="px-4 pt-2 pb-3">
              <span className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">Log</span>
              {events.length === 0 ? (
                <div className="text-xs text-text-muted py-3 text-center">No activity yet.</div>
              ) : (
                <div className="mt-1 space-y-0.5 font-mono">
                  {events.slice(0, 80).map((e, i) => (
                    <div key={i} className="flex gap-2 text-[11px] leading-relaxed">
                      <span className="text-text-muted shrink-0">{new Date(e.ts).toLocaleTimeString([], { hour12: false })}</span>
                      <span className={`shrink-0 ${kindColor(e.kind)}`}>{e.kind}</span>
                      <span className="text-text-tertiary break-all">{e.msg}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
