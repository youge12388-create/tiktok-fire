import http from './http'
import type { RunRecord, RunItem } from '@/types'

export interface RunDetail extends RunRecord {
  items?: RunItem[]
}

export function listRuns(params: { account_id?: string; status?: string; date?: string; limit?: number; offset?: number }) {
  return http.get<{ items: RunRecord[]; total: number }>('/runs', { params })
}

export function getRun(id: number) {
  return http.get<RunDetail>(`/runs/${id}`)
}

export function getRunArtifact(runId: number) {
  return `/api/v1/runs/${runId}/artifact`
}
