import { ref } from 'vue'

export type AppTheme = 'light' | 'dark'

const STORAGE_KEY = 'douyin-spark-theme'
const theme = ref<AppTheme>('dark')
let initialized = false

function isTheme(value: string | null): value is AppTheme {
  return value === 'light' || value === 'dark'
}

function storedTheme(): AppTheme | undefined {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY)
    return isTheme(value) ? value : undefined
  } catch {
    return undefined
  }
}

function preferredTheme(): AppTheme {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function applyTheme(nextTheme: AppTheme) {
  theme.value = nextTheme
  document.documentElement.dataset.theme = nextTheme
}

export function initializeTheme() {
  if (initialized || typeof window === 'undefined') return
  initialized = true

  applyTheme(storedTheme() || preferredTheme())
  const media = window.matchMedia?.('(prefers-color-scheme: dark)')
  media?.addEventListener('change', (event) => {
    if (!storedTheme()) applyTheme(event.matches ? 'dark' : 'light')
  })
}

export function useTheme() {
  function setTheme(nextTheme: AppTheme) {
    applyTheme(nextTheme)
    try {
      window.localStorage.setItem(STORAGE_KEY, nextTheme)
    } catch {
      // Theme still applies for the current session when storage is unavailable.
    }
  }

  function toggleTheme() {
    setTheme(theme.value === 'dark' ? 'light' : 'dark')
  }

  return { theme, setTheme, toggleTheme }
}
