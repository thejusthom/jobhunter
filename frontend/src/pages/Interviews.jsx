import { useState, useEffect, useCallback } from 'react'
import { api } from '../api'
import LinkedInIdEditor from '../components/LinkedInIdEditor'
import TimeSelect from '../components/TimeSelect'

const STATUSES = ['active', 'offer', 'accepted', 'rejected', 'withdrawn', 'on_hold', 'ghosted']
const ROUND_TYPES = ['phone', 'video', 'onsite', 'take_home', 'other']
const ROUND_STATUSES = ['pending', 'scheduled', 'completed', 'passed', 'failed', 'cancelled']
const SPONSORSHIP = [
  { value: 'not_discussed', label: 'Not discussed' },
  { value: 'will_sponsor', label: 'Will sponsor' },
  { value: 'no_sponsorship', label: 'No sponsorship' },
  { value: 'unclear', label: 'Unclear' },
]

const inputClass = "bg-surface border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:border-accent/50 outline-none transition-all duration-200"

const fmtDate = (s) => s ? new Date(s.includes('T') ? s : s.replace(' ', 'T')).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : ''
const toLocalInput = (s) => s ? s.replace(' ', 'T').slice(0, 16) : ''

const statusColor = (s) => ({
  active: 'text-sky-400 bg-sky-500/10 border-sky-500/20',
  offer: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
  accepted: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
  rejected: 'text-red-400 bg-red-500/10 border-red-500/20',
  withdrawn: 'text-text-muted bg-surface-overlay border-border',
  on_hold: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
  ghosted: 'text-text-muted bg-surface-overlay border-border',
}[s] || 'text-text-muted bg-surface-overlay border-border')

function SponsorshipBadge({ status, h1bKnown, h1bApprovals }) {
  const map = {
    not_discussed: { cls: 'text-amber-400 bg-amber-500/10 border-amber-500/25', label: '⚠ Discuss sponsorship' },
    will_sponsor: { cls: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20', label: 'Will sponsor' },
    no_sponsorship: { cls: 'text-red-400 bg-red-500/10 border-red-500/20', label: 'No sponsorship' },
    unclear: { cls: 'text-text-tertiary bg-surface-overlay border-border', label: 'Sponsorship unclear' },
  }
  const s = map[status] || map.not_discussed
  return (
    <span className="flex items-center gap-1.5 flex-wrap">
      <span className={`text-[11px] px-2 py-0.5 rounded-full border ${s.cls}`}>{s.label}</span>
      {h1bKnown && (
        <span className="text-[11px] px-2 py-0.5 rounded-full border text-emerald-400/80 bg-emerald-500/5 border-emerald-500/15"
          title="Found in your H-1B sponsors dataset">
          {'✓'} Known H-1B sponsor{h1bApprovals ? ` (${h1bApprovals})` : ''}
        </span>
      )}
    </span>
  )
}

export default function Interviews() {
  const [interviews, setInterviews] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('')
  const [search, setSearch] = useState('')
  const [searchDebounced, setSearchDebounced] = useState('')
  const [showForm, setShowForm] = useState(false)

  useEffect(() => {
    const t = setTimeout(() => setSearchDebounced(search), 300)
    return () => clearTimeout(t)
  }, [search])

  const load = useCallback(() => {
    setLoading(true)
    const params = {}
    if (filter) params.status = filter
    if (searchDebounced.trim()) params.search = searchDebounced.trim()
    Promise.all([api.getInterviews(params), api.getInterviewStats()])
      .then(([list, s]) => { setInterviews(list); setStats(s) })
      .finally(() => setLoading(false))
  }, [filter, searchDebounced])
  useEffect(() => { load() }, [load])

  const updateStatus = async (id, status) => {
    await api.updateInterview(id, { status })
    load()
  }

  const removeInterview = async (id) => {
    if (!confirm('Delete this interview and all its rounds?')) return
    await api.deleteInterview(id)
    load()
  }

  const notDiscussed = stats?.by_sponsorship?.not_discussed || 0

  return (
    <div className="animate-fade-in">
      <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
        <h1 className="text-xl font-semibold text-text-primary">Interviews</h1>
        <button
          onClick={() => setShowForm(!showForm)}
          className="bg-accent hover:bg-accent-hover text-white font-medium text-sm px-4 py-2 rounded-lg transition-all duration-200 btn-press"
        >
          {showForm ? 'Cancel' : '+ Add Interview'}
        </button>
      </div>

      {/* Stat chips */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
          <StatChip label="Active" value={stats.active} />
          <StatChip label="Offers" value={stats.offers} accent="text-emerald-400" />
          <StatChip label="Rejected" value={stats.rejected} accent="text-red-400" />
          <StatChip label="Rounds next 7d" value={stats.upcoming_rounds_7d} accent="text-sky-400" />
        </div>
      )}
      {notDiscussed > 0 && (
        <div className="mb-4 text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2">
          {'⚠'} {notDiscussed} {notDiscussed === 1 ? 'company has' : 'companies have'} no sponsorship conversation logged yet.
        </div>
      )}

      {showForm && <AddInterviewForm onDone={() => { setShowForm(false); load() }} />}

      {/* Filters */}
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <button onClick={() => setFilter('')}
          className={`text-xs px-2.5 py-1 rounded-md border transition-all ${!filter ? 'bg-accent/15 text-accent border-accent/30' : 'bg-surface-overlay text-text-tertiary border-border hover:text-text-secondary'}`}>
          All
        </button>
        {STATUSES.map(s => (
          <button key={s} onClick={() => setFilter(s)}
            className={`text-xs px-2.5 py-1 rounded-md border capitalize transition-all ${filter === s ? 'bg-accent/15 text-accent border-accent/30' : 'bg-surface-overlay text-text-tertiary border-border hover:text-text-secondary'}`}>
            {s.replace('_', ' ')}
          </button>
        ))}
      </div>

      <div className="relative mb-4">
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search by company or role..."
          className="w-full bg-surface border border-border rounded-lg px-3 py-2 pl-9 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent/40 focus:ring-1 focus:ring-accent/20 transition-all duration-200"
        />
        <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
      </div>

      {loading ? (
        <div className="space-y-2 animate-pulse">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="bg-surface-raised border border-border rounded-lg p-3.5 animate-shimmer">
              <div className="h-4 bg-surface-overlay rounded w-3/4 mb-2" />
              <div className="h-3 bg-surface-overlay rounded w-1/2" />
            </div>
          ))}
        </div>
      ) : interviews.length === 0 ? (
        <div className="text-center py-12">
          <div className="text-3xl mb-3 opacity-30">{'📅'}</div>
          <p className="text-text-muted">No interviews tracked yet. Add one from the queue, an application, or externally.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {interviews.map(iv => (
            <InterviewCard key={iv.id} iv={iv} onChangeStatus={updateStatus} onDelete={removeInterview} onReload={load} />
          ))}
        </div>
      )}
    </div>
  )
}

function StatChip({ label, value, accent = 'text-text-primary' }) {
  return (
    <div className="bg-surface-raised border border-border rounded-xl p-3 text-center">
      <div className={`text-2xl font-bold ${accent}`}>{value ?? 0}</div>
      <div className="text-text-tertiary text-xs mt-0.5">{label}</div>
    </div>
  )
}

function InterviewCard({ iv, onChangeStatus, onDelete, onReload }) {
  const [expanded, setExpanded] = useState(false)
  const [detail, setDetail] = useState(null)
  const [loadingDetail, setLoadingDetail] = useState(false)

  const loadDetail = useCallback(async () => {
    setLoadingDetail(true)
    try { setDetail(await api.getInterview(iv.id)) }
    finally { setLoadingDetail(false) }
  }, [iv.id])

  const toggle = () => {
    const next = !expanded
    setExpanded(next)
    if (next && !detail) loadDetail()
  }

  return (
    <div className="bg-surface-raised border border-border rounded-lg transition-all duration-200 hover:border-border-hover">
      <div className="p-3.5">
        <div className="flex items-start justify-between gap-2 flex-wrap sm:flex-nowrap">
          <div className="min-w-0 flex-1 cursor-pointer" onClick={toggle}>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-medium text-text-primary text-sm">{iv.company}</span>
              <LinkedInIdEditor company={iv.company} compact />
              <span className={`text-[10px] px-1.5 py-0.5 rounded uppercase tracking-wide border ${statusColor(iv.status)}`}>{iv.status.replace('_', ' ')}</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface-overlay text-text-muted border border-border">{iv.source}</span>
            </div>
            {iv.role && <div className="text-sm text-text-tertiary mt-0.5">{iv.role}{iv.location && ` · ${iv.location}`}</div>}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <select
              value={iv.status}
              onChange={e => onChangeStatus(iv.id, e.target.value)}
              onClick={e => e.stopPropagation()}
              className="bg-surface border border-border rounded-md text-xs text-text-primary px-2 py-1 outline-none cursor-pointer"
            >
              {STATUSES.map(s => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
            </select>
            <button onClick={toggle} className="text-text-muted hover:text-text-secondary text-xs px-1">
              {expanded ? '▲' : '▼'}
            </button>
          </div>
        </div>

        <div className="mt-2 flex items-center gap-3 flex-wrap">
          <SponsorshipBadge status={iv.sponsorship_status} h1bKnown={iv.h1b_known} h1bApprovals={iv.h1b_approvals} />
        </div>

        <div className="mt-2 flex items-center gap-3 text-xs text-text-muted flex-wrap">
          {iv.contact_name && (
            <span>{'👤'} {iv.contact_name}{iv.contact_role && `, ${iv.contact_role}`}</span>
          )}
          {iv.contact_email && <a href={`mailto:${iv.contact_email}`} className="text-accent hover:underline">{iv.contact_email}</a>}
          {iv.contact_linkedin && (
            <a href={iv.contact_linkedin.startsWith('http') ? iv.contact_linkedin : `https://${iv.contact_linkedin}`}
              target="_blank" rel="noopener noreferrer" className="text-sky-400 hover:underline">Contact {'↗'}</a>
          )}
          {(iv.salary_min || iv.salary_max) && (
            <span>{'💰'} {iv.salary_min ? `$${iv.salary_min.toLocaleString()}` : ''}{iv.salary_max ? ` - $${iv.salary_max.toLocaleString()}` : '+'}</span>
          )}
          <span className="text-text-tertiary">Rounds: {iv.rounds_done}/{iv.rounds_total}</span>
        </div>

        {iv.next_round_at && (
          <div className="mt-2 text-xs bg-sky-500/5 border border-sky-500/15 rounded-md px-2.5 py-1.5 text-sky-300 inline-flex items-center gap-2">
            {'⏰'} Next: <span className="font-medium">{iv.next_round_name || 'Round'}</span> {'·'} {fmtDate(iv.next_round_at)}
          </div>
        )}
      </div>

      {expanded && (
        <div className="border-t border-border px-3.5 py-3 animate-fade-in">
          {loadingDetail || !detail ? (
            <p className="text-xs text-text-muted animate-pulse">Loading rounds...</p>
          ) : (
            // Refresh only this card's detail on round/sponsorship edits so the list
            // doesn't re-sort and make the card jump away from the user.
            <ExpandedDetail detail={detail} onReload={loadDetail} onDelete={onDelete} />
          )}
        </div>
      )}
    </div>
  )
}

function ExpandedDetail({ detail, onReload, onDelete }) {
  const [savingSpons, setSavingSpons] = useState(false)
  const [sponsStatus, setSponsStatus] = useState(detail.sponsorship_status)
  const [sponsNotes, setSponsNotes] = useState(detail.sponsorship_notes || '')

  const saveSponsorship = async () => {
    setSavingSpons(true)
    try {
      await api.updateInterview(detail.id, { sponsorship_status: sponsStatus, sponsorship_notes: sponsNotes })
      await onReload()
    } finally { setSavingSpons(false) }
  }

  return (
    <div className="space-y-4">
      {/* Sponsorship block */}
      <div className="bg-surface border border-border rounded-lg p-3">
        <div className="text-xs font-semibold text-text-secondary mb-2">Sponsorship</div>
        <div className="flex gap-2 flex-wrap items-start">
          <select value={sponsStatus} onChange={e => setSponsStatus(e.target.value)} className={inputClass}>
            {SPONSORSHIP.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
          <textarea value={sponsNotes} onChange={e => setSponsNotes(e.target.value)} rows={1}
            placeholder="What did the recruiter say? (e.g. H-1B transfer ok, no new petitions...)"
            className={`flex-1 min-w-[200px] ${inputClass}`} />
          <button onClick={saveSponsorship} disabled={savingSpons}
            className="text-xs px-3 py-2 rounded-lg bg-accent hover:bg-accent-hover disabled:opacity-50 text-white btn-press">
            {savingSpons ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>

      {/* Rounds */}
      <div>
        <div className="text-xs font-semibold text-text-secondary mb-2">Rounds</div>
        {detail.rounds.length === 0 ? (
          <p className="text-xs text-text-muted mb-2">No rounds yet.</p>
        ) : (
          <div className="space-y-2 mb-3">
            {detail.rounds.map((r, i) => <RoundRow key={r.id} round={r} index={i} onReload={onReload} />)}
          </div>
        )}
        <AddRoundForm interviewId={detail.id} nextSeq={detail.rounds.length + 1} onReload={onReload} />
      </div>

      {/* Interview notes + delete */}
      <div className="flex items-center justify-between gap-2 pt-1">
        {detail.notes ? <span className="text-xs text-text-tertiary">{detail.notes}</span> : <span />}
        <button onClick={() => onDelete(detail.id)} className="text-xs text-red-400/80 hover:text-red-400 hover:underline">
          Delete interview
        </button>
      </div>
    </div>
  )
}

function RoundRow({ round, index, onReload }) {
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState(round)

  useEffect(() => { setForm(round) }, [round])

  const save = async () => {
    const { id, interview_id, reminder_id, created_at, updated_at, ...payload } = form
    await api.updateRound(round.id, payload)
    setEditing(false)
    onReload()
  }
  const setStatus = async (status) => { await api.updateRound(round.id, { status }); onReload() }
  const remove = async () => { if (confirm('Delete this round?')) { await api.deleteRound(round.id); onReload() } }

  const roundStatusColor = (s) => ({
    passed: 'text-emerald-400', completed: 'text-sky-400', failed: 'text-red-400',
    cancelled: 'text-text-muted', scheduled: 'text-amber-400', pending: 'text-text-tertiary',
  }[s] || 'text-text-tertiary')

  if (editing) {
    return (
      <div className="bg-surface border border-accent/30 rounded-lg p-3 space-y-2">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <input placeholder="Round name (e.g. Tech Screen)" value={form.name || ''} onChange={e => setForm({ ...form, name: e.target.value })} className={inputClass} />
          <select value={form.type} onChange={e => setForm({ ...form, type: e.target.value })} className={inputClass}>
            {ROUND_TYPES.map(t => <option key={t} value={t}>{t.replace('_', ' ')}</option>)}
          </select>
          <div className="flex gap-2">
            <input type="date" value={toLocalInput(form.scheduled_at).slice(0, 10)} onChange={e => setForm({ ...form, scheduled_at: e.target.value + 'T' + (toLocalInput(form.scheduled_at).slice(11) || '09:00') })} className={`flex-1 ${inputClass}`} />
            <TimeSelect value={toLocalInput(form.scheduled_at).slice(11) || '09:00'} onChange={e => setForm({ ...form, scheduled_at: (toLocalInput(form.scheduled_at).slice(0, 10) || new Date().toISOString().slice(0, 10)) + 'T' + e.target.value })} className={inputClass + ' cursor-pointer'} />
          </div>
          <select value={form.status} onChange={e => setForm({ ...form, status: e.target.value })} className={inputClass}>
            {ROUND_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <input placeholder="Interviewer" value={form.interviewer || ''} onChange={e => setForm({ ...form, interviewer: e.target.value })} className={inputClass} />
          <input placeholder="Interviewer role" value={form.interviewer_role || ''} onChange={e => setForm({ ...form, interviewer_role: e.target.value })} className={inputClass} />
          <input placeholder="Interviewer LinkedIn" value={form.interviewer_linkedin || ''} onChange={e => setForm({ ...form, interviewer_linkedin: e.target.value })} className={inputClass} />
          <input placeholder="Meeting link / location" value={form.meeting_link || ''} onChange={e => setForm({ ...form, meeting_link: e.target.value })} className={inputClass} />
          <input placeholder="Outcome" value={form.outcome || ''} onChange={e => setForm({ ...form, outcome: e.target.value })} className={`sm:col-span-2 ${inputClass}`} />
          <textarea placeholder="Notes" value={form.notes || ''} onChange={e => setForm({ ...form, notes: e.target.value })} rows={2} className={`sm:col-span-2 ${inputClass}`} />
        </div>
        <div className="flex gap-2">
          <button onClick={save} className="text-xs px-3 py-1.5 rounded-lg bg-accent hover:bg-accent-hover text-white btn-press">Save</button>
          <button onClick={() => { setEditing(false); setForm(round) }} className="text-xs px-3 py-1.5 rounded-lg bg-surface-overlay text-text-secondary border border-border">Cancel</button>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-surface border border-border rounded-lg p-2.5">
      <div className="flex items-start justify-between gap-2 flex-wrap">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[11px] text-text-muted w-5 shrink-0">#{round.seq || index + 1}</span>
            <span className="text-sm font-medium text-text-primary">{round.name || 'Round'}</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface-overlay text-text-muted border border-border">{(round.type || '').replace('_', ' ')}</span>
          </div>
          <div className="flex items-center gap-3 mt-1 text-xs text-text-muted flex-wrap pl-7">
            {round.scheduled_at && <span>{'📅'} {fmtDate(round.scheduled_at)}</span>}
            {round.interviewer && (
              <span>{round.interviewer}{round.interviewer_role && `, ${round.interviewer_role}`}</span>
            )}
            {round.interviewer_linkedin && (
              <a href={round.interviewer_linkedin.startsWith('http') ? round.interviewer_linkedin : `https://${round.interviewer_linkedin}`}
                target="_blank" rel="noopener noreferrer" className="text-sky-400 hover:underline">LinkedIn {'↗'}</a>
            )}
            {round.meeting_link && (
              <a href={round.meeting_link.startsWith('http') ? round.meeting_link : `https://${round.meeting_link}`}
                target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">Link {'↗'}</a>
            )}
            {round.reminder_id && <span className="text-amber-400/70">{'🔔'} reminder</span>}
          </div>
          {round.outcome && <div className="text-xs text-text-tertiary mt-1 pl-7">Outcome: {round.outcome}</div>}
          {round.notes && <div className="text-xs text-text-muted mt-1 pl-7">{round.notes}</div>}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <select value={round.status} onChange={e => setStatus(e.target.value)}
            className={`bg-surface border border-border rounded-md text-xs px-2 py-1 outline-none cursor-pointer ${roundStatusColor(round.status)}`}>
            {ROUND_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <button onClick={() => setEditing(true)} className="text-xs text-accent hover:underline">Edit</button>
          <button onClick={remove} className="text-xs text-red-400/70 hover:text-red-400">{'×'}</button>
        </div>
      </div>
    </div>
  )
}

function AddRoundForm({ interviewId, nextSeq, onReload }) {
  const blank = { name: '', type: 'video', scheduled_at: '', interviewer: '', meeting_link: '', notes: '', create_reminder: true }
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState(blank)
  const [staged, setStaged] = useState([])   // rounds queued to save together
  const [saving, setSaving] = useState(false)

  const isFilled = (r) => Boolean((r.name && r.name.trim()) || r.scheduled_at)
  const reset = () => { setForm(blank); setStaged([]) }

  // Push the current entry onto the queue and start a fresh one.
  const stageCurrent = () => {
    if (!isFilled(form)) return
    setStaged(prev => [...prev, form])
    setForm({ ...blank, create_reminder: form.create_reminder })
  }
  const removeStaged = (i) => setStaged(prev => prev.filter((_, idx) => idx !== i))

  const saveAll = async (e) => {
    e.preventDefault()
    const all = [...staged]
    if (isFilled(form)) all.push(form)
    if (all.length === 0) return
    setSaving(true)
    try {
      for (let i = 0; i < all.length; i++) {
        await api.addRound(interviewId, { ...all[i], seq: nextSeq + i })
      }
      reset()
      setOpen(false)
      onReload()  // single refresh after all rounds are saved
    } finally { setSaving(false) }
  }

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className="text-xs px-2.5 py-1 rounded-md bg-surface-overlay hover:bg-border text-text-secondary border border-border btn-press">
        + Add round(s)
      </button>
    )
  }

  const total = staged.length + (isFilled(form) ? 1 : 0)

  return (
    <form onSubmit={saveAll} className="bg-surface border border-border rounded-lg p-3 space-y-2">
      {staged.length > 0 && (
        <div className="space-y-1">
          {staged.map((r, i) => (
            <div key={i} className="flex items-center justify-between text-xs bg-surface-overlay border border-border rounded-md px-2 py-1">
              <span className="text-text-secondary truncate">
                #{nextSeq + i} · {r.name || 'Round'} · {r.type.replace('_', ' ')}{r.scheduled_at ? ` · ${fmtDate(r.scheduled_at)}` : ''}
              </span>
              <button type="button" onClick={() => removeStaged(i)} className="text-red-400/70 hover:text-red-400 shrink-0 ml-2" title="Remove">×</button>
            </div>
          ))}
        </div>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <input placeholder="Round name (e.g. Recruiter Screen)" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} className={inputClass} />
        <select value={form.type} onChange={e => setForm({ ...form, type: e.target.value })} className={inputClass}>
          {ROUND_TYPES.map(t => <option key={t} value={t}>{t.replace('_', ' ')}</option>)}
        </select>
        <div className="flex gap-2 sm:col-span-2">
          <input type="date" value={(form.scheduled_at || '').slice(0, 10)} onChange={e => setForm({ ...form, scheduled_at: e.target.value + 'T' + ((form.scheduled_at || '').slice(11) || '09:00') })} className={`flex-1 ${inputClass}`} />
          <TimeSelect value={(form.scheduled_at || '').slice(11) || '09:00'} onChange={e => setForm({ ...form, scheduled_at: ((form.scheduled_at || new Date().toISOString()).slice(0, 10)) + 'T' + e.target.value })} className={inputClass + ' cursor-pointer'} />
        </div>
        <input placeholder="Interviewer" value={form.interviewer} onChange={e => setForm({ ...form, interviewer: e.target.value })} className={inputClass} />
        <input placeholder="Meeting link / location" value={form.meeting_link} onChange={e => setForm({ ...form, meeting_link: e.target.value })} className={`sm:col-span-2 ${inputClass}`} />
        <textarea placeholder="Notes" value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} rows={2} className={`sm:col-span-2 ${inputClass}`} />
      </div>
      <label className="flex items-center gap-2 text-xs text-text-tertiary cursor-pointer">
        <input type="checkbox" checked={form.create_reminder} onChange={e => setForm({ ...form, create_reminder: e.target.checked })} />
        Remind me (adds to the notification bell when a date is set)
      </label>
      <div className="flex gap-2 flex-wrap">
        <button type="button" onClick={stageCurrent} disabled={!isFilled(form)}
          className="text-xs px-3 py-1.5 rounded-lg bg-surface-overlay hover:bg-border disabled:opacity-40 text-text-secondary border border-border btn-press">
          + Add another
        </button>
        <button type="submit" disabled={saving || total === 0}
          className="text-xs px-3 py-1.5 rounded-lg bg-accent hover:bg-accent-hover disabled:opacity-50 text-white btn-press">
          {saving ? 'Saving...' : `Save ${total} round${total === 1 ? '' : 's'}`}
        </button>
        <button type="button" onClick={() => { reset(); setOpen(false) }} className="text-xs px-3 py-1.5 rounded-lg bg-surface-overlay text-text-secondary border border-border">Cancel</button>
      </div>
    </form>
  )
}

function AddInterviewForm({ onDone }) {
  const [mode, setMode] = useState('external') // external | application | queue
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    company: '', role: '', location: '', contact_name: '', contact_role: '',
    contact_email: '', contact_linkedin: '', apply_link: '', salary_min: '', salary_max: '',
    sponsorship_status: 'not_discussed', notes: '',
  })
  // pickers
  const [apps, setApps] = useState([])
  const [jobs, setJobs] = useState([])
  const [pickSearch, setPickSearch] = useState('')
  const [selectedId, setSelectedId] = useState(null)
  // URL prefill (external mode)
  const [url, setUrl] = useState('')
  const [urlLoading, setUrlLoading] = useState(false)
  const [urlMsg, setUrlMsg] = useState('')

  const prefillFromUrl = async () => {
    if (!url.trim()) return
    setUrlLoading(true)
    setUrlMsg('')
    try {
      const f = await api.fetchInterviewUrl(url.trim())
      setForm(prev => ({
        ...prev,
        company: f.company || prev.company,
        role: f.role || prev.role,
        location: f.location || prev.location,
        apply_link: f.apply_link || url.trim(),
      }))
      setUrlMsg(f.company || f.role ? 'Prefilled — review and edit below.' : 'Could not extract much; fill manually.')
    } catch (e) {
      setUrlMsg(e.message || 'Failed to fetch from URL')
    } finally {
      setUrlLoading(false)
    }
  }

  useEffect(() => {
    if (mode === 'application' && apps.length === 0) {
      api.getApplications().then(setApps).catch(() => {})
    }
    if (mode === 'queue' && jobs.length === 0) {
      api.getJobs({ limit: 200 }).then(res => setJobs(res.jobs || [])).catch(() => {})
    }
    setSelectedId(null)
  }, [mode]) // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      let payload
      if (mode === 'application' && selectedId) {
        payload = { application_id: selectedId, sponsorship_status: form.sponsorship_status, notes: form.notes }
      } else if (mode === 'queue' && selectedId) {
        payload = { job_id: selectedId, sponsorship_status: form.sponsorship_status, notes: form.notes }
      } else {
        payload = { ...form }
        payload.salary_min = form.salary_min ? parseInt(form.salary_min) : null
        payload.salary_max = form.salary_max ? parseInt(form.salary_max) : null
      }
      await api.createInterview(payload)
      onDone()
    } catch (err) {
      alert(err.message || 'Failed to create interview')
    } finally { setSaving(false) }
  }

  const filteredApps = apps.filter(a => !pickSearch || `${a.company} ${a.title}`.toLowerCase().includes(pickSearch.toLowerCase()))
  const filteredJobs = jobs.filter(j => !pickSearch || `${j.company} ${j.title}`.toLowerCase().includes(pickSearch.toLowerCase()))

  // Render-function (not a nested component) so the filter input keeps focus across keystrokes.
  const renderPicker = (items, render) => (
    <div>
      <input placeholder="Filter..." value={pickSearch} onChange={e => setPickSearch(e.target.value)} className={`w-full mb-2 ${inputClass}`} />
      <div className="max-h-52 overflow-y-auto space-y-1 border border-border rounded-lg p-1.5">
        {items.length === 0 && <p className="text-xs text-text-muted p-2">Nothing to pick.</p>}
        {items.slice(0, 100).map(it => (
          <button type="button" key={it.id} onClick={() => setSelectedId(it.id)}
            className={`w-full text-left px-2.5 py-1.5 rounded-md text-xs transition-all ${selectedId === it.id ? 'bg-accent/15 text-accent border border-accent/30' : 'text-text-secondary hover:bg-surface-overlay border border-transparent'}`}>
            {render(it)}
          </button>
        ))}
      </div>
    </div>
  )

  return (
    <div className="bg-surface-raised border border-border rounded-xl p-4 sm:p-5 mb-5 animate-scale-in space-y-4">
      <div className="flex gap-1.5">
        {[['external', 'External / Manual'], ['application', 'From Application'], ['queue', 'From Job Queue']].map(([m, label]) => (
          <button key={m} onClick={() => setMode(m)}
            className={`text-xs px-3 py-1.5 rounded-lg border transition-all ${mode === m ? 'bg-accent/15 text-accent border-accent/30' : 'bg-surface-overlay text-text-tertiary border-border hover:text-text-secondary'}`}>
            {label}
          </button>
        ))}
      </div>

      <form onSubmit={submit} className="space-y-3">
        {mode === 'application' && renderPicker(filteredApps, a => <><span className="font-medium">{a.company}</span> — {a.title} <span className="text-text-muted">({a.status})</span></>)}
        {mode === 'queue' && renderPicker(filteredJobs, j => <><span className="font-medium">{j.company}</span> — {j.title}</>)}
        {mode === 'external' && (
          <>
          <div className="flex gap-2 items-start">
            <input
              placeholder="Paste a job URL to prefill..."
              value={url}
              onChange={e => setUrl(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); prefillFromUrl() } }}
              className={`flex-1 ${inputClass}`}
              disabled={urlLoading}
            />
            <button type="button" onClick={prefillFromUrl} disabled={urlLoading || !url.trim()}
              className="text-xs px-3 py-2 rounded-lg bg-surface-overlay hover:bg-border disabled:opacity-50 text-text-secondary border border-border btn-press whitespace-nowrap">
              {urlLoading ? 'Fetching...' : 'Prefill'}
            </button>
          </div>
          {urlMsg && <p className="text-xs text-text-muted -mt-1">{urlMsg}</p>}
          <div className="flex items-center gap-3 text-text-muted text-xs">
            <div className="flex-1 border-t border-border" />
            <span>or fill manually</span>
            <div className="flex-1 border-t border-border" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <input placeholder="Company *" required value={form.company} onChange={e => setForm({ ...form, company: e.target.value })} className={inputClass} />
            <input placeholder="Role" value={form.role} onChange={e => setForm({ ...form, role: e.target.value })} className={inputClass} />
            <input placeholder="Location" value={form.location} onChange={e => setForm({ ...form, location: e.target.value })} className={inputClass} />
            <input placeholder="Apply / job link" value={form.apply_link} onChange={e => setForm({ ...form, apply_link: e.target.value })} className={inputClass} />
            <input placeholder="Contact name" value={form.contact_name} onChange={e => setForm({ ...form, contact_name: e.target.value })} className={inputClass} />
            <input placeholder="Contact role (recruiter, HM...)" value={form.contact_role} onChange={e => setForm({ ...form, contact_role: e.target.value })} className={inputClass} />
            <input placeholder="Contact email" value={form.contact_email} onChange={e => setForm({ ...form, contact_email: e.target.value })} className={inputClass} />
            <input placeholder="Contact LinkedIn" value={form.contact_linkedin} onChange={e => setForm({ ...form, contact_linkedin: e.target.value })} className={inputClass} />
            <input placeholder="Salary min" type="number" value={form.salary_min} onChange={e => setForm({ ...form, salary_min: e.target.value })} className={inputClass} />
            <input placeholder="Salary max" type="number" value={form.salary_max} onChange={e => setForm({ ...form, salary_max: e.target.value })} className={inputClass} />
          </div>
          </>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <select value={form.sponsorship_status} onChange={e => setForm({ ...form, sponsorship_status: e.target.value })} className={inputClass}>
            {SPONSORSHIP.map(s => <option key={s.value} value={s.value}>Sponsorship: {s.label}</option>)}
          </select>
          <input placeholder="Notes" value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} className={inputClass} />
        </div>

        <button type="submit" disabled={saving || (mode !== 'external' && !selectedId)}
          className="w-full bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-medium text-sm py-2.5 rounded-lg transition-all duration-200 btn-press">
          {saving ? 'Saving...' : 'Add Interview'}
        </button>
      </form>
    </div>
  )
}
