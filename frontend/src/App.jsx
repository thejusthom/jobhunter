import { Routes, Route, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useEffect, useState, useRef, useCallback } from 'react'
import { api } from './api'
import { ActivityProvider } from './ActivityContext'
import ActivityPanel from './components/ActivityPanel'
import Dashboard from './pages/Dashboard'
import JobQueue from './pages/JobQueue'
import Applications from './pages/Applications'
import Interviews from './pages/Interviews'
import Evaluations from './pages/Evaluations'
import Analytics from './pages/Analytics'
import Recruiters from './pages/Recruiters'
import Reminders from './pages/Reminders'
import Emails from './pages/Emails'
import AutoApply from './pages/AutoApply'
import Sponsors from './pages/Sponsors'
import Settings from './pages/Settings'

const navItems = [
  { to: '/', label: 'Dashboard' },
  { to: '/jobs', label: 'Job Queue' },
  { to: '/applications', label: 'Applications' },
  { to: '/interviews', label: 'Interviews' },
  { to: '/evaluations', label: 'AI Evals' },
  { to: '/analytics', label: 'Analytics' },
  { to: '/recruiters', label: 'Recruiters' },
  { to: '/emails', label: 'Emails' },
  { to: '/apply', label: 'Auto Apply' },
  { to: '/sponsors', label: 'Sponsors' },
  { to: '/reminders', label: 'Reminders' },
  { to: '/settings', label: 'Settings' },
]

export default function App() {
  const location = useLocation()
  const navigate = useNavigate()
  const [mobileNav, setMobileNav] = useState(false)

  useEffect(() => {
    const match = navItems.find(n => n.to === location.pathname)
    document.title = match ? `${match.label} — JobHunter` : 'JobHunter'
  }, [location.pathname])

  // Close mobile nav on route change
  useEffect(() => { setMobileNav(false) }, [location.pathname])

  // --- Reminder notifications & dropdown ---
  const [dueReminders, setDueReminders] = useState([])
  const [allReminders, setAllReminders] = useState([])
  const [dismissedIds, setDismissedIds] = useState(new Set())
  const notifiedIdsRef = useRef(new Set())
  const [showReminderDropdown, setShowReminderDropdown] = useState(false)
  const reminderDropdownRef = useRef(null)

  const checkReminders = useCallback(async () => {
    try {
      const [due, all] = await Promise.all([
        api.getDueReminders(),
        api.getReminders(false),
      ])
      setDueReminders(due)
      setAllReminders(all)

      // Send browser notifications for new ones
      if (Notification.permission === 'granted') {
        for (const r of due) {
          if (!notifiedIdsRef.current.has(r.id)) {
            notifiedIdsRef.current.add(r.id)
            const body = r.job_company
              ? `${r.job_company}${r.job_title ? ' — ' + r.job_title : ''}`
              : r.app_company
                ? `${r.app_company}${r.app_title ? ' — ' + r.app_title : ''}`
                : ''
            new Notification(r.title, { body, icon: '/favicon.ico', tag: `reminder-${r.id}` })
          }
        }
      }
    } catch (_) {}
  }, [])

  useEffect(() => {
    // Request notification permission
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission()
    }
    // Check immediately and then every 60s
    checkReminders()
    const interval = setInterval(checkReminders, 60000)
    return () => clearInterval(interval)
  }, [checkReminders])

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e) => {
      if (reminderDropdownRef.current && !reminderDropdownRef.current.contains(e.target)) {
        setShowReminderDropdown(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const dismissReminder = async (id) => {
    try {
      await api.completeReminder(id)
      setDismissedIds(prev => new Set([...prev, id]))
      setDueReminders(prev => prev.filter(r => r.id !== id))
      setAllReminders(prev => prev.filter(r => r.id !== id))
    } catch (_) {}
  }

  const overdueReminders = allReminders.filter(r => new Date(r.due_date) <= new Date())
  const upcomingReminders = allReminders.filter(r => new Date(r.due_date) > new Date())
  // Toasts use dismissedIds to hide, bell badge uses full overdue count
  const visibleReminders = overdueReminders.filter(r => !dismissedIds.has(r.id))

  return (
    <ActivityProvider>
    <div className="min-h-screen bg-[#0f0f0f] text-text-primary">
      <nav className="bg-surface border-b border-border sticky top-0 z-50 backdrop-blur-sm bg-surface/95">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 flex items-center h-14 gap-1">
          <span className="text-base font-semibold text-white tracking-tight mr-4 sm:mr-8">JobHunter</span>

          {/* Desktop nav */}
          <div className="hidden md:flex items-center gap-1 overflow-x-auto">
            {navItems.map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded-md text-sm whitespace-nowrap transition-all duration-150 ${
                    isActive
                      ? 'bg-accent/15 text-accent font-medium'
                      : 'text-text-tertiary hover:text-text-secondary hover:bg-surface-raised'
                  }`
                }
              >
                {label}
              </NavLink>
            ))}
          </div>

          {/* Background activity */}
          <div className="ml-auto">
            <ActivityPanel />
          </div>

          {/* Reminder bell */}
          <div className="relative" ref={reminderDropdownRef}>
            <button
              onClick={() => setShowReminderDropdown(!showReminderDropdown)}
              className="relative p-2 text-text-tertiary hover:text-text-primary transition-colors"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
              </svg>
              {overdueReminders.length > 0 && (
                <span className="absolute top-1 right-1 w-2.5 h-2.5 bg-amber-500 rounded-full animate-pulse" />
              )}
              {upcomingReminders.length > 0 && overdueReminders.length === 0 && (
                <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 bg-text-muted rounded-full" />
              )}
            </button>

            {showReminderDropdown && (
              <div className="absolute right-0 top-full mt-1 w-96 bg-surface-raised border border-border rounded-xl shadow-2xl shadow-black/40 z-50 animate-fade-in overflow-hidden">
                <div className="px-4 py-3 border-b border-border flex items-center justify-between">
                  <span className="text-sm font-semibold text-text-primary">Reminders</span>
                  <button onClick={() => { navigate('/reminders'); setShowReminderDropdown(false) }} className="text-xs text-accent hover:underline">View All</button>
                </div>
                <div className="max-h-96 overflow-y-auto">
                  {overdueReminders.length > 0 && (
                    <div className="px-4 pt-3 pb-1">
                      <span className="text-xs uppercase tracking-wider text-amber-400 font-semibold">Overdue ({overdueReminders.length})</span>
                    </div>
                  )}
                  {overdueReminders.map(r => (
                    <div key={r.id} className="px-4 py-3 border-b border-border/50 hover:bg-surface-overlay/50 transition-colors">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <div className="text-sm font-medium text-text-primary">{r.title}</div>
                          {(r.job_company || r.app_company) && (
                            <div className="text-xs text-text-tertiary mt-0.5">
                              {r.job_company || r.app_company}
                              {(r.job_title || r.app_title) && ` — ${r.job_title || r.app_title}`}
                            </div>
                          )}
                          <div className="flex gap-3 mt-1.5">
                            {r.job_id && (
                              <button onClick={() => { navigate(`/jobs?select=${r.job_id}&t=${Date.now()}`); setShowReminderDropdown(false) }}
                                className="text-xs text-accent hover:underline">View Job</button>
                            )}
                            {r.job_link && (
                              <a href={r.job_link} target="_blank" rel="noopener noreferrer"
                                className="text-xs text-blue-400 hover:underline">Apply</a>
                            )}
                          </div>
                        </div>
                        <button onClick={() => dismissReminder(r.id)}
                          className="text-xs px-2.5 py-1 bg-amber-600 hover:bg-amber-500 text-white rounded-md transition-all shrink-0 font-medium">
                          Done
                        </button>
                      </div>
                    </div>
                  ))}
                  {upcomingReminders.length > 0 && (
                    <div className="px-4 pt-3 pb-1">
                      <span className="text-xs uppercase tracking-wider text-text-muted font-semibold">Upcoming</span>
                    </div>
                  )}
                  {upcomingReminders
                    .slice(0, 10)
                    .map(r => (
                    <div key={r.id} className="px-4 py-2.5 border-b border-border/30 hover:bg-surface-overlay/50 transition-colors">
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <div className="text-sm text-text-secondary truncate">{r.title}</div>
                          <div className="text-xs text-text-muted">
                            {new Date(r.due_date).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}
                          </div>
                        </div>
                        <div className="flex gap-2 shrink-0">
                          {r.job_id && (
                            <button onClick={() => { navigate(`/jobs?select=${r.job_id}&t=${Date.now()}`); setShowReminderDropdown(false) }}
                              className="text-xs text-accent hover:underline">View</button>
                          )}
                          <button onClick={() => dismissReminder(r.id)}
                            className="text-xs px-2 py-0.5 bg-surface-overlay hover:bg-border text-text-muted hover:text-text-secondary rounded-md border border-border transition-all">
                            Done
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                  {upcomingReminders.length === 0 && visibleReminders.length === 0 && (
                    <div className="px-4 py-6 text-center text-xs text-text-muted">No reminders</div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Mobile hamburger */}
          <button
            onClick={() => setMobileNav(!mobileNav)}
            className="md:hidden p-2 text-text-tertiary hover:text-text-primary transition-colors"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              {mobileNav ? (
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
              )}
            </svg>
          </button>
        </div>

        {/* Mobile dropdown */}
        {mobileNav && (
          <div className="md:hidden border-t border-border bg-surface animate-fade-in-down">
            <div className="px-4 py-3 grid grid-cols-2 gap-1.5">
              {navItems.map(({ to, label }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={to === '/'}
                  className={({ isActive }) =>
                    `px-3 py-2.5 rounded-lg text-sm text-center transition-all duration-150 ${
                      isActive
                        ? 'bg-accent/15 text-accent font-medium'
                        : 'text-text-tertiary hover:text-text-secondary bg-surface-raised'
                    }`
                  }
                >
                  {label}
                </NavLink>
              ))}
            </div>
          </div>
        )}
      </nav>
      <main className="max-w-7xl mx-auto px-3 sm:px-6 py-4 sm:py-6">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/jobs" element={<JobQueue />} />
          <Route path="/applications" element={<Applications />} />
          <Route path="/interviews" element={<Interviews />} />
          <Route path="/evaluations" element={<Evaluations />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/recruiters" element={<Recruiters />} />
          <Route path="/emails" element={<Emails />} />
          <Route path="/apply" element={<AutoApply />} />
          <Route path="/sponsors" element={<Sponsors />} />
          <Route path="/reminders" element={<Reminders />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>

      {/* Reminder popup toasts */}
      {visibleReminders.length > 0 && !showReminderDropdown && (
        <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm animate-fade-in-up">
          <div className="flex justify-end">
            <button onClick={() => setDismissedIds(prev => new Set([...prev, ...visibleReminders.map(r => r.id)]))}
              className="text-xs text-text-muted hover:text-text-secondary bg-surface-raised/80 backdrop-blur px-2.5 py-1 rounded-md border border-border transition-all">
              Dismiss All
            </button>
          </div>
          {visibleReminders.length > 3 && (
            <div className="text-xs text-text-muted text-right">+{visibleReminders.length - 3} more in bell menu</div>
          )}
          {visibleReminders.slice(0, 3).map(r => (
            <div key={r.id} className="bg-surface-raised border border-amber-500/30 rounded-xl p-4 shadow-2xl shadow-black/40 animate-scale-in">
              <div className="flex items-start gap-3">
                <span className="text-amber-400 text-lg shrink-0 mt-0.5">&#128276;</span>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-text-primary">{r.title}</div>
                  {(r.job_company || r.app_company) && (
                    <div className="text-xs text-text-tertiary mt-0.5">
                      {r.job_company || r.app_company}
                      {(r.job_title || r.app_title) && ` — ${r.job_title || r.app_title}`}
                    </div>
                  )}
                  <div className="flex gap-2 mt-2">
                    {r.job_id && (
                      <button onClick={() => navigate(`/jobs?select=${r.job_id}&t=${Date.now()}`)}
                        className="text-xs text-accent hover:underline">
                        View Job
                      </button>
                    )}
                    {r.job_link && (
                      <a href={r.job_link} target="_blank" rel="noopener noreferrer"
                        className="text-xs text-blue-400 hover:underline">
                        Open Link
                      </a>
                    )}
                    {r.job_contact_linkedin && (
                      <a href={r.job_contact_linkedin.startsWith('http') ? r.job_contact_linkedin : `https://${r.job_contact_linkedin}`}
                        target="_blank" rel="noopener noreferrer"
                        className="text-xs text-sky-400 hover:underline">
                        Contact
                      </a>
                    )}
                  </div>
                </div>
                <div className="flex flex-col gap-1 shrink-0">
                  <button onClick={() => setDismissedIds(prev => new Set([...prev, r.id]))}
                    className="text-text-muted hover:text-text-secondary text-lg leading-none transition-colors" title="Dismiss">
                    &times;
                  </button>
                </div>
              </div>
              <div className="flex gap-2 mt-2 pt-2 border-t border-border/30">
                <button onClick={() => dismissReminder(r.id)}
                  className="text-xs px-2 py-1 bg-amber-600 hover:bg-amber-500 text-white rounded-md transition-all shrink-0">
                  Done
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
    </ActivityProvider>
  )
}
