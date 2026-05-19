import { useState, useEffect } from 'react'
import { api } from '../api'
import LinkedInIdEditor from '../components/LinkedInIdEditor'

export default function Emails() {
  const [data, setData] = useState({ emails: [], total: 0 })
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const PAGE_SIZE = 50

  const load = () => {
    setLoading(true)
    const params = { limit: PAGE_SIZE, offset: page * PAGE_SIZE }
    if (search.trim()) params.company = search.trim()
    api.getCollectedEmails(params).then(setData).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [page, search])

  const totalPages = Math.ceil(data.total / PAGE_SIZE)

  // Group by company
  const grouped = {}
  for (const e of data.emails) {
    if (!grouped[e.company]) grouped[e.company] = []
    grouped[e.company].push(e)
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-semibold text-text-primary">Collected Emails</h1>
          <p className="text-sm text-text-muted mt-0.5">{data.total} contacts found via Hunter.io</p>
        </div>
        <input
          type="text"
          placeholder="Filter by company..."
          value={search}
          onChange={e => { setSearch(e.target.value); setPage(0) }}
          className="bg-surface border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:border-accent/50 outline-none w-64"
        />
      </div>

      {loading ? (
        <p className="text-text-muted animate-pulse">Loading...</p>
      ) : data.emails.length === 0 ? (
        <p className="text-text-muted">No emails collected yet. Use "Find Emails" on jobs to collect contacts.</p>
      ) : (
        <>
          {Object.entries(grouped).map(([company, emails]) => (
            <div key={company} className="bg-surface-raised border border-border rounded-xl p-5 mb-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <h2 className="text-text-primary font-semibold">{company}</h2>
                  <LinkedInIdEditor company={company} compact />
                </div>
                <span className="text-xs text-text-muted">{emails.length} contacts</span>
              </div>
              {emails[0]?.domain && (
                <p className="text-xs text-text-muted mb-3">
                  Domain: <span className="text-text-secondary">{emails[0].domain}</span>
                </p>
              )}
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-text-muted text-xs border-b border-border">
                      <th className="pb-2 pr-4">Name</th>
                      <th className="pb-2 pr-4">Email</th>
                      <th className="pb-2 pr-4">Position</th>
                      <th className="pb-2 pr-4">Department</th>
                      <th className="pb-2 pr-4">Confidence</th>
                      <th className="pb-2 pr-4">From Job</th>
                      <th className="pb-2">Links</th>
                    </tr>
                  </thead>
                  <tbody>
                    {emails.map(e => (
                      <tr key={e.id} className="border-b border-border/30 hover:bg-surface-overlay/30">
                        <td className="py-2 pr-4 text-text-primary font-medium">
                          {e.first_name} {e.last_name}
                        </td>
                        <td className="py-2 pr-4">
                          <a href={`mailto:${e.email}`} className="text-accent hover:underline">{e.email}</a>
                        </td>
                        <td className="py-2 pr-4 text-text-tertiary">{e.position || '-'}</td>
                        <td className="py-2 pr-4 text-text-tertiary">{e.department || '-'}</td>
                        <td className="py-2 pr-4">
                          <span className={`text-xs px-2 py-0.5 rounded-md font-medium ${
                            e.confidence >= 80 ? 'bg-emerald-900/20 text-emerald-400' :
                            e.confidence >= 50 ? 'bg-amber-900/20 text-amber-400' :
                            'bg-red-900/20 text-red-400'
                          }`}>
                            {e.confidence}%
                          </span>
                        </td>
                        <td className="py-2 pr-4 text-text-muted text-xs max-w-[200px] truncate">
                          {e.job_title || '-'}
                        </td>
                        <td className="py-2">
                          {e.linkedin_url && (
                            <a href={e.linkedin_url} target="_blank" rel="noopener noreferrer"
                               className="text-blue-400 hover:underline text-xs">LinkedIn</a>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}

          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-4 pt-3 border-t border-border">
              <button
                onClick={() => setPage(p => Math.max(0, p - 1))}
                disabled={page === 0}
                className="text-sm text-text-secondary hover:text-text-primary disabled:text-text-muted transition-colors"
              >
                Previous
              </button>
              <span className="text-xs text-text-muted">Page {page + 1} of {totalPages}</span>
              <button
                onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                className="text-sm text-text-secondary hover:text-text-primary disabled:text-text-muted transition-colors"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
