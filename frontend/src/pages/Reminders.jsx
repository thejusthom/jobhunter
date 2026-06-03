import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'

function formatDateForInput(date) {
  const d = new Date(date)
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

function formatTimeForInput(date) {
  const d = new Date(date)
  const pad = n => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function getDefaultDate() {
  const now = new Date()
  // If before 10am, default to today; otherwise tomorrow
  if (now.getHours() >= 10) {
    now.setDate(now.getDate() + 1)
  }
  return formatDateForInput(now)
}

export default function Reminders() {
  const [reminders, setReminders] = useState([])
  const [loading, setLoading] = useState(true)
  const [showAll, setShowAll] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ title: '', date: getDefaultDate(), time: '09:00', application_id: '' })

  const load = () => {
    setLoading(true)
    api.getReminders(showAll).then(setReminders).finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [showAll])

  const handleSubmit = async (e) => {
    e.preventDefault()
    const due_date = `${form.date}T${form.time}:00`
    const data = { title: form.title, due_date }
    if (form.application_id) data.application_id = parseInt(form.application_id)
    await api.createReminder(data)
    setForm({ title: '', date: getDefaultDate(), time: '09:00', application_id: '' })
    setShowForm(false)
    load()
  }

  const complete = async (id) => {
    await api.completeReminder(id)
    load()
  }

  const isOverdue = (d) => new Date(d) < new Date()

  const inputClass = "bg-surface border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:border-accent/50 outline-none transition-colors duration-150"

  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-4">
          <h1 className="text-xl font-semibold text-text-primary">Reminders</h1>
          <label className="flex items-center gap-2 text-sm text-text-tertiary cursor-pointer">
            <input type="checkbox" checked={showAll} onChange={e => setShowAll(e.target.checked)}
              className="rounded border-border accent-accent" />
            Show completed
          </label>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="bg-accent hover:bg-accent-hover text-white font-medium text-sm px-4 py-2 rounded-lg transition-all duration-150"
        >
          {showForm ? 'Cancel' : '+ Add Reminder'}
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleSubmit} className="bg-surface-raised border border-border rounded-xl p-5 mb-5">
          <div className="grid grid-cols-2 gap-3 mb-3">
            <input
              placeholder="Reminder title *"
              required
              value={form.title}
              onChange={e => setForm({ ...form, title: e.target.value })}
              className={`col-span-2 ${inputClass}`}
            />
            <div>
              <label className="block text-xs text-text-muted mb-1.5">Date</label>
              <input
                type="date"
                required
                value={form.date}
                onChange={e => setForm({ ...form, date: e.target.value })}
                className={`w-full ${inputClass}`}
              />
            </div>
            <div>
              <label className="block text-xs text-text-muted mb-1.5">Time</label>
              <input
                type="time"
                required
                value={form.time}
                onChange={e => setForm({ ...form, time: e.target.value })}
                className={`w-full ${inputClass}`}
              />
            </div>
            <input
              placeholder="Application ID (optional)"
              type="number"
              value={form.application_id}
              onChange={e => setForm({ ...form, application_id: e.target.value })}
              className={inputClass}
            />
          </div>
          <button type="submit" className="w-full bg-accent hover:bg-accent-hover text-white font-medium text-sm py-2.5 rounded-lg transition-all duration-150">
            Save Reminder
          </button>
        </form>
      )}

      {loading ? (
        <p className="text-text-muted animate-pulse">Loading...</p>
      ) : reminders.length === 0 ? (
        <p className="text-text-muted">No reminders. Create one to track follow-ups.</p>
      ) : (
        <div className="space-y-1.5">
          {reminders.map(r => (
            <div key={r.id} className={`bg-surface-raised border rounded-lg p-3.5 flex items-center justify-between transition-all duration-150 ${
              r.completed ? 'border-border opacity-50' : isOverdue(r.due_date) ? 'border-danger/40' : 'border-border hover:border-border-hover'
            }`}>
              <div className="min-w-0 flex-1">
                <div className={`font-medium text-sm ${r.completed ? 'text-text-muted line-through' : 'text-text-primary'}`}>
                  {r.title}
                </div>
                <div className="text-sm text-text-tertiary">
                  {(r.job_company || r.app_company) && (
                    <span>{r.job_company || r.app_company}{r.job_title ? ` · ${r.job_title}` : r.app_title ? ` · ${r.app_title}` : ''} · </span>
                  )}
                  <span className={isOverdue(r.due_date) && !r.completed ? 'text-danger' : ''}>
                    Due: {new Date(r.due_date).toLocaleString()}
                  </span>
                </div>
                {r.job_id && !r.completed && (
                  <div className="flex gap-3 mt-0.5">
                    <Link to={`/jobs?select=${r.job_id}`}
                      className="text-xs text-accent hover:underline">View in Queue</Link>
                    {r.job_link && (
                      <a href={r.job_link} target="_blank" rel="noopener noreferrer"
                        className="text-xs text-blue-400 hover:underline">Open Job Link</a>
                    )}
                  </div>
                )}
              </div>
              {!r.completed && (
                <button
                  onClick={() => complete(r.id)}
                  className="bg-accent hover:bg-accent-hover text-white font-medium text-xs px-3 py-1.5 rounded-lg transition-all duration-150"
                >
                  Done
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
