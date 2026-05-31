import { Routes, Route, NavLink, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import Dashboard from './pages/Dashboard'
import JobQueue from './pages/JobQueue'
import Applications from './pages/Applications'
import Evaluations from './pages/Evaluations'
import Analytics from './pages/Analytics'
import Recruiters from './pages/Recruiters'
import Reminders from './pages/Reminders'
import Emails from './pages/Emails'
import AutoApply from './pages/AutoApply'
import Settings from './pages/Settings'

const navItems = [
  { to: '/', label: 'Dashboard' },
  { to: '/jobs', label: 'Job Queue' },
  { to: '/applications', label: 'Applications' },
  { to: '/evaluations', label: 'AI Evals' },
  { to: '/analytics', label: 'Analytics' },
  { to: '/recruiters', label: 'Recruiters' },
  { to: '/emails', label: 'Emails' },
  { to: '/apply', label: 'Auto Apply' },
  { to: '/reminders', label: 'Reminders' },
  { to: '/settings', label: 'Settings' },
]

export default function App() {
  const location = useLocation()
  const [mobileNav, setMobileNav] = useState(false)

  useEffect(() => {
    const match = navItems.find(n => n.to === location.pathname)
    document.title = match ? `${match.label} — JobHunter` : 'JobHunter'
  }, [location.pathname])

  // Close mobile nav on route change
  useEffect(() => { setMobileNav(false) }, [location.pathname])

  return (
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

          {/* Mobile hamburger */}
          <button
            onClick={() => setMobileNav(!mobileNav)}
            className="md:hidden ml-auto p-2 text-text-tertiary hover:text-text-primary transition-colors"
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
          <Route path="/evaluations" element={<Evaluations />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/recruiters" element={<Recruiters />} />
          <Route path="/emails" element={<Emails />} />
          <Route path="/apply" element={<AutoApply />} />
          <Route path="/reminders" element={<Reminders />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  )
}
