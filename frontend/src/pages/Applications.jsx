import { useState, useEffect, useCallback } from 'react'
import { api } from '../api'
import LinkedInIdEditor from '../components/LinkedInIdEditor'

const STATUSES = ['applied', 'interview', 'offer', 'rejected', 'withdrawn', 'ghosted']

export default function Applications() {
  const [apps, setApps] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState(null)
  const [emailResults, setEmailResults] = useState(null)
  const [emailLoading, setEmailLoading] = useState(null)
  const [outreach, setOutreach] = useState(null)   // { appId, full, short }
  const [outreachLoading, setOutreachLoading] = useState(null)
  const [copied, setCopied] = useState(null)
  const [form, setForm] = useState({ title: '', company: '', location: '', apply_link: '', source: 'manual', notes: '', salary_min: '', salary_max: '' })
  const [urlInput, setUrlInput] = useState('')
  const [urlLoading, setUrlLoading] = useState(false)
  const [search, setSearch] = useState('')
  const [searchDebounced, setSearchDebounced] = useState('')

  useEffect(() => {
    const t = setTimeout(() => setSearchDebounced(search), 300)
    return () => clearTimeout(t)
  }, [search])

  const load = useCallback(() => {
    setLoading(true)
    const params = {}
    if (searchDebounced.trim()) params.search = searchDebounced.trim()
    api.getApplications(params).then(setApps).finally(() => setLoading(false))
  }, [searchDebounced])
  useEffect(() => { load() }, [load])

  const handleSubmit = async (e) => {
    e.preventDefault()
    const data = { ...form }
    if (data.salary_min) data.salary_min = parseInt(data.salary_min)
    else delete data.salary_min
    if (data.salary_max) data.salary_max = parseInt(data.salary_max)
    else delete data.salary_max
    await api.createApplication(data)
    setForm({ title: '', company: '', location: '', apply_link: '', source: 'manual', notes: '', salary_min: '', salary_max: '' })
    setShowForm(false)
    load()
  }

  const handleUrlAdd = async (e) => {
    e.preventDefault()
    if (!urlInput.trim()) return
    setUrlLoading(true)
    try {
      await api.addApplicationByUrl(urlInput.trim())
      setUrlInput('')
      setShowForm(false)
      load()
    } catch (err) {
      alert(err.message || 'Failed to fetch job from URL')
    } finally {
      setUrlLoading(false)
    }
  }

  const updateStatus = async (id, status) => {
    await api.updateApplication(id, { status })
    load()
  }

  const saveNotes = async (id, notes) => {
    await api.updateApplication(id, { notes })
    setEditing(null)
    load()
  }

  const handleLinkedInRecruiter = async (app) => {
    if (app.job_id) {
      try {
        const result = await api.linkedinSearch(app.job_id)
        window.open(result.url, '_blank')
        return
      } catch (_) { /* fall through to basic search */ }
    }
    const query = `${app.company} technical recruiter OR "talent acquisition"`
    window.open(`https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(query)}&geoUrn=%5B%22103644278%22%5D&origin=FACETED_SEARCH`, '_blank')
  }

  const handleLinkedInManager = async (app) => {
    if (app.job_id) {
      try {
        const result = await api.linkedinLeaders(app.job_id, 'hiring')
        window.open(result.url, '_blank')
        return
      } catch (_) { /* fall through to basic search */ }
    }
    const query = `${app.company} engineering manager`
    window.open(`https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(query)}&geoUrn=%5B%22103644278%22%5D&origin=FACETED_SEARCH`, '_blank')
  }

  const handleFindEmails = async (app) => {
    if (!app.job_id) {
      alert('No linked job — emails require a job with company info')
      return
    }
    setEmailLoading(app.id)
    setEmailResults(null)
    try {
      const result = await api.findEmails(app.job_id)
      setEmailResults({ ...result, appId: app.id })
    } catch (e) {
      alert(e.message)
    } finally {
      setEmailLoading(null)
    }
  }

  const handleOutreach = async (app) => {
    if (!app.job_id) {
      alert('No linked job — outreach requires a matched job')
      return
    }
    setOutreachLoading(app.id)
    try {
      const result = await api.generateOutreach(app.job_id, {})
      setOutreach({ appId: app.id, full: result.full, short: result.short })
    } catch (e) {
      alert(e.message)
    } finally {
      setOutreachLoading(null)
    }
  }

  const handleCopy = (text, label) => {
    navigator.clipboard.writeText(text)
    setCopied(label)
    setTimeout(() => setCopied(null), 2000)
  }

  const inputClass = "bg-surface border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:border-accent/50 outline-none transition-all duration-200"

  return (
    <div className="animate-fade-in">
      <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
        <h1 className="text-xl font-semibold text-text-primary">Applications</h1>
        <button
          onClick={() => setShowForm(!showForm)}
          className="bg-accent hover:bg-accent-hover text-white font-medium text-sm px-4 py-2 rounded-lg transition-all duration-200 btn-press"
        >
          {showForm ? 'Cancel' : '+ Add Application'}
        </button>
      </div>

      <div className="relative mb-4 animate-fade-in-up" style={{ animationDelay: '50ms' }}>
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search by role or company..."
          className="w-full bg-surface border border-border rounded-lg px-3 py-2 pl-9 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent/40 focus:ring-1 focus:ring-accent/20 transition-all duration-200"
        />
        <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        {search && (
          <button onClick={() => setSearch('')} className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary text-xs transition-colors">
            Clear
          </button>
        )}
      </div>

      {showForm && (
        <div className="bg-surface-raised border border-border rounded-xl p-4 sm:p-5 mb-5 animate-scale-in space-y-4">
          <form onSubmit={handleUrlAdd} className="flex gap-2">
            <input
              placeholder="Paste job URL to auto-fill..."
              value={urlInput}
              onChange={e => setUrlInput(e.target.value)}
              className={`flex-1 ${inputClass}`}
              disabled={urlLoading}
            />
            <button
              type="submit"
              disabled={urlLoading || !urlInput.trim()}
              className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-medium text-sm px-4 py-2 rounded-lg transition-all duration-200 btn-press whitespace-nowrap"
            >
              {urlLoading ? 'Fetching...' : 'Add from URL'}
            </button>
          </form>

          <div className="flex items-center gap-3 text-text-muted text-xs">
            <div className="flex-1 border-t border-border" />
            <span>or fill manually</span>
            <div className="flex-1 border-t border-border" />
          </div>

          <form onSubmit={handleSubmit} className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <input placeholder="Job Title *" required value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} className={inputClass} />
            <input placeholder="Company *" required value={form.company} onChange={e => setForm({ ...form, company: e.target.value })} className={inputClass} />
            <input placeholder="Location" value={form.location} onChange={e => setForm({ ...form, location: e.target.value })} className={inputClass} />
            <input placeholder="Apply Link" value={form.apply_link} onChange={e => setForm({ ...form, apply_link: e.target.value })} className={inputClass} />
            <input placeholder="Salary Min" type="number" value={form.salary_min} onChange={e => setForm({ ...form, salary_min: e.target.value })} className={inputClass} />
            <input placeholder="Salary Max" type="number" value={form.salary_max} onChange={e => setForm({ ...form, salary_max: e.target.value })} className={inputClass} />
            <textarea placeholder="Notes" value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} className={`sm:col-span-2 ${inputClass}`} rows={2} />
            <button type="submit" className="sm:col-span-2 bg-accent hover:bg-accent-hover text-white font-medium text-sm py-2.5 rounded-lg transition-all duration-200 btn-press">
              Save Application
            </button>
          </form>
        </div>
      )}

      {loading ? (
        <div className="space-y-2 animate-pulse">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="bg-surface-raised border border-border rounded-lg p-3.5 animate-shimmer">
              <div className="h-4 bg-surface-overlay rounded w-3/4 mb-2" />
              <div className="h-3 bg-surface-overlay rounded w-1/2" />
            </div>
          ))}
        </div>
      ) : apps.length === 0 ? (
        <div className="text-center py-12 animate-fade-in-up">
          <div className="text-3xl mb-3 opacity-30">&#128196;</div>
          <p className="text-text-muted">No applications yet. Apply to jobs from the queue or add manually.</p>
        </div>
      ) : (
        <div className="space-y-1.5 stagger-children">
          {apps.map(app => (
            <div key={app.id} className="bg-surface-raised border border-border rounded-lg p-3.5 transition-all duration-200 hover:border-border-hover hover:shadow-md hover:shadow-black/20">
              <div className="flex items-start justify-between gap-2 flex-wrap sm:flex-nowrap">
                <div className="min-w-0 flex-1">
                  <div className="font-medium text-text-primary text-sm">{app.title}</div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm text-text-tertiary">{app.company} {app.location && `· ${app.location}`}</span>
                    <LinkedInIdEditor company={app.company} compact />
                  </div>
                </div>
                <select
                  value={app.status}
                  onChange={e => updateStatus(app.id, e.target.value)}
                  className="bg-surface border border-border rounded-md text-xs text-text-primary px-2 py-1 outline-none cursor-pointer transition-colors"
                >
                  {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div className="flex items-center gap-2 sm:gap-3 mt-2 text-xs text-text-muted flex-wrap">
                <span>Applied: {new Date(app.applied_at).toLocaleDateString()}</span>
                <span>Source: {app.source}</span>
                {app.salary_min && <span>Salary: ${app.salary_min.toLocaleString()}{app.salary_max ? ` - $${app.salary_max.toLocaleString()}` : '+'}</span>}
                {app.resume_used && <span className="text-accent/70">Resume: {app.resume_used}</span>}
                {app.email_used && <span className="text-sky-400/70">Email: {app.email_used.split('@')[0]}</span>}
                {app.apply_link && (
                  <a href={app.apply_link} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">Link</a>
                )}
                {app.job_contact_linkedin && (
                  <a href={app.job_contact_linkedin.startsWith('http') ? app.job_contact_linkedin : `https://${app.job_contact_linkedin}`}
                    target="_blank" rel="noopener noreferrer" className="text-sky-400 hover:underline">Contact ↗</a>
                )}
              </div>
              <div className="flex gap-1.5 mt-2 flex-wrap">
                <button
                  onClick={() => handleLinkedInRecruiter(app)}
                  className="text-xs px-2.5 py-1 rounded-md bg-surface-overlay hover:bg-border text-text-secondary border border-border transition-all duration-200 btn-press"
                >
                  Find Recruiters
                </button>
                <button
                  onClick={() => handleLinkedInManager(app)}
                  className="text-xs px-2.5 py-1 rounded-md bg-surface-overlay hover:bg-border text-text-secondary border border-border transition-all duration-200 btn-press"
                >
                  Hiring Manager
                </button>
                <button
                  onClick={() => handleFindEmails(app)}
                  disabled={emailLoading === app.id}
                  className="text-xs px-2.5 py-1 rounded-md bg-surface-overlay hover:bg-border disabled:opacity-50 text-text-secondary border border-border transition-all duration-200 btn-press"
                >
                  {emailLoading === app.id ? 'Finding...' : 'Find Emails'}
                </button>
                {app.job_id && (
                  <button
                    onClick={() => handleOutreach(app)}
                    disabled={outreachLoading === app.id}
                    className="text-xs px-2.5 py-1 rounded-md bg-purple-900/10 hover:bg-purple-900/20 disabled:opacity-50 text-purple-400 border border-purple-500/15 transition-all duration-200 btn-press"
                  >
                    {outreachLoading === app.id ? 'Generating...' : 'Outreach'}
                  </button>
                )}
              </div>
              {outreach && outreach.appId === app.id && (
                <div className="bg-purple-900/10 border border-purple-500/20 rounded-lg p-3 mt-2 animate-scale-in">
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-xs font-medium text-purple-400">Outreach Messages</span>
                    <button onClick={() => setOutreach(null)} className="text-text-muted hover:text-text-tertiary text-xs transition-colors">x</button>
                  </div>
                  <div className="mb-2">
                    <div className="flex justify-between items-center mb-1">
                      <span className="text-[11px] text-text-muted">Full Version</span>
                      <button onClick={() => handleCopy(outreach.full, `full-${app.id}`)}
                        className="text-[11px] px-1.5 py-0.5 rounded bg-purple-900/30 text-purple-400 hover:bg-purple-900/50 transition-all btn-press">
                        {copied === `full-${app.id}` ? 'Copied!' : 'Copy'}
                      </button>
                    </div>
                    <p className="text-xs text-text-secondary leading-relaxed bg-surface rounded-md p-2.5 border border-border whitespace-pre-wrap">{outreach.full}</p>
                  </div>
                  <div>
                    <div className="flex justify-between items-center mb-1">
                      <span className="text-[11px] text-text-muted">Short Version <span className="text-text-muted">({outreach.short.length} chars)</span></span>
                      <button onClick={() => handleCopy(outreach.short, `short-${app.id}`)}
                        className="text-[11px] px-1.5 py-0.5 rounded bg-purple-900/30 text-purple-400 hover:bg-purple-900/50 transition-all btn-press">
                        {copied === `short-${app.id}` ? 'Copied!' : 'Copy'}
                      </button>
                    </div>
                    <p className="text-xs text-text-secondary leading-relaxed bg-surface rounded-md p-2.5 border border-border whitespace-pre-wrap">{outreach.short}</p>
                  </div>
                </div>
              )}
              {emailResults && emailResults.appId === app.id && (
                <div className="bg-surface border border-border rounded-lg p-3 mt-2 animate-scale-in">
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-xs font-medium text-text-secondary">Emails — {emailResults.company}</span>
                    <button onClick={() => setEmailResults(null)} className="text-text-muted hover:text-text-tertiary text-xs transition-colors">x</button>
                  </div>
                  {emailResults.pattern && (
                    <p className="text-xs text-text-muted mb-2">Pattern: <span className="text-accent">{emailResults.pattern}</span></p>
                  )}
                  {emailResults.people.length > 0 ? (
                    <div className="space-y-1.5 max-h-36 overflow-y-auto">
                      {emailResults.people.map((p, i) => (
                        <div key={i} className="text-xs border-t border-border/30 pt-1">
                          <span className="text-text-primary font-medium">{p.first_name} {p.last_name}</span>
                          {p.position && <span className="text-text-muted ml-2">{p.position}</span>}
                          <div><a href={`mailto:${p.email}`} className="text-accent hover:underline">{p.email}</a></div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-text-muted">No emails found.</p>
                  )}
                </div>
              )}
              {editing === app.id ? (
                <div className="mt-2 animate-fade-in">
                  <textarea
                    defaultValue={app.notes}
                    className={`w-full ${inputClass}`}
                    rows={2}
                    onKeyDown={e => { if (e.key === 'Enter' && e.ctrlKey) saveNotes(app.id, e.target.value) }}
                  />
                  <div className="text-xs text-text-muted mt-1">Ctrl+Enter to save</div>
                </div>
              ) : (
                <div className="mt-2 flex items-center gap-2">
                  {app.notes && <span className="text-xs text-text-tertiary">{app.notes}</span>}
                  <button onClick={() => setEditing(app.id)} className="text-xs text-accent hover:underline transition-colors">
                    {app.notes ? 'Edit notes' : 'Add notes'}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
