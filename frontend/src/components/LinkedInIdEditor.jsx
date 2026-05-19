import { useState, useEffect } from 'react'
import { api } from '../api'

/**
 * Inline LinkedIn company ID editor.
 * Shows a small pencil icon that expands into an edit form.
 * Props:
 *   company - company name (required)
 *   compact - if true, renders as a tiny inline widget (for list rows)
 */
export default function LinkedInIdEditor({ company, compact = false }) {
  const [editing, setEditing] = useState(false)
  const [linkedinId, setLinkedinId] = useState('')
  const [verified, setVerified] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!company) return
    setLoaded(false)
    api.getLinkedInId(company).then(data => {
      setLinkedinId(data.linkedin_id || '')
      setVerified(data.verified || false)
      setLoaded(true)
    }).catch(() => setLoaded(true))
  }, [company])

  const handleSave = async (e) => {
    e.preventDefault()
    const val = e.target.elements.lid.value.trim()
    if (!val) return
    setSaving(true)
    try {
      await api.updateLinkedInId(company, val)
      setLinkedinId(val)
      setVerified(true)
      setEditing(false)
    } catch (err) {
      alert(err.message)
    } finally {
      setSaving(false)
    }
  }

  if (!loaded) return null

  if (editing) {
    return (
      <form onSubmit={handleSave} className={`flex items-center gap-1.5 ${compact ? '' : 'bg-surface border border-accent/20 rounded-lg p-2.5 mb-3'}`}>
        <span className="text-xs text-text-muted shrink-0">LinkedIn ID:</span>
        <input
          name="lid"
          type="text"
          defaultValue={linkedinId}
          placeholder="e.g. 74126343"
          className="flex-1 min-w-0 text-xs bg-surface-overlay border border-border rounded-md px-2 py-1 text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent/50"
          autoFocus
        />
        <button type="submit" disabled={saving} className="text-xs px-2 py-1 bg-accent hover:bg-accent-hover disabled:opacity-50 text-white rounded-md transition-all shrink-0">
          {saving ? '...' : 'Save'}
        </button>
        <button type="button" onClick={() => setEditing(false)} className="text-xs px-1 py-1 text-text-muted hover:text-text-tertiary shrink-0">
          ✕
        </button>
      </form>
    )
  }

  return (
    <button
      onClick={() => setEditing(true)}
      className={`inline-flex items-center gap-1 text-xs transition-all ${
        linkedinId
          ? verified
            ? 'text-emerald-500/60 hover:text-emerald-400'
            : 'text-amber-500/60 hover:text-amber-400'
          : 'text-text-muted hover:text-text-tertiary'
      }`}
      title={linkedinId ? `LinkedIn ID: ${linkedinId}${verified ? ' (verified)' : ' (unverified)'}` : 'Set LinkedIn company ID'}
    >
      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" />
      </svg>
      <span>{linkedinId ? `LI: ${linkedinId}` : 'Set LI ID'}</span>
    </button>
  )
}
