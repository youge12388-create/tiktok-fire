import http from './http'
import type { DailyReconcile } from './tasks'

export interface NotificationStatus {
  configured: boolean
  webhook_url: string
  webhook_url_valid: boolean
  secret_set: boolean
  source: 'settings' | 'env' | 'none'
  editable: boolean
}

export function getDailyReconcile(date?: string) {
  return http.get<DailyReconcile>('/system/reconcile/daily', { params: date ? { date } : {} })
}

export function getNotificationStatus() {
  return http.get<{ dingtalk: NotificationStatus }>('/system/notifications/status')
}

export function updateNotificationConfig(body: { webhook_url?: string; secret?: string; clear?: boolean }) {
  return http.put<{ ok: boolean; dingtalk: NotificationStatus }>('/system/notifications/config', body)
}

export function testNotification() {
  return http.post<{ ok: boolean; message: string }>('/system/notifications/test')
}
