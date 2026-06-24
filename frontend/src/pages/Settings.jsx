import { useState, useEffect } from 'react'
import { api } from '../api'

const SOURCE_OPTIONS = [
  { value: 'simplify', label: 'Simplify' },
  { value: 'ats', label: 'ATS (Greenhouse, Lever, etc.)' },
  { value: 'jsearch', label: 'JSearch' },
  { value: 'adzuna', label: 'Adzuna' },
  { value: 'sponsors', label: 'H-1B Sponsors' },
]

const HOUR_OPTIONS = Array.from({ length: 24 }, (_, i) => ({
  value: i,
  label: i === 0 ? '12 AM' : i < 12 ? `${i} AM` : i === 12 ? '12 PM' : `${i - 12} PM`,
}))

export default function Settings() {
  const [blocked, setBlocked] = useState([])
  const [loading, setLoading] = useState(true)
  const [schedules, setSchedules] = useState([])
  const [schedLoading, setSchedLoading] = useState(true)
  const [showSchedForm, setShowSchedForm] = useState(false)
  const [schedForm, setSchedForm] = useState({ name: '', hours: [9], sources: ['simplify'] })

  const [backup, setBackup] = useState(null)
  const [backupBusy, setBackupBusy] = useState(false)
  const [backupMsg, setBackupMsg] = useState(null) // { ok, text }
  const [syncing, setSyncing] = useState(false)

  const syncDb = async () => {
    setSyncing(true)
    try {
      await api.syncDb()
      setBackupMsg({ ok: true, text: 'DB synced to Backblaze B2.' })
    } catch (e) {
      setBackupMsg({ ok: false, text: 'Sync failed: ' + e.message })
    } finally {
      setSyncing(false)
    }
  }

  const stopServer = async () => {
    if (!confirm('Sync DB to B2 and shut down the server?')) return
    try { await api.shutdownServer() } catch (_) {}
  }

  const loadBackup = () => api.getBackupStatus().then(setBackup).catch(() => setBackup(null))

  const handleBackup = async () => {
    setBackupBusy(true)
    setBackupMsg(null)
    try {
      const res = await api.pushBackup()
      const text = res.status === 'pushed'
        ? 'New backup pushed to GitHub.'
        : res.status === 'committed_unpushed'
          ? `Committed locally, but ${res.unpushed} commit(s) not pushed — check the remote/network.`
          : 'Already up to date — no new data since the last backup.'
      setBackupMsg({ ok: res.status !== 'committed_unpushed', text })
      if (res.last_commit) setBackup(prev => ({ ...(prev || {}), last_commit: res.last_commit, unpushed: res.unpushed ?? 0 }))
      loadBackup()
    } catch (e) {
      setBackupMsg({ ok: false, text: e.message || 'Backup failed' })
    } finally {
      setBackupBusy(false)
    }
  }

  const loadBlocked = () => {
    setLoading(true)
    api.getBlockedCompanies().then(setBlocked).finally(() => setLoading(false))
  }

  const loadSchedules = () => {
    setSchedLoading(true)
    api.getScheduledDiscoveries().then(setSchedules).finally(() => setSchedLoading(false))
  }

  useEffect(() => { loadBlocked(); loadSchedules(); loadBackup() }, [])

  const handleUnblock = async (company) => {
    await api.unblockCompany(company)
    loadBlocked()
  }

  const handleCreateSchedule = async (e) => {
    e.preventDefault()
    if (!schedForm.name.trim() || schedForm.hours.length === 0 || schedForm.sources.length === 0) return
    await api.createScheduledDiscovery({
      name: schedForm.name.trim(),
      cron_hours: schedForm.hours.join(','),
      sources: schedForm.sources.join(','),
    })
    setSchedForm({ name: '', hours: [9], sources: ['simplify'] })
    setShowSchedForm(false)
    loadSchedules()
  }

  const toggleSchedule = async (sched) => {
    await api.updateScheduledDiscovery(sched.id, { enabled: !sched.enabled })
    loadSchedules()
  }

  const deleteSchedule = async (id) => {
    await api.deleteScheduledDiscovery(id)
    loadSchedules()
  }

  const toggleHour = (h) => {
    setSchedForm(prev => ({
      ...prev,
      hours: prev.hours.includes(h) ? prev.hours.filter(x => x !== h) : [...prev.hours, h].sort((a, b) => a - b),
    }))
  }

  const toggleSource = (s) => {
    setSchedForm(prev => ({
      ...prev,
      sources: prev.sources.includes(s) ? prev.sources.filter(x => x !== s) : [...prev.sources, s],
    }))
  }

  const formatHours = (hoursStr) => {
    return hoursStr.split(',').map(h => {
      const n = parseInt(h.trim())
      return n === 0 ? '12 AM' : n < 12 ? `${n} AM` : n === 12 ? '12 PM' : `${n - 12} PM`
    }).join(', ')
  }

  const inputClass = "bg-surface border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:border-accent/50 outline-none transition-colors duration-150"

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-text-primary">Settings</h1>

      {/* Database Backup */}
      <div className="bg-surface-raised border border-border rounded-xl p-5">
        <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
          <div>
            <h2 className="text-text-primary font-semibold">Database Backup</h2>
            <p className="text-text-tertiary text-xs mt-0.5">
              Manually push the database to your private GitHub backup repo.
            </p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={syncDb}
              disabled={syncing}
              className="text-xs px-2.5 py-2 rounded-lg bg-surface-overlay text-text-secondary border border-border hover:border-border-hover disabled:opacity-50 transition-all btn-press whitespace-nowrap"
              title="Push DB to Backblaze B2 now (legacy Litestream sync)"
            >
              {syncing ? 'Syncing…' : '↑ Sync to B2'}
            </button>
            <button
              onClick={stopServer}
              className="text-xs px-2.5 py-2 rounded-lg bg-red-900/15 text-danger border border-red-500/30 hover:bg-red-900/25 transition-all btn-press whitespace-nowrap"
              title="Checkpoint WAL, sync to B2, then stop the server"
            >
              ⏻ Stop Server
            </button>
            <button
              onClick={handleBackup}
              disabled={backupBusy || (backup && !backup.configured)}
              className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-medium text-sm px-4 py-2 rounded-lg transition-all duration-150 btn-press whitespace-nowrap"
            >
              {backupBusy ? 'Backing up…' : 'Back up now'}
            </button>
          </div>
        </div>

        {backup && !backup.configured && (
          <p className="text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2">
            Backup repo not configured. Set <code>BACKUP_GIT_DIR</code> in <code>.env</code> (see BACKUP.md).
          </p>
        )}

        {backup && backup.configured && (
          <div className="text-xs text-text-tertiary space-y-1">
            <div><span className="text-text-muted">Target:</span> {backup.targets} &middot; <span className="text-text-muted">Repo:</span> {backup.repo}</div>
            <div>
              <span className="text-text-muted">Last backup:</span>{' '}
              {backup.last_commit
                ? (() => {
                    const [hash, iso, ...rest] = backup.last_commit.split(' ')
                    const when = iso ? new Date(iso).toLocaleString() : ''
                    return <span className="text-text-secondary">{when} ({hash})</span>
                  })()
                : <span className="text-text-muted">none yet</span>}
            </div>
            {backup.has_remote === false && (
              <div className="text-amber-400">No git remote set — create the private repo and run <code>git -C {backup.repo} push -u origin main</code> once.</div>
            )}
            {backup.unpushed > 0 && backup.has_remote && (
              <div className="text-amber-400">{backup.unpushed} local backup commit(s) not yet pushed.</div>
            )}
          </div>
        )}

        {backupMsg && (
          <p className={`text-xs mt-2 ${backupMsg.ok ? 'text-emerald-400' : 'text-red-400'}`}>{backupMsg.text}</p>
        )}
      </div>

      {/* Scheduled Discoveries */}
      <div className="bg-surface-raised border border-border rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-text-primary font-semibold">Scheduled Discovery</h2>
            <p className="text-text-tertiary text-xs mt-0.5">Auto-fetch new jobs at specific times every day</p>
          </div>
          <button
            onClick={() => setShowSchedForm(!showSchedForm)}
            className="bg-accent hover:bg-accent-hover text-white font-medium text-sm px-4 py-2 rounded-lg transition-all duration-150"
          >
            {showSchedForm ? 'Cancel' : '+ Add Schedule'}
          </button>
        </div>

        {showSchedForm && (
          <form onSubmit={handleCreateSchedule} className="bg-surface border border-border rounded-lg p-4 mb-4 space-y-3">
            <input
              placeholder="Schedule name (e.g. Morning Simplify fetch)"
              required
              value={schedForm.name}
              onChange={e => setSchedForm({ ...schedForm, name: e.target.value })}
              className={`w-full ${inputClass}`}
            />

            <div>
              <label className="block text-xs text-text-muted mb-2">Sources</label>
              <div className="flex flex-wrap gap-2">
                {SOURCE_OPTIONS.map(s => (
                  <button
                    key={s.value}
                    type="button"
                    onClick={() => toggleSource(s.value)}
                    className={`text-xs px-3 py-1.5 rounded-md border transition-all ${
                      schedForm.sources.includes(s.value)
                        ? 'bg-accent/15 text-accent border-accent/30 font-medium'
                        : 'bg-surface-overlay text-text-muted border-border hover:border-border-hover'
                    }`}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-xs text-text-muted mb-2">Run at (select hours)</label>
              <div className="flex flex-wrap gap-1.5">
                {HOUR_OPTIONS.filter(h => h.value >= 6 && h.value <= 23).map(h => (
                  <button
                    key={h.value}
                    type="button"
                    onClick={() => toggleHour(h.value)}
                    className={`text-[11px] px-2 py-1 rounded-md border transition-all ${
                      schedForm.hours.includes(h.value)
                        ? 'bg-accent/15 text-accent border-accent/30 font-medium'
                        : 'bg-surface-overlay text-text-muted border-border hover:border-border-hover'
                    }`}
                  >
                    {h.label}
                  </button>
                ))}
              </div>
            </div>

            <button type="submit" className="w-full bg-accent hover:bg-accent-hover text-white font-medium text-sm py-2.5 rounded-lg transition-all duration-150">
              Save Schedule
            </button>
          </form>
        )}

        {schedLoading ? (
          <p className="text-text-muted text-sm animate-pulse">Loading...</p>
        ) : schedules.length === 0 ? (
          <p className="text-text-muted text-sm">No scheduled discoveries. Add one to auto-fetch jobs daily.</p>
        ) : (
          <div className="space-y-1.5">
            {schedules.map(s => (
              <div key={s.id} className={`bg-surface border rounded-lg px-4 py-3 transition-all ${s.enabled ? 'border-border' : 'border-border opacity-50'}`}>
                <div className="flex items-center justify-between">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className={`text-sm font-medium ${s.enabled ? 'text-text-primary' : 'text-text-muted line-through'}`}>{s.name}</span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${s.enabled ? 'bg-emerald-900/20 text-emerald-400' : 'bg-surface-overlay text-text-muted'}`}>
                        {s.enabled ? 'Active' : 'Paused'}
                      </span>
                    </div>
                    <div className="text-xs text-text-tertiary mt-0.5">
                      <span className="text-text-muted">Sources:</span> {s.sources.split(',').join(', ')} &middot;{' '}
                      <span className="text-text-muted">At:</span> {formatHours(s.cron_hours)}
                      {s.last_run && (
                        <span> &middot; <span className="text-text-muted">Last:</span> {new Date(s.last_run).toLocaleString()}</span>
                      )}
                    </div>
                  </div>
                  <div className="flex gap-1.5 shrink-0 ml-3">
                    <button
                      onClick={() => toggleSchedule(s)}
                      className="text-xs px-2 py-1 rounded-md bg-surface-overlay hover:bg-border text-text-muted hover:text-text-secondary border border-border transition-all"
                    >
                      {s.enabled ? 'Pause' : 'Enable'}
                    </button>
                    <button
                      onClick={() => deleteSchedule(s.id)}
                      className="text-xs px-2 py-1 rounded-md text-danger/60 hover:text-danger bg-red-900/10 transition-all"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Blocked Companies */}
      <div className="bg-surface-raised border border-border rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-text-primary font-semibold">Blocked Companies</h2>
            <p className="text-text-tertiary text-xs mt-0.5">Jobs from these companies are automatically skipped during discovery</p>
          </div>
          <span className="text-xs text-text-muted">{blocked.length} blocked</span>
        </div>

        {loading ? (
          <p className="text-text-muted text-sm animate-pulse">Loading...</p>
        ) : blocked.length === 0 ? (
          <p className="text-text-muted text-sm">No blocked companies. You can block companies from the Job Queue follow-up dialog.</p>
        ) : (
          <div className="space-y-1.5">
            {blocked.map(b => (
              <div key={b.company} className="flex items-center justify-between bg-surface border border-border rounded-lg px-4 py-2.5">
                <div className="min-w-0">
                  <span className="text-sm text-text-primary font-medium">{b.company}</span>
                  {b.reason && <span className="text-xs text-text-muted ml-2">— {b.reason}</span>}
                </div>
                <button
                  onClick={() => handleUnblock(b.company)}
                  className="text-xs text-accent hover:text-accent-hover transition-colors shrink-0 ml-3"
                >
                  Unblock
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
