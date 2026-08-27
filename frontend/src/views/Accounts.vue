<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
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
const form = reactive({ name: '', device: '' })

const dialogVisible = ref(false)
const polling = ref(false)
const scanning = ref(false)
const scanAccountId = ref('')
const scanAccountName = ref('')
const scan = reactive<ScanStatus>({ status: 'idle', message: '', qrcode: '', error: '' })
let timer: number | undefined

async function load() {
  loading.value = true
  try {
    const { data } = await listAccounts()
    accounts.value = data.accounts
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '加载账号失败')
  } finally {
    loading.value = false
  }
}

async function add() {
  if (!form.name.trim()) {
    ElMessage.warning('请输入账号名称')
    return
  }
  await createAccount(form.name.trim(), form.device.trim())
  form.name = ''
  form.device = ''
  ElMessage.success('已新增账号')
  await load()
}

async function toggle(a: Account) {
  await updateAccount(a.id, { enabled: a.enabled })
  ElMessage.success('已更新')
}

async function rename(a: Account) {
  try {
    const { value } = await ElMessageBox.prompt('请输入新的账号名称', '修改账号名称', {
      inputValue: a.name,
      inputValidator: (v: string) => (v && v.trim() ? true : '名称不能为空')
    })
    await updateAccount(a.id, { name: value.trim() })
    ElMessage.success('已更新')
    await load()
  } catch {
    /* 用户取消 */
  }
}

async function del(a: Account) {
  try {
    await ElMessageBox.confirm(`确认删除账号「${a.name}」？登录态将归档而非立即删除。`, '删除账号', {
      type: 'warning'
    })
  } catch {
    return
  }
  await removeAccount(a.id)
  ElMessage.success('已删除')
  await load()
}

function accountStatus(a: Account) {
  if (!a.enabled) return { type: 'info', label: '已停用' }
  if (a.running || a.contacts_fetching || a.harvesting) return { type: 'warning', label: '运行中' }
  const s = a.session_status
  if (!s || s === 'unknown') {
    return { type: 'danger', label: a.state_file_exists ? '需重新登录' : '未登录' }
  }
  if (['expired', 'failed', 'invalid'].includes(s)) return { type: 'danger', label: '需重新登录' }
  return { type: 'success', label: '正常' }
}

function scanLabel(s: string) {
  switch (s) {
    case 'queuing':
    case 'starting':
      return '正在启动'
    case 'waiting_scan':
      return '等待扫码'
    case 'success':
      return '登录成功'
    case 'expired':
      return '二维码失效'
    case 'cancelled':
      return '已取消'
    case 'failed':
      return '登录失败'
    default:
      return s || '空闲'
  }
}

function fmtTime(v?: string | null) {
  if (!v) return '—'
  const d = new Date(v)
  if (Number.isNaN(d.getTime())) return v
  return d.toLocaleString('zh-CN', { hour12: false })
}

async function openScan(a: Account) {
  scanAccountId.value = a.id
  scanAccountName.value = a.name
  scan.status = 'queuing'
  scan.message = '正在启动扫码环境…'
  scan.qrcode = ''
  scan.error = ''
  dialogVisible.value = true
  try {
    await scanStart(a.id)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '发起扫码失败')
    dialogVisible.value = false
    return
  }
  startPolling()
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
    scan.status = data.status
    scan.message = data.message
    scan.qrcode = data.qrcode
    scan.error = data.error
    if (['success', 'failed', 'expired', 'cancelled'].includes(data.status)) {
      stopPolling()
      if (data.status === 'success') {
        ElMessage.success('登录成功')
        await load()
      }
    }
  } catch (e: any) {
    stopPolling()
    ElMessage.error(e?.response?.data?.detail || '查询扫码状态失败')
  }
}

function stopPolling() {
  polling.value = false
  if (timer) {
    window.clearInterval(timer)
    timer = undefined
  }
}

async function closeDialog() {
  if (polling.value) {
    scanning.value = true
    try {
      await scanCancel(scanAccountId.value)
    } catch {
      /* 忽略 */
    } finally {
      scanning.value = false
    }
    stopPolling()
  }
  dialogVisible.value = false
}

async function doCheck(a: Account) {
  try {
    const { data } = await checkLogin(a.id)
    if (data.logged_in) {
      ElMessage.success('登录状态正常')
    } else {
      ElMessage.warning(data.reason || '未登录')
    }
    await load()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '检测登录失败')
  }
}

onMounted(load)
</script>

<template>
  <div>
    <el-card class="block">
      <template #header>新增账号</template>
      <el-form inline>
        <el-form-item label="账号名称">
          <el-input v-model="form.name" style="width: 200px" placeholder="例如：我的抖音" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.device" style="width: 240px" placeholder="可选，用于标识设备" />
        </el-form-item>
        <el-button type="primary" @click="add">新增</el-button>
      </el-form>
    </el-card>

    <el-card class="block">
      <template #header>抖音账号</template>
      <el-table v-loading="loading" :data="accounts" empty-text="暂无账号">
        <el-table-column prop="name" label="名称" min-width="140" />
        <el-table-column prop="id" label="账号ID" width="160" />
        <el-table-column label="登录状态" width="120">
          <template #default="{ row }">
            <el-tag :type="accountStatus(row).type">{{ accountStatus(row).label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最后运行" width="180">
          <template #default="{ row }">{{ fmtTime(row.last_run) }}</template>
        </el-table-column>
        <el-table-column label="下次任务" width="180">
          <template #default="{ row }">{{ fmtTime(row.next_run) }}</template>
        </el-table-column>
        <el-table-column label="启用" width="80">
          <template #default="{ row }">
            <el-switch v-model="row.enabled" @change="toggle(row)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openScan(row)">扫码登录</el-button>
            <el-button link @click="doCheck(row)">检测登录</el-button>
            <el-button link @click="rename(row)">重命名</el-button>
            <el-button link type="danger" @click="del(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="`扫码登录 - ${scanAccountName}`"
      width="420px"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      @close="closeDialog"
    >
      <div class="scan-body">
        <template v-if="scan.status === 'success'">
          <el-result icon="success" title="登录成功" :sub-title="scan.message" />
        </template>
        <template v-else-if="['failed', 'expired', 'cancelled'].includes(scan.status)">
          <el-result icon="error" :title="scanLabel(scan.status)" :sub-title="scan.error || scan.message" />
        </template>
        <template v-else>
          <div class="qr-wrap">
            <img v-if="scan.qrcode" :src="scan.qrcode" alt="登录二维码" class="qr" />
            <div v-else class="qr-loading">
              <el-icon class="is-loading" size="40"><Loading /></el-icon>
              <span>{{ scan.message || '正在启动扫码环境…' }}</span>
            </div>
          </div>
          <p class="scan-tip">{{ scanLabel(scan.status) }} · {{ scan.message }}</p>
        </template>
      </div>
      <template #footer>
        <el-button type="primary" :loading="scanning" @click="closeDialog">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.block + .block { margin-top: 16px; }
.qr-wrap { display: flex; flex-direction: column; align-items: center; padding: 12px 0; }
.qr { width: 260px; height: 260px; object-fit: contain; background: #f8fafc; border-radius: 8px; }
.qr-loading { display: flex; flex-direction: column; align-items: center; gap: 12px; color: #64748b; padding: 60px 0; }
.scan-tip { margin: 12px 0 0; text-align: center; color: #475569; }
</style>
