import { defineStore } from 'pinia'
import http from '@/api/http'

export const useAuthStore = defineStore('auth', {
  state: () => ({ username: '', authenticated: false, loaded: false }),
  actions: {
    async fetchMe() {
      try {
        const { data } = await http.get<{ ok: boolean; username: string }>('/auth/me')
        this.username = data.username
        this.authenticated = true
      } finally {
        this.loaded = true
      }
    },
    async login(username: string, password: string) {
      const { data } = await http.post<{ ok: boolean; username: string }>('/auth/login', { username, password })
      this.username = data.username
      this.authenticated = true
    },
    async logout() {
      try {
        await http.post('/auth/logout')
      } finally {
        this.username = ''
        this.authenticated = false
        window.location.hash = '#/login'
      }
    }
  }
})
