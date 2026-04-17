import axios from 'axios'
import type { Stats, AlertsResponse } from './types'

const API_KEY = import.meta.env.VITE_API_KEY ?? 'test-api-key-1234'

const client = axios.create({
  headers: { 'X-API-Key': API_KEY },
})

export async function fetchStats(): Promise<Stats> {
  const { data } = await client.get<Stats>('/stats')
  return data
}

export async function fetchAlerts(limit = 20): Promise<AlertsResponse> {
  const { data } = await client.get<AlertsResponse>(`/alerts?limit=${limit}`)
  return data
}
