import { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react'
import { api } from './api'

const ActivityContext = createContext({ tasks: [], recent: [], events: [], refresh: () => {} })

export function useActivity() {
  return useContext(ActivityContext)
}

// Polls the server-side activity feed. Because this provider is mounted once at the app root,
// the live state survives route changes and page refreshes (the server holds the truth).
export function ActivityProvider({ children }) {
  const [data, setData] = useState({ tasks: [], recent: [], events: [] })
  const activeRef = useRef(false)

  const refresh = useCallback(async () => {
    try {
      const snap = await api.getActivity()
      setData(snap)
      activeRef.current = (snap.tasks?.length || 0) > 0
    } catch (_) { /* ignore transient errors */ }
  }, [])

  useEffect(() => {
    let timer
    let cancelled = false
    const tick = async () => {
      await refresh()
      if (cancelled) return
      // Poll fast while something is running, slow when idle.
      timer = setTimeout(tick, activeRef.current ? 1000 : 5000)
    }
    tick()
    return () => { cancelled = true; clearTimeout(timer) }
  }, [refresh])

  return (
    <ActivityContext.Provider value={{ ...data, refresh }}>
      {children}
    </ActivityContext.Provider>
  )
}
