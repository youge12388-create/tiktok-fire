<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { listAccounts } from '@/api/accounts'
import { getRun, getRunArtifact, listRuns } from '@/api/logs'
import type { Account, RunItem, RunRecord } from '@/types'

type LogRow = RunRecord & { _items?: RunItem[] }

const accounts = ref<Account[]>([])
const rows = ref<LogRow[]>([])
const total = ref(0)
const loading = ref(false)
const filters = reactive({ account_id: '', status: '', date: '', limit: 20, offset: 0 })

const page = computed(() => Math.floor(filters.offset / filters.limit) + 1)

async function loadAccounts() {
  const { data } = await listAccounts()
  accounts.value = data.accounts
}

async function load() {
  loading.value = true
  try {
    const { data } = await listRuns(filters)
    rows.value = data.items
    total.value = data.total
  } catch (e: any) {
    // 空态即可
  } finally {
    loading.value = false
  }
}

function onPage(p: number) {
  filters.offset = (p - 1) * filters.limit
  void load()
}

async function onExpand(row: LogRow) {
  if (row._items) return
  try {
    const { data } = await getRun(row.id)
    row._items = data.items || []
  } catch {
    /* 明细加载失败不阻塞列表 */
  }
}

function fmt(v?: string | null) {
  if (!v) return '—'
  const d = new Date(v)
  if (Number.isNaN(d.getTime())) return v
  return d.toLocaleString('zh-CN', { hour12: false })
}

function duration(start?: string | null, end?: string | null) {
  if (!start) return '—'
  const s = new Date(start).getTime()
  const e = end ? new Date(end).getTime() : Date.now()
  if (Number.isNaN(s) || Number.isNaN(e)) return '—'
  return `${Math.max(0, Math.round((e - s) / 1000))}s`
}

function statusType(s: string) {
  if (s === 'success') return 'success'
  if (s === 'uncertain') return 'warning'
  return 'danger'
}

function openArtifact(id: number) {
  window.open(getRunArtifact(id), '_blank')
}

watch(() => [filters.account_id, filters.status, filters.date], () => {
  filters.offset = 0
  void load()
})

onMounted(() => {
  void loadAccounts()
  void load()
})
</script>

<template>
  <div>
    <el-card style="margin-bottom: 16px">
      <el-form inline>
        <el-form-item label="账号">
          <el-select v-model="filters.account_id" clearable placeholder="全部账号" style="width: 180px">
            <el-option v-for="a in accounts" :key="a.id" :label="a.name" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filters.status" clearable placeholder="全部状态" style="width: 140px">
            <el-option label="成功" value="success" />
            <el-option label="失败" value="failed" />
            <el-option label="不确定" value="uncertain" />
          </el-select>
        </el-form-item>
        <el-form-item label="日期">
          <el-date-picker v-model="filters.date" type="date" value-format="YYYY-MM-DD" clearable />
        </el-form-item>
      </el-form>
    </el-card>

    <el-card header="执行日志">
      <el-table v-loading="loading" :data="rows" empty-text="暂无记录" @expand-change="onExpand">
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="detail">
              <el-table :data="row._items || []" size="small" empty-text="无明细">
                <el-table-column prop="friend_name" label="好友" min-width="140" />
                <el-table-column label="状态" width="110">
                  <template #default="{ row: it }"><el-tag :type="statusType(it.status)">{{ it.status }}</el-tag></template>
                </el-table-column>
                <el-table-column prop="message_preview" label="文案" min-width="160" />
                <el-table-column prop="error" label="失败原因" min-width="180" />
              </el-table>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="180">
          <template #default="{ row }">{{ fmt(row.started_at) }}</template>
        </el-table-column>
        <el-table-column prop="account_id" label="账号" width="150" />
        <el-table-column prop="task_type" label="任务" width="110" />
        <el-table-column label="状态" width="110">
          <template #default="{ row }"><el-tag :type="statusType(row.status)">{{ row.status }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="success_count" label="成功" width="80" />
        <el-table-column prop="failed_count" label="失败" width="80" />
        <el-table-column label="耗时" width="90">
          <template #default="{ row }">{{ duration(row.started_at, row.finished_at) }}</template>
        </el-table-column>
        <el-table-column label="风控" width="80">
          <template #default="{ row }"><el-tag v-if="row.risk_detected" type="danger">是</el-tag><span v-else>-</span></template>
        </el-table-column>
        <el-table-column label="截图" width="70">
          <template #default="{ row }">
            <el-link v-if="row.artifact" type="primary" @click="openArtifact(row.id)">查看</el-link>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="error" label="原因" min-width="160" show-overflow-tooltip />
      </el-table>
      <el-pagination
        style="margin-top: 12px; justify-content: flex-end"
        layout="prev, pager, next, total"
        :total="total"
        :page-size="filters.limit"
        :current-page="page"
        @current-change="onPage"
      />
    </el-card>
  </div>
</template>

<style scoped>
.detail { padding: 8px 16px 16px 48px; }
</style>
