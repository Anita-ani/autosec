export interface Totals {
  events: number
  events_24h: number
  alerts: number
  open_alerts: number
  blocked_ips: number
}

export interface BlockedIp {
  ip: string
  reason?: string
  triggered_by?: string
  blocked_at?: string
}

export interface Country {
  country: string
  country_code: string
  count: number
}

export interface Stats {
  totals: Totals
  alerts_by_severity: Record<string, number>
  open_alerts_by_type: Record<string, number>
  events_by_type_24h: Record<string, number>
  top_source_countries: Country[]
  top_blocked_ips: BlockedIp[]
}

export interface Alert {
  id: string
  alert_type: string
  source_ip: string
  severity: string
  message: string
  resolved: boolean
  created_at?: string
}

export interface AlertsResponse {
  alerts: Alert[]
  count: number
}
