const TOKEN_KEY = 'autosec_token'
const ROLE_KEY  = 'autosec_role'

export function saveSession(token: string, role: string) {
  sessionStorage.setItem(TOKEN_KEY, token)
  sessionStorage.setItem(ROLE_KEY, role)
}

export function clearSession() {
  sessionStorage.removeItem(TOKEN_KEY)
  sessionStorage.removeItem(ROLE_KEY)
}

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY)
}

export function getRole(): string | null {
  return sessionStorage.getItem(ROLE_KEY)
}

export function isAuthenticated(): boolean {
  return !!getToken()
}
