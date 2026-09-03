<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading, MoreFilled, Plus, UserFilled } from '@element-plus/icons-vue'
import { getErrorMessage } from '@/api/errors'
import {
  checkLogin,
  createAccount,
  listAccounts,
  removeAccount,
  scanCancel,
  scanStart,
  scanStatus,
  updateAccount
} from '@/api/accounts'
import type { Account, ScanStatus } from '@/types'

const accounts = ref<Account[]>([])
const loading = ref(false)
const saving = ref(false)
const createDialogVisible = ref(false)
const scanDialogVisible = ref(false)
const polling = ref(false)
const cancellingScan = ref(false)
const scanAccountId = ref('')
const scanAccountName = ref('')
const form = reactive({ name: '', device: '' })
const scan = reactive<ScanStatus>({ status: 'idle', message: '', qrcode: '', error: '' })
let timer: number | undefined

async function load() {
  loading.value = true
  try {
    const { data } = await listAccounts()
    accounts.value = data.accounts
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '账号加载失败，请刷新重试'))
  } finally {
    loading.value = false
  }
}

function openCreate() {
  form.name = ''
  form.device = ''
  createDialogVisible.value = true
}

async function add() {
  if (!form.name.trim()) {
    ElMessage.warning('请输入账号名称')
    return
  }
  saving.value = true
  try {
    await createAccount(form.name.trim(), form.device.trim())
    createDialogVisible.value = false
    ElMessage.success('账号已添加，请扫码登录')
    await load()
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '账号添加失败，请稍后重试'))
  } finally {
    saving.value = false
  }
}

async function toggle(account: Account) {
  const enabled = account.enabled
  try {
    await updateAccount(account.id, { enabled })
    ElMessage.success(enabled ? '账号已启用' : '账号已停用')
  } catch (error: unknown) {
    account.enabled = !enabled
    ElMessage.error(getErrorMessage(error, '账号状态更新失败'))
  }
}

async function rename(account: Account) {
  try {
    const { value } = await ElMessageBox.prompt('请输入便于识别的账号名称', '修改账号名称', {
      inputValue: account.name,
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputValidator: (input: string) => (input.trim() ? true : '名称不能为空')
    })
    await updateAccount(account.id, { name: value.trim() })
    ElMessage.success('账号名称已更新')
    await load()
  } catch (error: unknown) {
    if (error instanceof Error && error.message === 'cancel') return
    if (typeof error === 'string' && error === 'cancel') return
    ElMessage.error(getErrorMessage(error, '账号名称更新失败'))
  }
}

async function del(account: Account) {
  try {
    await ElMessageBox.confirm(`删除「${account.name}」后，登录态会被归档。`, '删除账号', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消'
    })
  } catch {
    return
  }
  try {
    await removeAccount(account.id)
    ElMessage.success('账号已删除')
    await load()
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '账号删除失败'))
  }
}

function accountStatus(account: Account) {
  if (!account.enabled) return { type: 'info', label: '已停用' }
  if (account.running || account.contacts_fetching || account.harvesting) return { type: 'warning', label: '运行中' }
  if (!account.state_file_exists || ['unknown', 'expired', 'failed', 'invalid'].includes(account.session_status || '')) {
    return { type: 'danger', label: account.state_file_exists ? '需重新登录' : '未登录' }
  }
  return { type: 'success', label: '正常' }
}

function scanLabel(status: string) {
  const labels: Record<string, string> = {
    queuing: '正在启动',
    starting: '正在启动',
    waiting_scan: '等待扫码',
    success: '登录成功',
    expired: '二维码已失效',
    cancelled: '已取消',
    failed: '登录失败'
  }
  return labels[status] || '准备中'
}

function fmtTime(value?: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false })
}

async function openScan(account: Account) {
  scanAccountId.value = account.id
  scanAccountName.value = account.name
  scan.status = 'queuing'
  scan.message = '正在准备登录二维码'
  scan.qrcode = ''
  scan.error = ''
  scanDialogVisible.value = true
  try {
    await scanStart(account.id)
    startPolling()
  } catch (error: unknown) {
    scanDialogVisible.value = false
    ElMessage.error(getErrorMessage(error, '扫码登录启动失败'))
  }
}

function startPolling() {
  stopPolling()
  polling.value = true
  timer = window.setInterval(poll, 1500)
}

async function poll() {
  if (!scanAccountId.value) return
  try {
    const { data } = await scanStatus(scanAccountId.value)
    Object.assign(scan, data)
    if (['success', 'failed', 'expired', 'cancelled'].includes(data.status)) {
      stopPolling()
      if (data.status === 'success') {
        ElMessage.success('登录成功')
        await load()
      }
    }
  } catch (error: unknown) {
    stopPolling()
    ElMessage.error(getErrorMessage(error, '登录状态查询失败'))
  }
}

function stopPolling() {
  polling.value = false
  if (timer) {
    window.clearInterval(timer)
    timer = undefined
  }
}

async function closeScan() {
  if (polling.value) {
    cancellingScan.value = true
    try { await scanCancel(scanAccountId.value) } catch { /* 扫码可能已结束 */ }
    cancellingScan.value = false
    stopPolling()
  }
  scanDialogVisible.value = false
}

async function retryScan() {
  const account = accounts.value.find((item) => item.id === scanAccountId.value)
  await closeScan()
  if (account) await openScan(account)
}

async function doCheck(account: Account) {
  try {
    const { data } = await checkLogin(account.id)
    if (data.logged_in) ElMessage.success('登录状态正常')
    else ElMessage.warning(data.reason || '账号未登录')
    await load()
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '登录状态检测失败'))
  }
}

function handleCommand(command: string, account: Account) {
  if (command === 'check') void doCheck(account)
  if (command === 'rename') void rename(account)
  if (command === 'delete') void del(account)
}

onMounted(load)
onUnmounted(stopPolling)
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div><h1 class="page-title">账号管理</h1><p class="page-description">添加抖音账号并保持登录状态。账号正常后才能同步联系人和执行任务。</p></div>
      <div class="page-actions"><el-button type="primary" :icon="Plus" @click="openCreate">添加账号</el-button></div>
    </div>

    <section class="surface">
      <div class="section-header">
        <div><h2 class="section-title">抖音账号</h2><p class="section-description">共 {{ accounts.length }} 个账号</p></div>
      </div>

      <el-skeleton v-if="loading" :rows="5" animated class="loading-block" />
      <div v-else-if="accounts.length" class="account-list">
        <div v-for="account in accounts" :key="account.id" class="account-row">
          <span class="account-avatar"><el-icon><UserFilled /></el-icon></span>
          <div class="account-name"><strong>{{ account.name }}</strong><small>{{ account.device || account.id }}</small></div>
          <div class="account-time"><span>下次任务</span><strong>{{ fmtTime(account.next_run) }}</strong></div>
          <el-tag :type="accountStatus(account).type" size="small">{{ accountStatus(account).label }}</el-tag>
          <el-switch v-model="account.enabled" aria-label="启用账号" @change="toggle(account)" />
          <el-button :type="accountStatus(account).type === 'danger' ? 'primary' : 'default'" size="small" @click="openScan(account)">{{ accountStatus(account).type === 'danger' ? '扫码登录' : '重新登录' }}</el-button>
          <el-dropdown trigger="click" @command="handleCommand($event, account)">
            <el-button text :icon="MoreFilled" aria-label="更多操作" />
            <template #dropdown><el-dropdown-menu><el-dropdown-item command="check">检测登录状态</el-dropdown-item><el-dropdown-item command="rename">修改名称</el-dropdown-item><el-dropdown-item divided command="delete">删除账号</el-dropdown-item></el-dropdown-menu></template>
          </el-dropdown>
        </div>
      </div>
      <div v-else class="empty-panel">
        <el-icon><UserFilled /></el-icon><h3>还没有抖音账号</h3><p>添加账号并扫码登录，之后就能同步联系人。</p><el-button type="primary" :icon="Plus" @click="openCreate">添加第一个账号</el-button>
      </div>
    </section>

    <el-dialog v-model="createDialogVisible" title="添加账号" width="420px" align-center :close-on-click-modal="false">
      <el-form label-position="top" @submit.prevent="add">
        <el-form-item label="账号名称" required><el-input v-model="form.name" autofocus placeholder="例如：主账号" @keyup.enter="add" /></el-form-item>
        <el-form-item label="备注（可选）"><el-input v-model="form.device" placeholder="例如：办公室电脑" @keyup.enter="add" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="createDialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="add">添加并继续</el-button></template>
    </el-dialog>

    <el-dialog v-model="scanDialogVisible" :title="`扫码登录 · ${scanAccountName}`" width="420px" align-center :close-on-click-modal="false" :close-on-press-escape="false" @close="closeScan">
      <div class="scan-content">
        <el-result v-if="scan.status === 'success'" icon="success" title="登录成功" sub-title="现在可以同步联系人和执行任务了" />
        <el-result v-else-if="['failed', 'expired', 'cancelled'].includes(scan.status)" icon="error" :title="scanLabel(scan.status)" :sub-title="scan.error || scan.message" />
        <template v-else>
          <div class="qr-area">
            <img v-if="scan.qrcode" :src="scan.qrcode" alt="抖音登录二维码" />
            <div v-else><el-icon class="is-loading"><Loading /></el-icon><span>{{ scan.message }}</span></div>
          </div>
          <p>打开抖音扫一扫，扫码后会自动完成登录。</p>
        </template>
      </div>
      <template #footer><el-button v-if="['failed', 'expired', 'cancelled'].includes(scan.status)" @click="retryScan">重新扫码</el-button><el-button type="primary" :loading="cancellingScan" @click="closeScan">{{ scan.status === 'success' ? '完成' : '取消' }}</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.loading-block { padding: 24px 20px; }
.account-list { padding: 0 20px; }
.account-row { display: grid; grid-template-columns: 38px minmax(150px, 1fr) 150px auto auto auto 36px; align-items: center; gap: 14px; min-height: 72px; border-bottom: 1px solid var(--color-border); }
.account-row:last-child { border-bottom: 0; }
.account-avatar { display: grid; width: 36px; height: 36px; place-items: center; border-radius: 50%; color: var(--color-text-secondary); background: var(--color-surface-muted); }
.account-name { min-width: 0; }
.account-name strong, .account-name small, .account-time span, .account-time strong { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.account-name strong { font-size: 13px; }
.account-name small, .account-time span { margin-top: 4px; color: var(--color-text-secondary); font-size: 10px; }
.account-time strong { margin-top: 4px; font-size: 11px; font-weight: 600; }
.scan-content { min-height: 300px; }
.qr-area { display: grid; min-height: 260px; place-items: center; border-radius: 10px; background: var(--color-surface-muted); }
.qr-area img { width: 240px; height: 240px; object-fit: contain; }
.qr-area > div { display: flex; flex-direction: column; align-items: center; gap: 12px; color: var(--color-text-secondary); font-size: 12px; }
.qr-area .el-icon { font-size: 34px; }
.scan-content > p { margin: 14px 0 0; color: var(--color-text-secondary); font-size: 12px; text-align: center; }

@media (max-width: 820px) {
  .account-row { grid-template-columns: 36px minmax(0, 1fr) auto auto; gap: 10px; padding: 14px 0; }
  .account-time { display: none; }
  .account-row > .el-switch { grid-column: 2; justify-self: start; }
  .account-row > .el-button { grid-column: 3; }
  .account-row > .el-dropdown { grid-column: 4; }
}
@media (max-width: 480px) {
  .account-list { padding: 0 14px; }
  .account-row { grid-template-columns: 34px minmax(0, 1fr) auto; }
  .account-row > .el-tag { grid-column: 3; }
  .account-row > .el-switch { grid-column: 2; }
  .account-row > .el-button { grid-column: 2 / 3; justify-self: start; }
  .account-row > .el-dropdown { grid-column: 3; grid-row: 2; }
}
</style>
