<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { Document } from '@element-plus/icons-vue'
import { listAccounts } from '@/api/accounts'
import { getErrorMessage } from '@/api/errors'
import { getRun, getRunArtifact, listRuns } from '@/api/logs'
import type { Account, RunItem, RunRecord } from '@/types'

type LogRow = RunRecord & { _items?: RunItem[] }

const accounts = ref<Account[]>([])
const rows = ref<LogRow[]>([])
const total = ref(0)
const loading = ref(false)
const errorMessage = ref('')
const filters = reactive({ account_id: '', status: '', date: '', limit: 20, offset: 0 })

const page = computed(() => Math.floor(filters.offset / filters.limit) + 1)
const accountNameMap = computed(() => new Map(accounts.value.map((account) => [account.id, account.display_name || account.name])))
const hasFilters = computed(() => Boolean(filters.account_id || filters.status || filters.date))

function statusType(status: string) {
  if (status === 'success') return 'success'
  if (status === 'uncertain' || status === 'running') return 'warning'
  return 'danger'
}

function statusLabel(status: string) {
  if (status === 'success') return '成功'
  if (status === 'uncertain') return '待确认'
  if (status === 'running') return '执行中'
  return '失败'
}

function taskLabel(task: string) {
  return task === 'spark' ? '续火任务' : task || '自动任务'
}

async function loadAccounts() {
  try {
    const { data } = await listAccounts()
    accounts.value = data.accounts
  } catch (error: unknown) {
    errorMessage.value = getErrorMessage(error, '账号列表加载失败')
  }
}

async function load() {
  loading.value = true
  errorMessage.value = ''
  try {
    const { data } = await listRuns(filters)
    rows.value = data.items
    total.value = data.total
  } catch (error: unknown) {
    errorMessage.value = getErrorMessage(error, '执行记录加载失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  filters.account_id = ''
  filters.status = ''
  filters.date = ''
}

function onPage(pageNumber: number) {
  filters.offset = (pageNumber - 1) * filters.limit
  void load()
}

async function onExpand(row: LogRow, expandedRows: LogRow[]) {
  if (!expandedRows.includes(row) || row._items) return
  try {
    const { data } = await getRun(row.id)
    row._items = data.items || []
  } catch (error: unknown) {
    errorMessage.value = getErrorMessage(error, '记录明细加载失败')
  }
}

function fmt(value?: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

function duration(start?: string | null, end?: string | null) {
  if (!start) return '—'
  const startMs = new Date(start).getTime()
  const endMs = end ? new Date(end).getTime() : Date.now()
  if (Number.isNaN(startMs) || Number.isNaN(endMs)) return '—'
  const seconds = Math.max(0, Math.round((endMs - startMs) / 1000))
  return seconds >= 60 ? `${Math.floor(seconds / 60)}分 ${seconds % 60}秒` : `${seconds}秒`
}

function openArtifact(id: number) {
  window.open(getRunArtifact(id), '_blank', 'noopener,noreferrer')
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
  <div class="page logs-page">
    <header class="page-header">
      <div>
        <h1 class="page-title">执行记录</h1>
        <p class="page-description">查看每次任务的发送结果和失败原因。</p>
      </div>
    </header>

    <el-alert
      v-if="errorMessage"
      class="page-alert"
      type="error"
      :title="errorMessage"
      show-icon
      closable
      @close="errorMessage = ''"
    >
      <template #default>
        <el-button link type="primary" @click="load">重新加载</el-button>
      </template>
    </el-alert>

    <section class="surface">
      <div class="toolbar filter-bar">
        <el-select v-model="filters.account_id" clearable placeholder="全部账号" aria-label="筛选账号">
          <el-option v-for="account in accounts" :key="account.id" :label="account.display_name || account.name" :value="account.id" />
        </el-select>
        <el-select v-model="filters.status" clearable placeholder="全部结果" aria-label="筛选结果">
          <el-option label="成功" value="success" />
          <el-option label="失败" value="failed" />
          <el-option label="待确认" value="uncertain" />
          <el-option label="执行中" value="running" />
        </el-select>
        <el-date-picker
          v-model="filters.date"
          type="date"
          value-format="YYYY-MM-DD"
          clearable
          placeholder="选择日期"
          aria-label="筛选日期"
        />
        <el-button v-if="hasFilters" text @click="resetFilters">清除筛选</el-button>
      </div>

      <div class="section-header record-header">
        <div>
          <h2>运行记录</h2>
          <p>共 {{ total }} 条，展开一条记录可查看联系人明细。</p>
        </div>
      </div>

      <div v-if="loading" class="table-loading" aria-label="正在加载执行记录">
        <el-skeleton :rows="6" animated />
      </div>

      <el-table v-else-if="rows.length" :data="rows" @expand-change="onExpand">
        <el-table-column type="expand" width="44">
          <template #default="{ row }">
            <div class="detail-panel">
              <div class="detail-heading">
                <strong>联系人明细</strong>
                <span>{{ row._items?.length ?? 0 }} 条</span>
              </div>
              <el-skeleton v-if="!row._items" :rows="2" animated />
              <el-table v-else :data="row._items" size="small" empty-text="暂无联系人明细">
                <el-table-column prop="friend_name" label="联系人" min-width="140" />
                <el-table-column label="结果" width="90">
                  <template #default="{ row: item }">
                    <el-tag :type="statusType(item.status)" size="small">{{ statusLabel(item.status) }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="message_preview" label="发送内容" min-width="180" show-overflow-tooltip />
                <el-table-column prop="error" label="失败原因" min-width="180" show-overflow-tooltip />
              </el-table>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="时间" min-width="130">
          <template #default="{ row }">{{ fmt(row.started_at) }}</template>
        </el-table-column>
        <el-table-column label="账号" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ accountNameMap.get(row.account_id) || row.account_id }}</template>
        </el-table-column>
        <el-table-column label="任务" width="105">
          <template #default="{ row }">{{ taskLabel(row.task_type) }}</template>
        </el-table-column>
        <el-table-column label="结果" width="90">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="成功 / 失败" width="110">
          <template #default="{ row }">{{ row.success_count }} / {{ row.failed_count }}</template>
        </el-table-column>
        <el-table-column label="耗时" width="100">
          <template #default="{ row }">{{ duration(row.started_at, row.finished_at) }}</template>
        </el-table-column>
        <el-table-column label="异常" width="80">
          <template #default="{ row }">
            <el-tag v-if="row.risk_detected" type="danger" size="small">风险</el-tag>
            <span v-else class="muted-text">—</span>
          </template>
        </el-table-column>
        <el-table-column label="截图" width="70">
          <template #default="{ row }">
            <el-button v-if="row.artifact" link type="primary" @click="openArtifact(row.id)">查看</el-button>
            <span v-else class="muted-text">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="error" label="错误摘要" min-width="180" show-overflow-tooltip />
      </el-table>

      <div v-else class="empty-panel">
        <el-icon><Document /></el-icon>
        <h3>{{ hasFilters ? '没有符合条件的记录' : '还没有执行记录' }}</h3>
        <p>{{ hasFilters ? '尝试清除筛选条件。' : '任务执行后，结果会自动显示在这里。' }}</p>
        <el-button v-if="hasFilters" @click="resetFilters">清除筛选</el-button>
      </div>

      <el-pagination
        v-if="!loading && total > filters.limit"
        class="pagination"
        layout="prev, pager, next, total"
        :total="total"
        :page-size="filters.limit"
        :current-page="page"
        @current-change="onPage"
      />
    </section>
  </div>
</template>

<style scoped>
.filter-bar {
  padding: 16px 20px;
  border-bottom: 1px solid var(--color-border);
}

.filter-bar :deep(.el-select),
.filter-bar :deep(.el-date-editor) {
  width: 168px;
}

.record-header {
  padding: 20px 20px 14px;
}

.table-loading {
  padding: 12px 20px 28px;
}

.detail-panel {
  padding: 16px 20px 20px 56px;
  background: var(--color-surface-glass-muted);
}

.detail-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  color: var(--color-text-secondary);
  font-size: 13px;
}

.detail-heading strong {
  color: var(--color-text);
}

.muted-text {
  color: var(--color-text-tertiary);
}

.pagination {
  justify-content: flex-end;
  padding: 18px 20px;
  border-top: 1px solid var(--color-border);
}

@media (max-width: 720px) {
  .filter-bar {
    align-items: stretch;
  }

  .filter-bar :deep(.el-select),
  .filter-bar :deep(.el-date-editor) {
    width: 100%;
  }

  .detail-panel {
    padding-left: 16px;
  }
}
</style>
