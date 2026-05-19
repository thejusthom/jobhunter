import { useState, useEffect } from 'react'
import { api } from '../api'
import LinkedInIdEditor from '../components/LinkedInIdEditor'

export default function Recruiters() {
  const [recruiters, setRecruiters] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ name: '', company: '', linkedin_url: '', email: '', notes: '' })

  const load = () => {
    setLoading(true)
    api.getRecruiters().then(setRecruiters).finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    await api.createRecruiter(form)
    setForm({ name: '', company: '', linkedin_url: '', email: '', notes: '' })
    setShowForm(false)
    load()
  }

  const inputClass = "bg-surface border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:border-accent/50 outline-none transition-colors duration-150"

  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <h1 className="text-xl font-semibold text-text-primary">Recruiters</h1>
        <button
          onClick={() => setShowForm(!showForm)}
          className="bg-accent hover:bg-accent-hover text-white font-medium text-sm px-4 py-2 rounded-lg transition-all duration-150"
        >
          {showForm ? 'Cancel' : '+ Add Recruiter'}
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleSubmit} className="bg-surface-raised border border-border rounded-xl p-5 mb-5 grid grid-cols-2 gap-3">
          <input placeholder="Name *" required value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} className={inputClass} />
          <input placeholder="Company" value={form.company} onChange={e => setForm({ ...form, company: e.target.value })} className={inputClass} />
          <input placeholder="LinkedIn URL" value={form.linkedin_url} onChange={e => setForm({ ...form, linkedin_url: e.target.value })} className={inputClass} />
          <input placeholder="Email" type="email" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} className={inputClass} />
          <textarea placeholder="Notes" value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} className={`col-span-2 ${inputClass}`} rows={2} />
          <button type="submit" className="col-span-2 bg-accent hover:bg-accent-hover text-white font-medium text-sm py-2.5 rounded-lg transition-all duration-150">
            Save Recruiter
          </button>
        </form>
      )}

      {loading ? (
        <p className="text-text-muted animate-pulse">Loading...</p>
      ) : recruiters.length === 0 ? (
        <p className="text-text-muted">No recruiters tracked yet.</p>
      ) : (
        <div className="space-y-1.5">
          {recruiters.map(r => (
            <div key={r.id} className="bg-surface-raised border border-border rounded-lg p-3.5 transition-all duration-150 hover:border-border-hover">
              <div className="flex items-start justify-between">
                <div>
                  <div className="font-medium text-text-primary text-sm">{r.name}</div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-text-tertiary">{r.company}</span>
                    {r.company && <LinkedInIdEditor company={r.company} compact />}
                  </div>
                </div>
                <div className="flex gap-3">
                  {r.linkedin_url && (
                    <a href={r.linkedin_url} target="_blank" rel="noopener noreferrer" className="text-accent text-sm hover:underline">LinkedIn</a>
                  )}
                  {r.email && (
                    <a href={`mailto:${r.email}`} className="text-accent/70 text-sm hover:underline">{r.email}</a>
                  )}
                </div>
              </div>
              {r.notes && <p className="text-xs text-text-tertiary mt-2">{r.notes}</p>}
              <div className="text-xs text-text-muted mt-1.5">Added {new Date(r.created_at).toLocaleDateString()}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
