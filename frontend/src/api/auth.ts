import http from './http'

export function login(username: string, password: string) {
  return http.post<{ ok: boolean; username: string }>('/auth/login', { username, password })
}

export function logout() {
  return http.post('/auth/logout')
}

export function me() {
  return http.get<{ ok: boolean; username: string }>('/auth/me')
}
