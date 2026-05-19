import { useState, useEffect } from 'react'
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
  const [form, setForm] = useState({ title: '', company: '', location: '', apply_link: '', source: 'manual', notes: '', salary_min: '', salary_max: '' })

  const load = () => {
    setLoading(true)
    api.getApplications().then(setApps).finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])

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

  const updateStatus = async (id, status) => {
    await api.updateApplication(id, { status })
    load()
  }

  const saveNotes = async (id, notes) => {
    await api.updateApplication(id, { notes })
    setEditing(null)
    load()
  }

  const handleLinkedInRecruiter = (app) => {
    const query = `${app.company} software recruiter`
    const url = `https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(query)}&geoUrn=%5B%22103644278%22%5D&origin=FACETED_SEARCH`
    window.open(url, '_blank')
  }

  const handleLinkedInManager = (app) => {
    const query = `${app.company} engineering manager`
    const url = `https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(query)}&geoUrn=%5B%22103644278%22%5D&origin=FACETED_SEARCH`
    window.open(url, '_blank')
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

  const inputClass = "bg-surface border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:border-accent/50 outline-none transition-colors duration-150"

  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <h1 className="text-xl font-semibold text-text-primary">Applications</h1>
        <button
          onClick={() => setShowForm(!showForm)}
          className="bg-accent hover:bg-accent-hover text-white font-medium text-sm px-4 py-2 rounded-lg transition-all duration-150"
        >
          {showForm ? 'Cancel' : '+ Add Application'}
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleSubmit} className="bg-surface-raised border border-border rounded-xl p-5 mb-5 grid grid-cols-2 gap-3">
          <input placeholder="Job Title *" required value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} className={inputClass} />
          <input placeholder="Company *" required value={form.company} onChange={e => setForm({ ...form, company: e.target.value })} className={inputClass} />
          <input placeholder="Location" value={form.location} onChange={e => setForm({ ...form, location: e.target.value })} className={inputClass} />
          <input placeholder="Apply Link" value={form.apply_link} onChange={e => setForm({ ...form, apply_link: e.target.value })} className={inputClass} />
          <input placeholder="Salary Min" type="number" value={form.salary_min} onChange={e => setForm({ ...form, salary_min: e.target.value })} className={inputClass} />
          <input placeholder="Salary Max" type="number" value={form.salary_max} onChange={e => setForm({ ...form, salary_max: e.target.value })} className={inputClass} />
          <textarea placeholder="Notes" value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} className={`col-span-2 ${inputClass}`} rows={2} />
          <button type="submit" className="col-span-2 bg-accent hover:bg-accent-hover text-white font-medium text-sm py-2.5 rounded-lg transition-all duration-150">
            Save Application
          </button>
        </form>
      )}

      {loading ? (
        <p className="text-text-muted animate-pulse">Loading...</p>
      ) : apps.length === 0 ? (
        <p className="text-text-muted">No applications yet. Apply to jobs from the queue or add manually.</p>
      ) : (
        <div className="space-y-1.5">
          {apps.map(app => (
            <div key={app.id} className="bg-surface-raised border border-border rounded-lg p-3.5 transition-all duration-150 hover:border-border-hover">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="font-medium text-text-primary text-sm">{app.title}</div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-text-tertiary">{app.company} {app.location && `· ${app.location}`}</span>
                    <LinkedInIdEditor company={app.company} compact />
                  </div>
                </div>
                <select
                  value={app.status}
                  onChange={e => updateStatus(app.id, e.target.value)}
                  className="bg-surface border border-border rounded-md text-xs text-text-primary px-2 py-1 outline-none cursor-pointer"
                >
                  {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div className="flex items-center gap-3 mt-2 text-xs text-text-muted">
                <span>Applied: {new Date(app.applied_at).toLocaleDateString()}</span>
                <span>Source: {app.source}</span>
                {app.salary_min && <span>Salary: ${app.salary_min.toLocaleString()}{app.salary_max ? ` - $${app.salary_max.toLocaleString()}` : '+'}</span>}
                {app.resume_used && <span className="text-accent/70">Resume: {app.resume_used}</span>}
                {app.apply_link && (
                  <a href={app.apply_link} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">Link</a>
                )}
              </div>
              <div className="flex gap-1.5 mt-2 flex-wrap">
                <button
                  onClick={() => handleLinkedInRecruiter(app)}
                  className="text-xs px-2.5 py-1 rounded-md bg-surface-overlay hover:bg-border text-text-secondary border border-border transition-all"
                >
                  Find Recruiters
                </button>
                <button
                  onClick={() => handleLinkedInManager(app)}
                  className="text-xs px-2.5 py-1 rounded-md bg-surface-overlay hover:bg-border text-text-secondary border border-border transition-all"
                >
                  Hiring Manager
                </button>
                <button
                  onClick={() => handleFindEmails(app)}
                  disabled={emailLoading === app.id}
                  className="text-xs px-2.5 py-1 rounded-md bg-surface-overlay hover:bg-border disabled:opacity-50 text-text-secondary border border-border transition-all"
                >
                  {emailLoading === app.id ? 'Finding...' : 'Find Emails'}
                </button>
              </div>
              {emailResults && emailResults.appId === app.id && (
                <div className="bg-surface border border-border rounded-lg p-3 mt-2">
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-xs font-medium text-text-secondary">Emails — {emailResults.company}</span>
                    <button onClick={() => setEmailResults(null)} className="text-text-muted hover:text-text-tertiary text-xs">x</button>
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
                <div className="mt-2">
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
                  <button onClick={() => setEditing(app.id)} className="text-xs text-accent hover:underline">
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
