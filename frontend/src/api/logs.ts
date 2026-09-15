import http from './http'
import { withAppBasePath } from './base'
import type { RunRecord, RunItem } from '@/types'

export interface RunDetail extends RunRecord {
  items?: RunItem[]
}

export interface RunFilters {
  account_id?: string
  status?: string
  date?: string
  risk?: boolean
  limit?: number
  offset?: number
}

export function listRuns(params: RunFilters) {
  return http.get<{ items: RunRecord[]; total: number }>('/runs', { params })
}

export function getRun(id: number) {
  return http.get<RunDetail>(`/runs/${id}`)
}

export function getRunArtifact(runId: number) {
  return withAppBasePath(`/api/v1/runs/${runId}/artifact`)
}
