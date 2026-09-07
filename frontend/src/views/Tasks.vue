<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Setting, UserFilled } from '@element-plus/icons-vue'
import { listAccounts } from '@/api/accounts'
import { getErrorMessage } from '@/api/errors'
import { dryRun, getTask, putTask, runTask } from '@/api/tasks'
import type { Account } from '@/types'

const accounts = ref<Account[]>([])
const accountId = ref('')
const messagesText = ref('')
const loading = ref(false)
const saving = ref(false)
const running = ref(false)
let taskRequestId = 0
const form = reactive({
  schedule_time: '21:00',
  jitter_minutes: 30,
  send_gap_min: 6,
  send_gap_max: 12,
  max_friends_per_run: 0,
  auto_run_enabled: true
})

const currentAccount = computed(() => accounts.value.find((account) => account.id === accountId.value))
const messageCount = computed(() => messagesText.value.split('\n').map((message) => message.trim()).filter(Boolean).length)
const canExecute = computed(() => Boolean(
  currentAccount.value?.enabled
    && currentAccount.value.state_file_exists
    && currentAccount.value.session_status === 'ok'
    && !currentAccount.value.running
))

function accountStatus(account?: Account) {
  if (!account) return { type: 'info', label: '未选择', message: '请选择一个账号' }
  if (!account.enabled) return { type: 'info', label: '已停用', message: '请先启用账号' }
  if (account.running) return { type: 'warning', label: '执行中', message: '当前账号正在执行任务' }
  if (!account.state_file_exists) return { type: 'danger', label: '需登录', message: '请先完成扫码登录' }
  if (['expired', 'failed', 'invalid'].includes(account.session_status || '')) return { type: 'danger', label: '需重新登录', message: '登录态已失效，请重新扫码登录' }
  if (account.session_status === 'unknown') return { type: 'warning', label: '待检测', message: '建议先检测登录状态，确认登录态可用' }
  return { type: 'success', label: '正常', message: '账号可以执行任务' }
}

async function loadAccounts() {
  try {
    const { data } = await listAccounts()
    accounts.value = data.accounts
    if (!accountId.value && data.accounts.length) accountId.value = data.accounts[0].id
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '账号加载失败，请刷新重试'))
  }
}

async function loadTask(requestedAccountId = accountId.value) {
  const requestId = ++taskRequestId
  if (!requestedAccountId) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const { data } = await getTask(requestedAccountId)
    if (requestId !== taskRequestId || accountId.value !== requestedAccountId) return
    Object.assign(form, {
      schedule_time: data.schedule_time,
      jitter_minutes: data.jitter_minutes,
      send_gap_min: data.send_gap_min,
      send_gap_max: data.send_gap_max,
      max_friends_per_run: data.max_friends_per_run,
      auto_run_enabled: data.auto_run_enabled
    })
    messagesText.value = (data.messages || []).join('\n')
  } catch (error: unknown) {
    if (requestId !== taskRequestId || accountId.value !== requestedAccountId) return
    ElMessage.error(getErrorMessage(error, '任务配置加载失败'))
  } finally {
    if (requestId === taskRequestId) loading.value = false
  }
}

function validate() {
  if (!/^([01]?\d|2[0-3]):[0-5]\d$/.test(form.schedule_time)) {
    ElMessage.warning('请选择正确的执行时间')
    return false
  }
  if (form.send_gap_min > form.send_gap_max) {
    ElMessage.warning('最短间隔不能大于最长间隔')
    return false
  }
  if (!messageCount.value) {
    ElMessage.warning('请至少填写一条发送文案')
    return false
  }
  return true
}

async function save() {
  if (!accountId.value || !validate()) return
  saving.value = true
  try {
    await putTask(accountId.value, { ...form, messages: messagesText.value.split('\n').map((message) => message.trim()).filter(Boolean) })
    ElMessage.success('任务配置已保存')
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '任务配置保存失败'))
  } finally {
    saving.value = false
  }
}

function ensureExecutable() {
  if (!canExecute.value) {
    ElMessage.warning(accountStatus(currentAccount.value).message)
    return false
  }
  return validate()
}

async function doDryRun() {
  if (!ensureExecutable()) return
  running.value = true
  try {
    await dryRun(accountId.value)
    ElMessage.success('测试任务已开始，不会发送真实消息')
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '测试任务启动失败'))
  } finally {
    running.value = false
  }
}

async function doRun() {
  if (!ensureExecutable()) return
  try {
    await ElMessageBox.confirm(`将使用「${currentAccount.value?.name}」发送真实消息。`, '确认立即执行', {
      type: 'warning',
      confirmButtonText: '确认执行',
      cancelButtonText: '取消'
    })
  } catch {
    return
  }
  running.value = true
  try {
    await runTask(accountId.value)
    ElMessage.success('任务已开始，可在执行记录中查看结果')
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '任务启动失败'))
  } finally {
    running.value = false
  }
}

watch(accountId, (nextAccountId) => void loadTask(nextAccountId))
onMounted(loadAccounts)
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div><h1 class="page-title">任务配置</h1><p class="page-description">设置每天的执行时间、发送间隔和消息文案。</p></div>
      <div class="page-actions"><el-button @click="$router.push('/logs')">查看执行记录</el-button></div>
    </div>

    <section class="surface account-bar">
      <div><label class="field-label" for="task-account">抖音账号</label><el-select id="task-account" v-model="accountId" placeholder="选择账号"><el-option v-for="account in accounts" :key="account.id" :label="account.display_name || account.name" :value="account.id" /></el-select></div>
      <div v-if="currentAccount" class="account-state"><el-tag :type="accountStatus(currentAccount).type" size="small">{{ accountStatus(currentAccount).label }}</el-tag><span>{{ accountStatus(currentAccount).message }}</span></div>
    </section>

    <div v-if="!accountId" class="surface empty-panel"><el-icon><UserFilled /></el-icon><h3>还没有可配置的账号</h3><p>请先添加账号并完成扫码登录。</p><el-button type="primary" @click="$router.push('/accounts')">去添加账号</el-button></div>

    <section v-else class="surface config-surface">
      <el-skeleton v-if="loading" :rows="9" animated class="loading-block" />
      <template v-else>
        <el-alert v-if="!canExecute" :type="accountStatus(currentAccount).type === 'danger' ? 'warning' : 'info'" :closable="false" show-icon class="account-alert">
          <template #title>{{ accountStatus(currentAccount).message }}</template>
          <template #default><router-link v-if="accountStatus(currentAccount).type === 'danger'" to="/accounts" class="alert-link">去账号管理</router-link></template>
        </el-alert>

        <el-form label-position="top" class="task-form">
          <div class="form-section">
            <div class="form-section-title"><h2>运行时间</h2><el-switch v-model="form.auto_run_enabled" inline-prompt active-text="自动" inactive-text="手动" /></div>
            <p class="form-help">开启自动运行后，系统每天按以下时间执行。</p>
            <div class="form-grid">
              <el-form-item label="每天执行时间"><el-time-select v-model="form.schedule_time" start="00:00" step="00:15" end="23:45" placeholder="选择时间" /></el-form-item>
              <el-form-item label="随机延迟"><div class="inline-field"><el-input-number v-model="form.jitter_minutes" :min="0" controls-position="right" /><span>分钟内</span></div></el-form-item>
            </div>
          </div>

          <div class="form-section">
            <h2>发送控制</h2><p class="form-help">适当的发送间隔有助于降低账号风险。</p>
            <div class="form-grid">
              <el-form-item label="每位联系人间隔"><div class="range-field"><el-input-number v-model="form.send_gap_min" :min="1" controls-position="right" /><span>至</span><el-input-number v-model="form.send_gap_max" :min="1" controls-position="right" /><span>秒</span></div></el-form-item>
              <el-form-item label="每次发送上限"><div class="inline-field"><el-input-number v-model="form.max_friends_per_run" :min="0" controls-position="right" /><span>人，0 表示不限</span></div></el-form-item>
            </div>
          </div>

          <div class="form-section message-section">
            <h2>发送文案</h2><p class="form-help">每行填写一条，执行时会随机选择。建议准备 3 条以上。</p>
            <el-input v-model="messagesText" type="textarea" :rows="7" maxlength="5000" placeholder="例如：最近还好吗？来续个火～" />
            <span class="message-count">已填写 {{ messageCount }} 条</span>
          </div>
        </el-form>

        <div class="form-actions">
          <span>保存后，新设置会用于下一次任务。</span>
          <div><el-button :loading="running" :disabled="!canExecute" @click="doDryRun">测试运行</el-button><el-button type="danger" plain :loading="running" :disabled="!canExecute" @click="doRun">立即执行</el-button><el-button type="primary" :loading="saving" @click="save">保存配置</el-button></div>
        </div>
      </template>
    </section>
  </div>
</template>

<style scoped>
.account-bar { display: flex; align-items: flex-end; gap: 20px; margin-bottom: 16px; padding: 16px 20px; }
.account-bar > div:first-child { width: 240px; }
.account-state { display: flex; align-items: center; gap: 9px; padding-bottom: 5px; color: var(--color-text-secondary); font-size: 11px; }
.config-surface { overflow: visible; }
.loading-block { padding: 24px; }
.account-alert { width: auto; margin: 20px 20px 0; }
.alert-link { color: var(--color-warning); font-size: 12px; font-weight: 600; }
.task-form { padding: 4px 24px 0; }
.form-section { padding: 22px 0 6px; border-bottom: 1px solid var(--color-border); }
.form-section:last-child { border-bottom: 0; }
.form-section-title { display: flex; align-items: center; justify-content: space-between; }
.form-section h2 { margin: 0; font-size: 14px; }
.form-help { margin: 5px 0 18px; color: var(--color-text-secondary); font-size: 11px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 28px; }
.form-grid :deep(.el-select), .form-grid :deep(.el-date-editor) { width: 180px; }
.inline-field, .range-field { display: flex; align-items: center; gap: 8px; color: var(--color-text-secondary); font-size: 11px; }
.inline-field .el-input-number { width: 140px; }
.range-field .el-input-number { width: 120px; }
.message-section :deep(.el-textarea__inner) { line-height: 1.7; resize: vertical; }
.message-count { display: block; margin-top: 7px; color: var(--color-text-secondary); font-size: 10px; text-align: right; }
.form-actions { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 18px 24px; border-top: 1px solid var(--color-border); background: var(--color-surface-muted); }
.form-actions > span { color: var(--color-text-secondary); font-size: 11px; }
.form-actions > div { display: flex; gap: 8px; }

@media (max-width: 720px) {
  .account-bar { align-items: stretch; flex-direction: column; gap: 10px; }
  .account-bar > div:first-child { width: 100%; }
  .form-grid { grid-template-columns: 1fr; gap: 0; }
  .task-form { padding: 4px 16px 0; }
  .form-actions { align-items: stretch; flex-direction: column; padding: 16px; }
  .form-actions > div { flex-wrap: wrap; }
  .form-actions .el-button { flex: 1; }
}
@media (max-width: 480px) {
  .range-field { align-items: flex-start; flex-wrap: wrap; }
  .range-field .el-input-number { width: calc(50% - 22px); }
}
</style>
