<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listAccounts } from '@/api/accounts'
import { listRuns } from '@/api/logs'
import http from '@/api/http'
import type { RunRecord } from '@/types'

const summary = ref<any>(null)
const runs = ref<RunRecord[]>([])
const nextRun = ref('')

onMounted(async () => {
  try {
    const { data } = await http.get('/system/summary')
    summary.value = data
  } catch { /* ignore */ }
  try {
    const { data } = await listRuns({ limit: 10 })
    runs.value = data.items
  } catch { /* ignore */ }
  try {
    const { data } = await listAccounts()
    const times = data.accounts.map((a: any) => a.next_run).filter(Boolean).sort()
    nextRun.value = times[0] || ''
  } catch { /* ignore */ }
})

function statusType(s: string) {
  if (s === 'success') return 'success'
  if (s === 'uncertain') return 'warning'
  return 'danger'
}

function fmtTime(v?: string) {
  if (!v) return '—'
  const d = new Date(v)
  if (Number.isNaN(d.getTime())) return v
  return d.toLocaleString('zh-CN', { hour12: false })
}

function fmtUptime(sec?: number) {
  if (sec == null) return '—'
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  return h > 0 ? `${h}小时 ${m}分` : `${m}分钟`
}
</script>

<template>
  <div>
    <el-card class="block" style="margin-bottom: 16px">
      <el-descriptions :column="2" size="small" border>
        <el-descriptions-item label="服务状态"><el-tag type="success">运行中</el-tag></el-descriptions-item>
        <el-descriptions-item label="版本">{{ summary?.version ?? '1.0.0' }}</el-descriptions-item>
        <el-descriptions-item label="运行时间">{{ fmtUptime(summary?.uptime_seconds) }}</el-descriptions-item>
        <el-descriptions-item label="下一次任务">{{ nextRun ? fmtTime(nextRun) : '—' }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-row :gutter="16">
      <el-col :span="6"><el-card><el-statistic title="今日执行" :value="summary?.today?.runs ?? 0" /></el-card></el-col>
      <el-col :span="6"><el-card><el-statistic title="发送成功" :value="summary?.today?.sent_ok ?? 0" /></el-card></el-col>
      <el-col :span="6"><el-card><el-statistic title="发送失败" :value="summary?.today?.sent_failed ?? 0" /></el-card></el-col>
      <el-col :span="6"><el-card><el-statistic title="风控" :value="summary?.today?.risk ?? 0" /></el-card></el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :span="8"><el-card header="账号"><el-descriptions :column="1" size="small">
        <el-descriptions-item label="账号总数">{{ summary?.accounts?.total ?? 0 }}</el-descriptions-item>
        <el-descriptions-item label="启用">{{ summary?.accounts?.enabled ?? 0 }}</el-descriptions-item>
        <el-descriptions-item label="运行中">{{ summary?.accounts?.running ?? 0 }}</el-descriptions-item>
        <el-descriptions-item label="需重登">{{ summary?.accounts?.expired ?? 0 }}</el-descriptions-item>
        <el-descriptions-item label="已停用">{{ summary?.accounts?.disabled ?? 0 }}</el-descriptions-item>
      </el-descriptions></el-card></el-col>
      <el-col :span="16"><el-card header="最近执行">
        <el-table :data="runs" size="small" empty-text="暂无记录">
          <el-table-column prop="started_at" label="时间" width="170" />
          <el-table-column prop="account_id" label="账号" width="120" />
          <el-table-column prop="task_type" label="任务" width="100" />
          <el-table-column label="状态" width="100">
            <template #default="{ row }"><el-tag :type="statusType(row.status)">{{ row.status }}</el-tag></template>
          </el-table-column>
          <el-table-column prop="success_count" label="成功" width="80" />
          <el-table-column prop="failed_count" label="失败" width="80" />
        </el-table>
      </el-card></el-col>
    </el-row>
  </div>
</template>
