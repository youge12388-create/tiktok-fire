import http from './http'
import type { Contact } from '@/types'

export interface ContactsResponse {
  contacts: Contact[]
  fetching: boolean
  contacts_error?: string | null
  selected_count?: number
}

export function listContacts(accountId: string) {
  return http.get<ContactsResponse>(`/accounts/${accountId}/contacts`)
}

export function syncContacts(accountId: string) {
  return http.post(`/accounts/${accountId}/contacts/sync`)
}

export function setContactsSelection(accountId: string, names: string[]) {
  return http.put<{ selected: string[]; updated: number; added: number }>(`/accounts/${accountId}/contacts/selection`, { names })
}

export function deleteContacts(accountId: string, names: string[]) {
  return http.post<{ removed: number; total: number }>(`/accounts/${accountId}/contacts/delete`, { names })
}
