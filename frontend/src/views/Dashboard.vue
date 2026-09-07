<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { CircleCheck, UserFilled, WarningFilled } from '@element-plus/icons-vue'
import { listAccounts } from '@/api/accounts'
import { listRuns } from '@/api/logs'
import http from '@/api/http'
import type { Account, RunRecord } from '@/types'

interface Summary {
  version?: string
  uptime_seconds?: number
  today?: { runs?: number; sent_ok?: number; sent_failed?: number; risk?: number }
  accounts?: { total?: number; enabled?: number; running?: number; expired?: number; disabled?: number }
  browser_slots_available?: number
  max_concurrent?: number
}

const summary = ref<Summary | null>(null)
const accounts = ref<Account[]>([])
const runs = ref<RunRecord[]>([])
const loading = ref(true)
const hasError = ref(false)

const accountNameMap = computed(() => new Map(accounts.value.map((account) => [account.id, account.display_name || account.name])))
const attentionCount = computed(() => summary.value?.accounts?.expired ?? 0)
const nextRun = computed(() => accounts.value.map((account) => account.next_run).filter(Boolean).sort()[0] || '')

function statusType(status: string) {
  if (status === 'success') return 'success'
  if (status === 'uncertain') return 'warning'
  return 'danger'
}

function statusLabel(status: string) {
  if (status === 'success') return '成功'
  if (status === 'uncertain') return '待确认'
  return '失败'
}

function accountStatus(account: Account) {
  if (!account.enabled) return { label: '已停用', type: 'info' }
  if (account.running) return { label: '执行中', type: 'warning' }
  if (!account.state_file_exists || ['unknown', 'expired', 'failed', 'invalid'].includes(account.session_status || '')) {
    return { label: '需登录', type: 'danger' }
  }
  return { label: '正常', type: 'success' }
}

function fmtTime(value?: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false })
}

async function load() {
  loading.value = true
  hasError.value = false
  const [summaryResult, runsResult, accountsResult] = await Promise.allSettled([
    http.get<Summary>('/system/summary'),
    listRuns({ limit: 6 }),
    listAccounts()
  ])

  if (summaryResult.status === 'fulfilled') summary.value = summaryResult.value.data
  else hasError.value = true
  if (runsResult.status === 'fulfilled') runs.value = runsResult.value.data.items
  else hasError.value = true
  if (accountsResult.status === 'fulfilled') accounts.value = accountsResult.value.data.accounts
  else hasError.value = true
  loading.value = false
}

onMounted(load)
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h1 class="page-title">总览</h1>
        <p class="page-description">查看今天的发送结果和账号状态。</p>
      </div>
      <div class="page-actions"><el-button type="primary" @click="$router.push('/tasks')">配置任务</el-button></div>
    </div>

    <el-alert v-if="hasError && !loading" type="warning" :closable="false" show-icon class="data-alert">
      <template #title>部分数据加载失败</template>
      <template #default><el-button link type="warning" @click="load">重新加载</el-button></template>
    </el-alert>

    <div v-if="!loading && !accounts.length" class="surface onboarding">
      <div class="onboarding-copy">
        <el-icon><UserFilled /></el-icon>
        <div><h2>先添加一个抖音账号</h2><p>完成扫码登录后，就能同步联系人并创建续火任务。</p></div>
      </div>
      <div class="onboarding-steps">
        <router-link to="/accounts"><strong>1</strong><span>添加并登录账号</span></router-link>
        <router-link to="/contacts"><strong>2</strong><span>选择联系人</span></router-link>
        <router-link to="/tasks"><strong>3</strong><span>保存任务配置</span></router-link>
      </div>
      <el-button type="primary" @click="$router.push('/accounts')">开始设置</el-button>
    </div>

    <el-alert v-else-if="!loading && attentionCount" type="warning" :closable="false" show-icon class="data-alert">
      <template #title>{{ attentionCount }} 个账号需要重新登录</template>
      <template #default><router-link to="/accounts" class="alert-link">去处理账号</router-link></template>
    </el-alert>

    <section class="surface metrics" aria-label="今日数据">
      <el-skeleton v-if="loading" :rows="2" animated />
      <template v-else>
        <div><span>今日执行</span><strong>{{ summary?.today?.runs ?? 0 }}</strong></div>
        <div><span>发送成功</span><strong>{{ summary?.today?.sent_ok ?? 0 }}</strong></div>
        <div><span>发送失败</span><strong :class="{ danger: summary?.today?.sent_failed }">{{ summary?.today?.sent_failed ?? 0 }}</strong></div>
        <div><span>风控提醒</span><strong :class="{ danger: summary?.today?.risk }">{{ summary?.today?.risk ?? 0 }}</strong></div>
      </template>
    </section>

    <div class="dashboard-grid">
      <section class="surface">
        <div class="section-header">
          <div><h2 class="section-title">账号状态</h2><p class="section-description">下一次任务：{{ fmtTime(nextRun) }}</p></div>
          <router-link to="/accounts" class="link-action">管理账号</router-link>
        </div>
        <el-skeleton v-if="loading" :rows="4" animated class="section-loading" />
        <div v-else-if="accounts.length" class="account-list">
          <div v-for="account in accounts.slice(0, 5)" :key="account.id" class="account-row">
            <span class="account-icon"><el-icon><UserFilled /></el-icon></span>
            <div><strong>{{ account.display_name || account.name }}</strong><small>{{ fmtTime(account.next_run) }}</small></div>
            <el-tag :type="accountStatus(account).type" size="small">{{ accountStatus(account).label }}</el-tag>
          </div>
        </div>
        <div v-else class="small-empty"><el-icon><WarningFilled /></el-icon><span>暂无账号</span></div>
      </section>

      <section class="surface recent-runs">
        <div class="section-header">
          <div><h2 class="section-title">最近执行</h2><p class="section-description">显示最近 6 次任务结果</p></div>
          <router-link to="/logs" class="link-action">查看全部</router-link>
        </div>
        <el-skeleton v-if="loading" :rows="4" animated class="section-loading" />
        <div v-else-if="runs.length" class="run-table" role="table" aria-label="最近执行记录">
          <div class="run-row run-table-header" role="row">
            <span role="columnheader">时间</span>
            <span role="columnheader">账号</span>
            <span role="columnheader">结果</span>
            <span role="columnheader">成功 / 失败</span>
          </div>
          <div v-for="run in runs" :key="run.id" class="run-row" role="row">
            <span role="cell">{{ fmtTime(run.started_at) }}</span>
            <span class="run-account" role="cell">{{ accountNameMap.get(run.account_id) || run.account_id }}</span>
            <span role="cell"><el-tag :type="statusType(run.status)" size="small">{{ statusLabel(run.status) }}</el-tag></span>
            <span class="run-count" role="cell">{{ run.success_count }} / {{ run.failed_count }}</span>
          </div>
        </div>
        <div v-else class="small-empty"><el-icon><CircleCheck /></el-icon><span>还没有执行记录</span></div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.data-alert { margin-bottom: 16px; }
.alert-link { color: var(--color-warning); font-size: 12px; font-weight: 600; }
.onboarding { display: flex; align-items: center; gap: 24px; margin-bottom: 16px; padding: 22px 24px; }
.onboarding-copy { display: flex; min-width: 250px; flex: 1; align-items: center; gap: 14px; }
.onboarding-copy > .el-icon { color: var(--color-primary); font-size: 28px; }
.onboarding h2 { margin: 0; font-size: 16px; }
.onboarding p { margin: 5px 0 0; color: var(--color-text-secondary); font-size: 12px; }
.onboarding-steps { display: flex; align-items: center; gap: 8px; }
.onboarding-steps a { display: flex; align-items: center; gap: 6px; color: var(--color-text-secondary); font-size: 11px; }
.onboarding-steps strong { display: grid; width: 22px; height: 22px; place-items: center; border: 1px solid var(--color-border); border-radius: 50%; color: var(--color-text); font-size: 10px; }
.metrics { display: grid; grid-template-columns: repeat(4, 1fr); margin-bottom: 16px; }
.metrics .el-skeleton { grid-column: 1 / -1; padding: 20px; }
.metrics > div { padding: 20px 22px; border-right: 1px solid var(--color-border); }
.metrics > div:last-child { border-right: 0; }
.metrics span { display: block; margin-bottom: 9px; color: var(--color-text-secondary); font-size: 12px; }
.metrics strong { font-size: 27px; font-variant-numeric: tabular-nums; }
.metrics strong.danger { color: var(--color-danger); }
.dashboard-grid { display: grid; grid-template-columns: minmax(280px, 0.8fr) minmax(0, 1.5fr); gap: 16px; }
.section-loading { padding: 20px; }
.account-list { padding: 6px 20px 12px; }
.account-row { display: flex; align-items: center; gap: 10px; min-height: 54px; border-bottom: 1px solid var(--color-border); }
.account-row:last-child { border-bottom: 0; }
.account-icon { display: grid; width: 30px; height: 30px; flex: 0 0 30px; place-items: center; border-radius: 50%; color: var(--color-text-secondary); background: var(--color-surface-muted); }
.account-row > div { min-width: 0; flex: 1; }
.account-row strong, .account-row small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.account-row strong { font-size: 12px; }
.account-row small { margin-top: 4px; color: var(--color-text-secondary); font-size: 10px; }
.run-row { display: grid; min-height: 50px; grid-template-columns: minmax(110px, 1.2fr) minmax(100px, 1fr) 82px 105px; align-items: center; padding: 0 12px; border-bottom: 1px solid var(--color-border); font-size: 12px; }
.run-row:last-child { border-bottom: 0; }
.run-table-header { min-height: 42px; color: var(--color-text-secondary); background: var(--color-surface-muted); font-weight: 600; }
.run-account { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.run-count { font-variant-numeric: tabular-nums; }
.small-empty { display: flex; min-height: 180px; align-items: center; justify-content: center; gap: 8px; color: var(--color-text-secondary); font-size: 12px; }
.small-empty .el-icon { font-size: 18px; }

@media (max-width: 960px) {
  .onboarding { align-items: flex-start; flex-direction: column; }
  .dashboard-grid { grid-template-columns: 1fr; }
}
@media (max-width: 640px) {
  .onboarding-steps { align-items: flex-start; flex-direction: column; }
  .metrics { grid-template-columns: repeat(2, 1fr); }
  .metrics > div:nth-child(2) { border-right: 0; }
  .metrics > div:nth-child(-n+2) { border-bottom: 1px solid var(--color-border); }
  .metrics > div { padding: 17px; }
  .metrics strong { font-size: 24px; }
  .run-row { grid-template-columns: 92px minmax(80px, 1fr) 64px; padding: 0 8px; }
  .run-row > :last-child { display: none; }
}
</style>
