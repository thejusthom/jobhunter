import { useState } from 'react'
import { api } from '../api'

export default function Analytics() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)

  const load = () => {
    setLoading(true)
    api.getAnalytics().then(setData).finally(() => setLoading(false))
  }

  if (!data && !loading) {
    return (
      <div className="text-center py-20">
        <h1 className="text-xl font-semibold text-text-primary mb-2">Analytics</h1>
        <p className="text-text-tertiary text-sm mb-5">View detailed stats about your job search</p>
        <button
          onClick={load}
          className="bg-accent hover:bg-accent-hover text-white font-medium text-sm px-6 py-2.5 rounded-lg transition-all duration-150"
        >
          Load Analytics
        </button>
      </div>
    )
  }

  if (loading) return <p className="text-text-muted animate-pulse">Loading analytics...</p>

  const { totals, apps_by_company, apps_by_day, apps_by_status, apps_by_source, apps_by_resume, jobs_by_ats, jobs_by_company, match_pct_distribution, recruiters_by_company,
    interviews_by_status, interviews_by_company, interviews_by_sponsorship, rounds_by_type, rounds_by_status, interview_funnel } = data

  const sponsorshipLabel = (s) => ({ not_discussed: 'Not discussed', will_sponsor: 'Will sponsor', no_sponsorship: 'No sponsorship', unclear: 'Unclear' }[s] || s)
  const sponsorshipData = (interviews_by_sponsorship || []).map(d => ({ ...d, sponsorship_status: sponsorshipLabel(d.sponsorship_status) }))

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-text-primary">Analytics</h1>
        <button onClick={load} className="text-xs text-accent hover:underline">Refresh</button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Applications" value={totals.applications} />
        <StatCard label="This Week" value={totals.apps_this_week} />
        <StatCard label="This Month" value={totals.apps_this_month} />
        <StatCard label="Recruiters" value={totals.recruiters_contacted} />
        <StatCard label="Jobs Discovered" value={totals.jobs_discovered} />
        <StatCard label="AI Evaluations" value={totals.evaluations} />
        <StatCard label="Avg Match %" value={`${totals.avg_match_pct}%`} />
        <StatCard label="Blocked Companies" value={totals.blocked_companies} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <BarSection title="Applications by Company" data={apps_by_company} keyField="company" valueField="count" />
        <BarSection title="Applications by Status" data={apps_by_status} keyField="status" valueField="count" />
        <BarSection title="Jobs by ATS Platform" data={jobs_by_ats} keyField="ats" valueField="count" />
        <BarSection title="Applications by Source" data={apps_by_source} keyField="source" valueField="count" />
        <BarSection title="Resumes Used" data={apps_by_resume} keyField="resume" valueField="count" />
        <BarSection title="Match % Distribution" data={match_pct_distribution} keyField="bracket" valueField="count" />
        <BarSection title="Top Companies (Discovered)" data={jobs_by_company} keyField="company" valueField="count" />
        <BarSection title="Recruiters by Company" data={recruiters_by_company} keyField="company" valueField="count" />
      </div>

      {/* --- Interviews --- */}
      <div>
        <h2 className="text-lg font-semibold text-text-primary mb-3 mt-2">Interviews</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          <StatCard label="Interviews Tracked" value={totals.interviews_total ?? 0} />
          <StatCard label="Active" value={totals.interviews_active ?? 0} />
          <StatCard label="Offers" value={totals.offers ?? 0} />
          <StatCard label="Rounds (next 7d)" value={totals.rounds_upcoming_7d ?? 0} />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <BarSection title="Interview Funnel" data={interview_funnel} keyField="stage" valueField="count" />
          <BarSection title="Sponsorship Status" data={sponsorshipData} keyField="sponsorship_status" valueField="count" />
          <BarSection title="Interviews by Status" data={interviews_by_status} keyField="status" valueField="count" />
          <BarSection title="Interviews by Company" data={interviews_by_company} keyField="company" valueField="count" />
          <BarSection title="Rounds by Type" data={rounds_by_type} keyField="type" valueField="count" />
          <BarSection title="Rounds by Status" data={rounds_by_status} keyField="status" valueField="count" />
        </div>
      </div>

      {apps_by_day.length > 0 && (
        <div className="bg-surface-raised border border-border rounded-xl p-5">
          <h3 className="text-text-primary font-semibold mb-4">Applications per Day</h3>
          <div className="flex items-end gap-1 h-32">
            {apps_by_day.slice(-30).map(d => {
              const maxCount = Math.max(...apps_by_day.slice(-30).map(x => x.count))
              const height = maxCount > 0 ? (d.count / maxCount) * 100 : 0
              return (
                <div key={d.day} className="flex-1 flex flex-col items-center gap-1 group relative">
                  <div
                    className="w-full bg-accent/30 hover:bg-accent/50 rounded-sm transition-colors min-h-[2px]"
                    style={{ height: `${height}%` }}
                  />
                  <div className="absolute -top-6 left-1/2 -translate-x-1/2 bg-surface-overlay text-text-primary text-xs px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none">
                    {d.day}: {d.count}
                  </div>
                </div>
              )
            })}
          </div>
          <div className="flex justify-between mt-2 text-xs text-text-muted">
            <span>{apps_by_day.slice(-30)[0]?.day}</span>
            <span>{apps_by_day.slice(-1)[0]?.day}</span>
          </div>
        </div>
      )}
    </div>
  )
}

function StatCard({ label, value }) {
  return (
    <div className="bg-surface-raised border border-border rounded-xl p-4 text-center">
      <div className="text-2xl font-bold text-text-primary">{value}</div>
      <div className="text-text-tertiary text-xs mt-1">{label}</div>
    </div>
  )
}

function BarSection({ title, data, keyField, valueField }) {
  if (!data || data.length === 0) return null
  const max = Math.max(...data.map(d => d[valueField]))

  return (
    <div className="bg-surface-raised border border-border rounded-xl p-5">
      <h3 className="text-text-primary font-semibold mb-3 text-sm">{title}</h3>
      <div className="space-y-2">
        {data.map(d => (
          <div key={d[keyField]} className="flex items-center gap-3">
            <span className="text-xs text-text-tertiary w-28 truncate shrink-0 capitalize">{d[keyField]}</span>
            <div className="flex-1 bg-surface rounded-full h-2 overflow-hidden">
              <div
                className="bg-accent/40 h-full rounded-full transition-all duration-300"
                style={{ width: `${max > 0 ? (d[valueField] / max) * 100 : 0}%` }}
              />
            </div>
            <span className="text-xs text-text-secondary font-medium w-8 text-right">{d[valueField]}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
