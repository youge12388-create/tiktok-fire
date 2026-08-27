import http from './http'
import type { Account, ScanStatus } from '@/types'

export function listAccounts() {
  return http.get<{ accounts: Account[]; current: string; max_concurrent: number; browser_slots_available: number }>('/accounts')
}

export function createAccount(name: string, device = '') {
  return http.post<{ ok: boolean; account: Account }>('/accounts', { name, device })
}

export function updateAccount(id: string, payload: Partial<Pick<Account, 'name' | 'device' | 'enabled'>>) {
  return http.patch<{ ok: boolean; account: Account }>(`/accounts/${id}`, payload)
}

export function removeAccount(id: string) {
  return http.delete(`/accounts/${id}`)
}

export function scanStart(id: string) {
  return http.post<{ ok: boolean; resumed: boolean; status: string; message: string; qrcode: string; error?: string }>(
    `/accounts/${id}/login/start`
  )
}

export function scanStatus(id: string) {
  return http.get<ScanStatus>(`/accounts/${id}/login/status`)
}

export function scanCancel(id: string) {
  return http.post<{ ok: boolean; message: string }>(`/accounts/${id}/login/cancel`)
}

export function checkLogin(id: string) {
  return http.post<{ logged_in: boolean; reason: string; session_status: string }>(`/accounts/${id}/check-login`)
}
