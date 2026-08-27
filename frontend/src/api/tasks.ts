import http from './http'

export interface SparkTask {
  schedule_time: string
  jitter_minutes: number
  send_gap_min: number
  send_gap_max: number
  max_friends_per_run: number
  friends: string[]
  messages: string[]
  auto_run_enabled: boolean
  allow_first_message: boolean
}

export function getTask(accountId: string) {
  return http.get<SparkTask>(`/accounts/${accountId}/spark-task`)
}

export function putTask(accountId: string, config: Partial<SparkTask>) {
  return http.put<SparkTask>(`/accounts/${accountId}/spark-task`, { config })
}

export function dryRun(accountId: string) {
  return http.post<{ started: boolean }>(`/accounts/${accountId}/spark-task/dry-run`)
}

export function runTask(accountId: string) {
  return http.post<{ started: boolean }>(`/accounts/${accountId}/spark-task/run`)
}
