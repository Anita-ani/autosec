import axios from 'axios'
import type { Stats, AlertsResponse } from './types'
import { getToken, clearSession } from './auth'

const client = axios.create()

// Attach Bearer token from sessionStorage on every request
client.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers = config.headers ?? {}
    config.headers['Authorization'] = `Bearer ${token}`
  }
  return config
})

// On 401, clear the session and reload so the login page appears
client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      clearSession()
      window.location.reload()
    }
    return Promise.reject(err)
  },
)

export async function login(username: string, password: string): Promise<{ token: string; role: string }> {
  const { data } = await axios.post('/auth/token', { username, password })
  return { token: data.access_token, role: data.role }
}

export async function fetchStats(): Promise<Stats> {
  const { data } = await client.get<Stats>('/stats')
  return data
}

export async function fetchAlerts(limit = 20): Promise<AlertsResponse> {
  const { data } = await client.get<AlertsResponse>(`/alerts?limit=${limit}`)
  return data
}
