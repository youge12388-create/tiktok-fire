import http from './http'
import type { Contact } from '@/types'

export function listContacts(accountId: string) {
  return http.get<{ contacts: Contact[]; fetching: boolean; contacts_error?: string | null }>(`/accounts/${accountId}/contacts`)
}

export function syncContacts(accountId: string) {
  return http.post(`/accounts/${accountId}/contacts/sync`)
}
