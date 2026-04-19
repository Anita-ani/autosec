import { useEffect, useRef, useState } from 'react'
import { fetchStats, fetchAlerts } from './api'
import type { Stats, Alert } from './types'
import { StatCard } from './components/StatCard'
import { SeverityPieChart } from './components/SeverityPieChart'
import { HorizontalBarChart } from './components/HorizontalBarChart'
import { AlertsTable } from './components/AlertsTable'
import { CountriesTable } from './components/CountriesTable'
import { BlockedIpsTable } from './components/BlockedIpsTable'
import { Login } from './components/Login'
import { isAuthenticated, clearSession, getRole } from './auth'
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
  const stats = usePolled<Stats>(fetchStats, POLL_INTERVAL)
  const alertsData = usePolled<{ alerts: Alert[]; count: number }>(
    () => fetchAlerts(20),
    POLL_INTERVAL,
  )

  const lastUpdated = stats.lastUpdated ?? alertsData.lastUpdated
  const hasError = stats.error || alertsData.error
  const role = getRole()

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
            <span
              className="error-badge"
              title={stats.error ?? alertsData.error ?? ''}
            >
              ⚠ API error
            </span>
          )}
          <span className="updated">
            {lastUpdated
              ? `Updated ${lastUpdated.toLocaleTimeString()}`
              : 'Loading…'}
          </span>
          <span className="poll-note">auto-refresh 30s</span>
          {role && <span className="role-badge">{role}</span>}
          <button className="logout-btn" onClick={onLogout}>Sign out</button>
        </div>
      </header>

      <main className="content">
        {/* Stat Cards */}
        {stats.data && (
          <section className="cards-row">
            <StatCard
              label="Total Events"
              value={stats.data.totals.events}
              accent="#4f8ef7"
            />
            <StatCard
              label="Events (24h)"
              value={stats.data.totals.events_24h}
              accent="#7b61ff"
            />
            <StatCard
              label="Total Alerts"
              value={stats.data.totals.alerts}
              accent="#e67e22"
            />
            <StatCard
              label="Open Alerts"
              value={stats.data.totals.open_alerts}
              accent="#e74c3c"
            />
            <StatCard
              label="Blocked IPs"
              value={stats.data.totals.blocked_ips}
              accent="#1abc9c"
            />
          </section>
        )}

        {/* Charts row */}
        {stats.data && (
          <section className="charts-row">
            <div className="panel">
              <h2>Alerts by Severity</h2>
              <SeverityPieChart data={stats.data.alerts_by_severity} />
            </div>
            <div className="panel">
              <h2>Open Alerts by Type</h2>
              <HorizontalBarChart
                data={stats.data.open_alerts_by_type}
                color="#e67e22"
                label="open alerts"
              />
            </div>
            <div className="panel">
              <h2>Event Types (24h)</h2>
              <HorizontalBarChart
                data={stats.data.events_by_type_24h}
                color="#4f8ef7"
                label="events"
              />
            </div>
          </section>
        )}

        {/* Recent Alerts */}
        <section className="panel full-width">
          <h2>
            Recent Alerts
            {alertsData.data && (
              <span className="count-badge">
                {alertsData.data.count} total
              </span>
            )}
          </h2>
          {alertsData.data ? (
            <AlertsTable alerts={alertsData.data.alerts} />
          ) : (
            <div className="loading">Loading…</div>
          )}
        </section>

        {/* Countries + Blocked IPs */}
        {stats.data && (
          <section className="charts-row two-col">
            <div className="panel">
              <h2>Top Source Countries (24h)</h2>
              <CountriesTable countries={stats.data.top_source_countries} />
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
