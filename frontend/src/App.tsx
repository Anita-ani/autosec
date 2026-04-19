import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchStats, fetchAlerts } from './api'
import type { Stats, Alert } from './types'
import { StatCard } from './components/StatCard'
import { SeverityPieChart } from './components/SeverityPieChart'
import { HorizontalBarChart } from './components/HorizontalBarChart'
import { AlertsTable } from './components/AlertsTable'
import { CountriesTable } from './components/CountriesTable'
import { BlockedIpsTable } from './components/BlockedIpsTable'
import { GeoMap } from './components/GeoMap'
import { Login } from './components/Login'
import { isAuthenticated, clearSession, getRole } from './auth'
import { useTheme } from './hooks/useTheme'
import { useAlertFeed } from './hooks/useAlertFeed'
import './App.css'

const POLL_INTERVAL = 30_000

function usePolled<T>(fetcher: () => Promise<T>, intervalMs: number) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = async () => {
    try {
      const result = await fetcher()
      setData(result)
      setLastUpdated(new Date())
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  useEffect(() => {
    load()
    timerRef.current = setInterval(load, intervalMs)
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { data, error, lastUpdated, reload: load }
}

export default function App() {
  const [authed, setAuthed] = useState(isAuthenticated)

  if (!authed) {
    return <Login onLogin={() => setAuthed(true)} />
  }

  return <Dashboard onLogout={() => { clearSession(); setAuthed(false) }} />
}

function Dashboard({ onLogout }: { onLogout: () => void }) {
  const [theme, toggleTheme] = useTheme()

  const stats = usePolled<Stats>(fetchStats, POLL_INTERVAL)
  const alertsData = usePolled<{ alerts: Alert[]; count: number }>(
    () => fetchAlerts(20),
    POLL_INTERVAL,
  )

  // Live alert feed — prepend new alerts, mark resolved ones
  const [liveAlerts, setLiveAlerts] = useState<Alert[]>([])
  const [newIds, setNewIds] = useState<Set<string>>(new Set())

  // Sync liveAlerts whenever the poll refreshes
  useEffect(() => {
    if (alertsData.data) setLiveAlerts(alertsData.data.alerts)
  }, [alertsData.data])

  const handleNewAlert = useCallback((alert: Alert) => {
    setLiveAlerts(prev => {
      if (prev.some(a => a.id === alert.id)) return prev
      return [alert, ...prev].slice(0, 50)
    })
    setNewIds(prev => new Set(prev).add(alert.id))
    setTimeout(() => {
      setNewIds(prev => { const s = new Set(prev); s.delete(alert.id); return s })
    }, 2000)
  }, [])

  const handleResolved = useCallback((alertId: string) => {
    setLiveAlerts(prev =>
      prev.map(a => (a.id === alertId ? { ...a, resolved: true } : a)),
    )
  }, [])

  const wsConnected = useAlertFeed(handleNewAlert, handleResolved)

  const lastUpdated    = stats.lastUpdated ?? alertsData.lastUpdated
  const hasError       = stats.error || alertsData.error
  const role           = getRole()
  const initialLoading = !stats.data && !alertsData.data && !hasError

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-icon">🛡</span>
          <span className="brand-name">AutoSecOps</span>
          <span className="brand-sub">Security Dashboard</span>
        </div>
        <div className="header-right">
          {hasError && (
            <span className="error-badge" title={stats.error ?? alertsData.error ?? ''}>
              ⚠ API error
            </span>
          )}
          <span title={wsConnected ? 'Live feed connected' : 'Polling mode'}>
            <span className={`ws-dot${wsConnected ? '' : ' offline'}`} />
          </span>
          <span className="updated">
            {lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()}` : 'Loading…'}
          </span>
          {role && <span className="role-badge">{role}</span>}
          <button className="theme-btn" onClick={toggleTheme} title="Toggle theme">
            {theme === 'dark' ? '☀' : '🌙'}
          </button>
          <button className="logout-btn" onClick={onLogout}>Sign out</button>
        </div>
      </header>

      {initialLoading && (
        <div className="loading-screen">
          <div className="loading-spinner" />
          <p className="loading-label">Loading dashboard…</p>
        </div>
      )}

      <main className="content" style={initialLoading ? { display: 'none' } : undefined}>
        {/* Stat Cards */}
        {stats.data && (
          <section className="cards-row">
            <StatCard label="Total Events"  value={stats.data.totals.events}      accent="#4f8ef7" />
            <StatCard label="Events (24h)"  value={stats.data.totals.events_24h}  accent="#7b61ff" />
            <StatCard label="Total Alerts"  value={stats.data.totals.alerts}      accent="#e67e22" />
            <StatCard label="Open Alerts"   value={stats.data.totals.open_alerts} accent="#e74c3c" />
            <StatCard label="Blocked IPs"   value={stats.data.totals.blocked_ips} accent="#1abc9c" />
          </section>
        )}

        {/* Charts */}
        {stats.data && (
          <section className="charts-row">
            <div className="panel">
              <h2>Alerts by Severity</h2>
              <SeverityPieChart data={stats.data.alerts_by_severity} />
            </div>
            <div className="panel">
              <h2>Open Alerts by Type</h2>
              <HorizontalBarChart data={stats.data.open_alerts_by_type} color="#e67e22" label="open alerts" />
            </div>
            <div className="panel">
              <h2>Event Types (24h)</h2>
              <HorizontalBarChart data={stats.data.events_by_type_24h} color="#4f8ef7" label="events" />
            </div>
          </section>
        )}

        {/* Recent Alerts (live) */}
        <section className="panel full-width">
          <h2>
            Recent Alerts
            <span className="count-badge">
              {wsConnected ? 'live' : `${alertsData.data?.count ?? 0} total`}
            </span>
          </h2>
          {liveAlerts.length > 0 ? (
            <AlertsTable alerts={liveAlerts} newIds={newIds} />
          ) : alertsData.data ? (
            <div className="empty-state">No alerts</div>
          ) : (
            <div className="loading">Loading…</div>
          )}
        </section>

        {/* Geo map + blocked IPs */}
        {stats.data && (
          <section className="charts-row two-col">
            <div className="panel">
              <h2>Source Countries (24h)</h2>
              {stats.data.top_source_countries.length > 0 ? (
                <GeoMap countries={stats.data.top_source_countries} />
              ) : (
                <CountriesTable countries={[]} />
              )}
            </div>
            <div className="panel">
              <h2>Recently Blocked IPs</h2>
              <BlockedIpsTable ips={stats.data.top_blocked_ips} />
            </div>
          </section>
        )}
      </main>
    </div>
  )
}
