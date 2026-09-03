import axios from 'axios'

export function getErrorMessage(error: unknown, fallback: string) {
  if (!axios.isAxiosError<{ detail?: string }>(error)) return fallback
  return error.response?.data?.detail || fallback
}
