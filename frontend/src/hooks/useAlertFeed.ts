import { useEffect, useRef, useState } from 'react'
import { getToken } from '../auth'
import type { Alert } from '../types'

type FeedMessage =
  | { type: 'alert.created'; data: Alert }
  | { type: 'alert.resolved'; data: { alert_id: string } }
  | { type: 'ping' }

type OnNewAlert   = (alert: Alert) => void
type OnResolved   = (alertId: string) => void

const RECONNECT_DELAY_MS = 3_000
const MAX_RECONNECT_DELAY_MS = 30_000

export function useAlertFeed(
  onNewAlert: OnNewAlert,
  onResolved: OnResolved,
): boolean {
  const [connected, setConnected] = useState(false)
  const wsRef      = useRef<WebSocket | null>(null)
  const delayRef   = useRef(RECONNECT_DELAY_MS)
  const timerRef   = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true

    function connect() {
      const token = getToken()
      if (!token || !mountedRef.current) return

      const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
      const url   = `${proto}://${window.location.host}/ws/feed?token=${encodeURIComponent(token)}`
      const ws    = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        if (!mountedRef.current) { ws.close(); return }
        setConnected(true)
        delayRef.current = RECONNECT_DELAY_MS
      }

      ws.onmessage = (e) => {
        try {
          const msg: FeedMessage = JSON.parse(e.data)
          if (msg.type === 'alert.created') onNewAlert(msg.data)
          if (msg.type === 'alert.resolved') onResolved(msg.data.alert_id)
        } catch { /* ignore parse errors */ }
      }

      ws.onclose = (ev) => {
        setConnected(false)
        if (!mountedRef.current) return
        // 4001 = invalid token — don't retry
        if (ev.code === 4001) return
        timerRef.current = setTimeout(() => {
          delayRef.current = Math.min(delayRef.current * 2, MAX_RECONNECT_DELAY_MS)
          connect()
        }, delayRef.current)
      }

      ws.onerror = () => { ws.close() }
    }

    connect()

    return () => {
      mountedRef.current = false
      if (timerRef.current) clearTimeout(timerRef.current)
      wsRef.current?.close()
    }
    // callbacks are stable refs from App — no need to re-run on change
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return connected
}
