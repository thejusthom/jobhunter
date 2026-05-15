import { useState, useEffect } from 'react'
import { api } from '../api'

export default function Settings() {
  const [blocked, setBlocked] = useState([])
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    api.getBlockedCompanies().then(setBlocked).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const handleUnblock = async (company) => {
    await api.unblockCompany(company)
    load()
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-text-primary">Settings</h1>

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
