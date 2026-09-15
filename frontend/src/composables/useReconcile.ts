/**
 * 续火核对状态的统一展示口径。
 *
 * 状态来源与后端 `services/reconcile_service.py` 的 run_items.status 分组一一对应，
 * 避免总览、联系人、执行记录三处各写一套文案。
 */

export type ReconcileStatus = 'succeeded' | 'failed' | 'uncertain' | 'skipped' | 'pending'

export interface StatusMeta {
  label: string
  tag: 'success' | 'danger' | 'warning' | 'info'
  /** 是否需要人工关注（失败 / 待确认 / 未发送）。 */
  attention: boolean
  /** 是否允许按人补发。 */
  retryable: boolean
}

const META: Record<ReconcileStatus, StatusMeta> = {
  succeeded: { label: '已续上', tag: 'success', attention: false, retryable: false },
  failed: { label: '续火失败', tag: 'danger', attention: true, retryable: true },
  uncertain: { label: '待确认', tag: 'warning', attention: true, retryable: true },
  skipped: { label: '已跳过', tag: 'info', attention: true, retryable: true },
  pending: { label: '未执行', tag: 'info', attention: true, retryable: true }
}

export function statusMeta(status?: string): StatusMeta {
  return META[(status as ReconcileStatus) ?? 'pending'] ?? META.pending
}

/** run_items / run_records 的原始状态文案（执行记录页沿用）。 */
export function runStatusLabel(status: string) {
  if (status === 'success') return '成功'
  if (status === 'uncertain') return '待确认'
  if (status === 'running') return '执行中'
  if (status === 'skipped') return '已跳过'
  return '失败'
}

export function runStatusType(status: string) {
  if (status === 'success') return 'success'
  if (status === 'uncertain' || status === 'running') return 'warning'
  if (status === 'skipped') return 'info'
  return 'danger'
}

export function fmtDateTime(value?: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  })
}
