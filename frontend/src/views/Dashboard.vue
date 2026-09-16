<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { CircleCheck, UserFilled, WarningFilled } from '@element-plus/icons-vue'
import { listAccounts } from '@/api/accounts'
import { listRuns } from '@/api/logs'
import { getDailyReconcile } from '@/api/system'
import { retryRun } from '@/api/tasks'
import type { AccountReconcile, DailyReconcile } from '@/api/tasks'
import http from '@/api/http'
import type { Account, RunRecord } from '@/types'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getErrorMessage } from '@/api/errors'
import { runTask, stopRun, toggleAutoRun } from '@/api/tasks'
import { fmtDateTime, runStatusLabel, runStatusType } from '@/composables/useReconcile'

interface Summary {
  version?: string
  uptime_seconds?: number
  today?: { runs?: number; sent_ok?: number; sent_failed?: number; risk?: number }
  accounts?: { total?: number; enabled?: number; running?: number; expired?: number; disabled?: number }
  browser_slots_available?: number
  max_concurrent?: number
}

const router = useRouter()
const summary = ref<Summary | null>(null)
const accounts = ref<Account[]>([])
const runs = ref<RunRecord[]>([])
const reconcile = ref<DailyReconcile | null>(null)
const loading = ref(true)
const hasError = ref(false)
const busy = ref('')
const retryingAccount = ref('')

const accountNameMap = computed(() => new Map(accounts.value.map((account) => [account.id, account.display_name || account.name])))
const attentionCount = computed(() => summary.value?.accounts?.expired ?? 0)
const nextRun = computed(() => accounts.value.map((account) => account.next_run).filter(Boolean).sort()[0] || '')
const reconcileTotals = computed(() => reconcile.value?.totals)
// 只展示真正需要人工处理的账号：有失败、待确认或未执行的人。
const problemAccounts = computed(() => (reconcile.value?.accounts ?? []).filter((a) => a.need_retry > 0 || a.counts.uncertain > 0 || a.counts.pending > 0))
const today = new Date().toLocaleDateString('sv-SE')

function statusType(status: string) {
  return runStatusType(status)
}

function statusLabel(status: string) {
  return runStatusLabel(status)
}

function taskStatus(account: Account) {
  if (!account.enabled) return { label: '已停用', type: 'info' }
  if (account.running) return { label: '执行中', type: 'warning' }
  if (!account.state_file_exists) return { label: '需登录', type: 'danger' }
  if (['expired', 'failed', 'invalid'].includes(account.session_status || '')) return { label: '需重新登录', type: 'danger' }
  if (account.session_status === 'unknown') return { label: '待检测', type: 'warning' }
  if (!account.auto_run_enabled) return { label: '已暂停', type: 'info' }
  return { label: '运行中', type: 'success' }
}

function canExecute(account: Account) {
  return Boolean(
    account.enabled
      && account.state_file_exists
      && account.session_status === 'ok'
      && !account.running
  )
}

/** 指标卡片的跳转目标：把「谁失败了」变成执行记录里的可筛选结果。 */
function openMetric(kind: 'runs' | 'ok' | 'failed' | 'risk') {
  const query: Record<string, string> = { date: today }
  if (kind === 'ok') query.status = 'success'
  if (kind === 'failed') query.status = 'failed'
  if (kind === 'risk') query.risk = '1'
  void router.push({ path: '/logs', query })
}

async function onToggleAutoRun(account: Account, val: string | number | boolean) {
  try {
    await toggleAutoRun(account.id, Boolean(val))
    await load()
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '自动运行切换失败'))
    void load()
  }
}

async function runNow(account: Account) {
  if (!canExecute(account)) {
    ElMessage.warning('账号未登录或正在执行，无法立即执行')
    return
  }
  try {
    await ElMessageBox.confirm(
      `将使用「${account.display_name || account.name}」发送真实消息。`,
      '确认立即执行',
      { type: 'warning', confirmButtonText: '确认执行', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  busy.value = account.id
  try {
    await runTask(account.id)
    ElMessage.success('任务已开始，可在执行记录中查看')
    await load()
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '任务启动失败'))
  } finally {
    busy.value = ''
  }
}

async function stopNow(account: Account) {
  busy.value = account.id
  try {
    const { data } = await stopRun(account.id)
    if (data.stopped) ElMessage.success('已发送停止指令，正在中断当前任务')
    else ElMessage.info('当前没有正在执行的任务')
    await load()
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '停止操作失败'))
  } finally {
    busy.value = ''
  }
}

/** 补发：只针对本次指定的人重发，不重发整份名单。 */
async function retryContacts(account: AccountReconcile, names?: string[]) {
  const targets = names?.length ? names : account.retry_names
  if (!targets.length) {
    ElMessage.info('该账号今日没有失败或漏执行的联系人需要补发')
    return
  }
  const preview = targets.slice(0, 5).join('、')
  const more = targets.length > 5 ? ` 等 ${targets.length} 人` : ''
  try {
    await ElMessageBox.confirm(
      `将只给「${targets.length} 位」失败或漏执行的联系人重发一次：${preview}${more}。\n已成功的人不会被重复发送。`,
      '确认补发',
      { type: 'warning', confirmButtonText: '确认补发', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  retryingAccount.value = account.account_id
  try {
    const { data } = await retryRun(account.account_id, names)
    ElMessage.success(`已开始补发 ${data.count} 人${data.skipped.length ? `，${data.skipped.length} 人已不在名单中已跳过` : ''}`)
    await load()
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '补发启动失败'))
  } finally {
    retryingAccount.value = ''
  }
}

function fmtTime(value?: string | null) {
  return fmtDateTime(value)
}

function reconcileSummary(account: AccountReconcile) {
  const c = account.counts
  if (!account.selected_total) return '尚未勾选联系人'
  if (account.running_today) return '今日有任务正在执行'
  if (!account.last_run_at) return '今日尚未执行'
  if (c.failed === 0 && c.uncertain === 0 && c.pending === 0 && c.skipped === 0) return '全部续火成功'
  const parts: string[] = []
  if (c.failed) parts.push(`${c.failed} 人失败`)
  if (c.uncertain) parts.push(`${c.uncertain} 人待确认`)
  if (c.skipped) parts.push(`${c.skipped} 人跳过`)
  if (c.pending) parts.push(`${c.pending} 人未执行`)
  return parts.join('，')
}

async function load() {
  loading.value = true
  hasError.value = false
  const [summaryResult, runsResult, accountsResult, reconcileResult] = await Promise.allSettled([
    http.get<Summary>('/system/summary'),
    listRuns({ limit: 6 }),
    listAccounts(),
    getDailyReconcile()
  ])

  if (summaryResult.status === 'fulfilled') summary.value = summaryResult.value.data
  else hasError.value = true
  if (runsResult.status === 'fulfilled') runs.value = runsResult.value.data.items
  else hasError.value = true
  if (accountsResult.status === 'fulfilled') accounts.value = accountsResult.value.data.accounts
  else hasError.value = true
  if (reconcileResult.status === 'fulfilled') reconcile.value = reconcileResult.value.data
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
        <button type="button" class="metric" @click="openMetric('runs')">
          <span>今日执行</span><strong>{{ summary?.today?.runs ?? 0 }}</strong><small>查看记录 ›</small>
        </button>
        <button type="button" class="metric" @click="openMetric('ok')">
          <span>发送成功</span><strong>{{ summary?.today?.sent_ok ?? 0 }}</strong><small>查看记录 ›</small>
        </button>
        <button type="button" class="metric" @click="openMetric('failed')">
          <span>发送失败</span><strong :class="{ danger: summary?.today?.sent_failed }">{{ summary?.today?.sent_failed ?? 0 }}</strong><small>查看失败 ›</small>
        </button>
        <button type="button" class="metric" @click="openMetric('risk')">
          <span>风控提醒</span><strong :class="{ danger: summary?.today?.risk }">{{ summary?.today?.risk ?? 0 }}</strong><small>查看记录 ›</small>
        </button>
      </template>
    </section>

    <section class="surface reconcile-surface" aria-label="今日续火核对">
      <div class="section-header">
        <div>
          <h2 class="section-title">今日续火核对</h2>
          <p class="section-description">
            按当前勾选名单核对今天的实际发送结果。已选 {{ reconcileTotals?.selected ?? 0 }} 人，
            成功 {{ reconcileTotals?.succeeded ?? 0 }} 人<template v-if="reconcileTotals?.need_retry">，失败或漏发 {{ reconcileTotals.need_retry }} 人待补发</template>。
          </p>
        </div>
        <el-button size="small" :loading="loading" @click="load">重新核对</el-button>
      </div>

      <el-skeleton v-if="loading" :rows="3" animated class="section-loading" />
      <template v-else-if="reconcile?.accounts.length">
        <div v-if="!problemAccounts.length" class="all-clear">
          <el-icon><CircleCheck /></el-icon>
          <div><strong>今天的名单全部续火成功</strong><span>没有需要补发的人。</span></div>
        </div>
        <div v-else class="reconcile-list">
          <article v-for="account in problemAccounts" :key="account.account_id" class="reconcile-card">
            <div class="reconcile-card-head">
              <div>
                <strong>{{ account.display_name }}</strong>
                <small>{{ reconcileSummary(account) }}</small>
              </div>
              <el-button
                type="primary"
                size="small"
                :disabled="account.running || !account.need_retry"
                :loading="retryingAccount === account.account_id"
                @click="retryContacts(account)"
              >
                补发失败/漏发 {{ account.need_retry ? `(${account.need_retry})` : '' }}
              </el-button>
            </div>

            <ul v-if="account.failed.length" class="contact-issues">
              <li v-for="item in account.failed" :key="`f-${item.name}`">
                <el-tag type="danger" size="small">失败</el-tag>
                <span class="issue-name">{{ item.name }}</span>
                <span class="issue-reason">{{ item.reason || '未记录原因' }}</span>
                <el-button link type="primary" size="small" :disabled="account.running" @click="retryContacts(account, [item.name])">只补发此人</el-button>
              </li>
            </ul>
            <ul v-if="account.uncertain.length" class="contact-issues">
              <li v-for="item in account.uncertain" :key="`u-${item.name}`">
                <el-tag type="warning" size="small">待确认</el-tag>
                <span class="issue-name">{{ item.name }}</span>
                <span class="issue-reason">{{ item.reason || '发送后状态未确认' }}</span>
                <el-button link type="primary" size="small" :disabled="account.running" @click="retryContacts(account, [item.name])">只补发此人</el-button>
              </li>
            </ul>
            <p v-if="account.pending.length" class="pending-note">今日未执行 {{ account.pending.length }} 人：{{ account.pending.slice(0, 6).join('、') }}{{ account.pending.length > 6 ? ' …' : '' }}</p>
          </article>
        </div>
      </template>
      <div v-else class="small-empty"><el-icon><CircleCheck /></el-icon><span>还没有可核对的账号</span></div>
    </section>

    <div class="dashboard-grid">
      <section class="surface">
        <div class="section-header">
          <div><h2 class="section-title">账号状态</h2><p class="section-description">下一次任务：{{ fmtTime(nextRun) }}</p></div>
          <router-link to="/accounts" class="link-action">管理账号</router-link>
        </div>
        <el-skeleton v-if="loading" :rows="4" animated class="section-loading" />
        <div v-else-if="accounts.length" class="task-cards">
          <div v-for="account in accounts" :key="account.id" class="task-card">
            <div class="task-card-top">
              <span class="account-icon"><el-icon><UserFilled /></el-icon></span>
              <div class="task-card-main">
                <strong>{{ account.display_name || account.name }}</strong>
                <small>下次任务：{{ fmtTime(account.next_run) }}</small>
              </div>
              <el-tag :type="taskStatus(account).type" size="small">{{ taskStatus(account).label }}</el-tag>
            </div>
            <div class="task-card-meta">
              <span>已选 {{ account.selected_count ?? 0 }} 人</span>
              <span v-if="account.next_harvest">周级采集：{{ fmtTime(account.next_harvest) }}</span>
            </div>
            <div class="task-card-actions">
              <el-switch v-model="account.auto_run_enabled" inline-prompt active-text="运行" inactive-text="停止" :disabled="!account.enabled" @change="(val) => onToggleAutoRun(account, val)" />
              <div class="task-card-btns">
                <el-button size="small" :disabled="!canExecute(account)" :loading="busy === account.id" @click="runNow(account)">立即执行</el-button>
                <el-button v-if="account.running" size="small" type="danger" plain @click="stopNow(account)">中断</el-button>
              </div>
            </div>
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
.metric { display: block; width: 100%; padding: 20px 22px; border: 0; border-right: 1px solid var(--color-border); border-radius: 0; color: inherit; background: none; font: inherit; text-align: left; cursor: pointer; transition: background 160ms ease; }
.metric:last-child { border-right: 0; }
.metric:hover, .metric:focus-visible { background: var(--color-surface-muted); }
.metric:focus-visible { outline: 2px solid var(--color-primary); outline-offset: -2px; }
.metric span { display: block; margin-bottom: 9px; color: var(--color-text-secondary); font-size: 12px; }
.metric strong { display: block; font-size: 27px; font-variant-numeric: tabular-nums; }
.metric strong.danger { color: var(--color-danger); }
.metric small { display: block; margin-top: 8px; color: var(--color-text-tertiary); font-size: 10px; letter-spacing: 0.02em; }
.metric:hover small { color: var(--color-primary); }
.reconcile-surface { margin-bottom: 16px; }
.reconcile-list { display: grid; gap: 12px; padding: 4px 20px 20px; }
.reconcile-card { padding: 14px 16px; border: 1px solid var(--color-glass-border); border-radius: 8px; background: var(--color-surface-muted); }
.reconcile-card-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.reconcile-card-head strong { display: block; font-size: 13px; }
.reconcile-card-head small { display: block; margin-top: 4px; color: var(--color-text-secondary); font-size: 11px; }
.contact-issues { margin: 12px 0 0; padding: 0; list-style: none; display: grid; gap: 6px; }
.contact-issues li { display: flex; align-items: center; gap: 8px; min-width: 0; font-size: 12px; }
.issue-name { flex: 0 0 auto; font-weight: 600; }
.issue-reason { min-width: 0; flex: 1; overflow: hidden; color: var(--color-text-secondary); text-overflow: ellipsis; white-space: nowrap; }
.pending-note { margin: 12px 0 0; color: var(--color-text-tertiary); font-size: 11px; line-height: 1.6; }
.all-clear { display: flex; align-items: center; gap: 12px; padding: 6px 20px 22px; }
.all-clear .el-icon { color: var(--color-success); font-size: 22px; }
.all-clear strong, .all-clear span { display: block; }
.all-clear strong { font-size: 13px; }
.all-clear span { margin-top: 4px; color: var(--color-text-secondary); font-size: 11px; }
.dashboard-grid { display: grid; grid-template-columns: minmax(280px, 0.8fr) minmax(0, 1.5fr); gap: 16px; }
.section-loading { padding: 20px; }
.task-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; padding: 12px 20px 20px; }
.task-card { display: flex; flex-direction: column; gap: 12px; padding: 14px 16px; border: 1px solid var(--color-glass-border); border-radius: 8px; background: var(--color-surface-glass-muted); background-image: var(--color-glass-sheen); box-shadow: inset 0 1px 0 var(--color-glass-highlight), inset 0 -1px 0 var(--color-glass-lowlight); }
.task-card-top { display: flex; align-items: center; gap: 10px; }
.account-icon { display: grid; width: 30px; height: 30px; flex: 0 0 30px; place-items: center; border-radius: 50%; color: var(--color-text-secondary); background: var(--color-surface-muted); }
.task-card-main { min-width: 0; flex: 1; }
.task-card-main strong, .task-card-main small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.task-card-main strong { font-size: 13px; }
.task-card-main small { margin-top: 4px; color: var(--color-text-secondary); font-size: 10px; }
.task-card-meta { display: flex; gap: 16px; color: var(--color-text-secondary); font-size: 11px; }
.task-card-actions { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.task-card-btns { display: flex; gap: 6px; }
.run-row { display: grid; min-height: 50px; grid-template-columns: minmax(110px, 1.2fr) minmax(100px, 1fr) 82px 105px; align-items: center; padding: 0 12px; border-bottom: 1px solid var(--color-border); font-size: 12px; }
.run-row:last-child { border-bottom: 0; }
.run-table-header { min-height: 42px; color: var(--color-text-secondary); background: var(--color-surface-glass-muted); font-weight: 600; }
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
  .metric:nth-child(2) { border-right: 0; }
  .metric:nth-child(-n+2) { border-bottom: 1px solid var(--color-border); }
  .metric { padding: 17px; }
  .metric strong { font-size: 24px; }
  .reconcile-card-head { align-items: stretch; flex-direction: column; }
  .contact-issues li { flex-wrap: wrap; }
  .issue-reason { flex: 1 0 100%; white-space: normal; }
  .run-row { grid-template-columns: 92px minmax(80px, 1fr) 64px; padding: 0 8px; }
  .run-row > :last-child { display: none; }
}
</style>
