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

export interface ReconcileContact {
  name: string
  status: string
  reason: string
  at: string
}

export interface ReconcileCounts {
  succeeded: number
  failed: number
  uncertain: number
  skipped: number
  pending: number
}

export interface ReconcileReport {
  account_id: string
  date: string
  selected_total: number
  counts: ReconcileCounts
  need_retry: number
  retry_names: string[]
  retryable_names: string[]
  contacts: ReconcileContact[]
  failed: ReconcileContact[]
  uncertain: ReconcileContact[]
  skipped: ReconcileContact[]
  pending: string[]
  risk_today: boolean
  running_today: boolean
  last_run_at: string | null
}

export interface AccountReconcile extends Omit<ReconcileReport, 'account_id' | 'contacts' | 'retryable_names'> {
  account_id: string
  name: string
  display_name: string
  enabled: boolean
  running: boolean
  session_status: string
  state_file_exists: boolean
}

export interface DailyReconcile {
  date: string
  accounts: AccountReconcile[]
  totals: ReconcileCounts & { selected: number; need_retry: number; risk_accounts: number }
}

export interface RetryResult {
  started: boolean
  count: number
  names: string[]
  skipped: string[]
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

export function toggleAutoRun(accountId: string, enabled: boolean) {
  return http.post<{ ok: boolean; auto_run_enabled: boolean }>(`/accounts/${accountId}/spark-task/auto-run`, { enabled })
}

export function stopRun(accountId: string) {
  return http.post<{ ok: boolean; stopped: boolean }>(`/accounts/${accountId}/spark-task/stop`)
}

/** 核对当前勾选名单今日的实际发送结果。 */
export function getReconcile(accountId: string, date?: string) {
  return http.get<ReconcileReport>(`/accounts/${accountId}/spark-task/reconcile`, { params: date ? { date } : {} })
}

/** 只补发指定联系人；不传 names 时补发今日确定失败的人。 */
export function retryRun(accountId: string, names?: string[]) {
  return http.post<RetryResult>(`/accounts/${accountId}/spark-task/retry`, names?.length ? { names } : {})
}
