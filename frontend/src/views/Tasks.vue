<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listAccounts } from '@/api/accounts'
import { dryRun, getTask, putTask, runTask } from '@/api/tasks'
import type { Account } from '@/types'

const accounts = ref<Account[]>([])
const accountId = ref('')
const messagesText = ref('')
const loading = ref(false)
const busy = ref(false)
const form = reactive({
  schedule_time: '21:00',
  jitter_minutes: 30,
  send_gap_min: 6,
  send_gap_max: 12,
  max_friends_per_run: 0,
  auto_run_enabled: true
})

const currentAccount = computed(() => accounts.value.find((a) => a.id === accountId.value))
const canExecute = computed(() => Boolean(currentAccount.value && currentAccount.value.enabled && currentAccount.value.state_file_exists))

function accountStatusType(a: Account) {
  if (!a.enabled) return 'info'
  if (a.running) return 'warning'
  const s = a.session_status
  if (!s || s === 'unknown' || s === 'expired' || s === 'failed') return 'danger'
  return 'success'
}

function accountStatusLabel(a: Account) {
  if (!a.enabled) return '已停用'
  if (a.running) return '运行中'
  const s = a.session_status
  if (!s || s === 'unknown' || s === 'expired' || s === 'failed') return '需登录'
  return '正常'
}

async function loadAccounts() {
  const { data } = await listAccounts()
  accounts.value = data.accounts
  if (!accountId.value && data.accounts.length) accountId.value = data.accounts[0].id
}

async function loadTask() {
  if (!accountId.value) return
  loading.value = true
  try {
    const { data } = await getTask(accountId.value)
    Object.assign(form, {
      schedule_time: data.schedule_time,
      jitter_minutes: data.jitter_minutes,
      send_gap_min: data.send_gap_min,
      send_gap_max: data.send_gap_max,
      max_friends_per_run: data.max_friends_per_run,
      auto_run_enabled: data.auto_run_enabled
    })
    messagesText.value = (data.messages || []).join('\n')
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!/^([01]?\d|2[0-3]):[0-5]\d$/.test(form.schedule_time)) {
    ElMessage.warning('时间格式需为 HH:MM')
    return
  }
  await putTask(accountId.value, {
    ...form,
    messages: messagesText.value.split('\n').map((s) => s.trim()).filter(Boolean)
  })
  ElMessage.success('任务已保存')
}

function ensureExecutable() {
  if (!currentAccount.value) {
    ElMessage.warning('请先选择抖音账号')
    return false
  }
  if (!currentAccount.value.enabled) {
    ElMessage.warning('该账号已停用')
    return false
  }
  if (currentAccount.value.running) {
    ElMessage.warning('该账号正在执行任务')
    return false
  }
  if (!currentAccount.value.state_file_exists) {
    ElMessage.warning('该账号尚未登录，无法执行')
    return false
  }
  return true
}

async function doDryRun() {
  if (!ensureExecutable()) return
  busy.value = true
  try {
    await dryRun(accountId.value)
    ElMessage.success('Dry Run 已开始（不发送真实消息）')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || 'Dry Run 失败')
  } finally {
    setTimeout(() => (busy.value = false), 2000)
  }
}

async function doRun() {
  if (!ensureExecutable()) return
  try {
    await ElMessageBox.confirm('确认立即执行续火任务（将真实发送消息）？', '二次确认', { type: 'warning' })
  } catch {
    return
  }
  busy.value = true
  try {
    await runTask(accountId.value)
    ElMessage.success('任务已开始')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '执行失败')
  } finally {
    setTimeout(() => (busy.value = false), 2000)
  }
}

watch(accountId, loadTask)
onMounted(loadAccounts)
</script>

<template>
  <div>
    <el-card style="margin-bottom: 16px">
      <el-form inline>
        <el-form-item label="抖音账号">
          <el-select v-model="accountId" style="width: 220px">
            <el-option v-for="a in accounts" :key="a.id" :label="a.name" :value="a.id" />
          </el-select>
          <el-tag v-if="currentAccount" :type="accountStatusType(currentAccount)" style="margin-left: 8px">
            {{ accountStatusLabel(currentAccount) }}
          </el-tag>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card header="续火任务配置" v-loading="loading">
      <el-form label-width="140px" v-if="accountId">
        <el-form-item label="是否启用"><el-switch v-model="form.auto_run_enabled" /></el-form-item>
        <el-form-item label="执行时间"><el-input v-model="form.schedule_time" style="width: 120px" placeholder="HH:MM" /></el-form-item>
        <el-form-item label="随机窗口(分钟)"><el-input-number v-model="form.jitter_minutes" :min="0" /></el-form-item>
        <el-form-item label="好友间隔(秒)"><el-input-number v-model="form.send_gap_min" :min="1" /> ~ <el-input-number v-model="form.send_gap_max" :min="1" /></el-form-item>
        <el-form-item label="每次上限"><el-input-number v-model="form.max_friends_per_run" :min="0" /></el-form-item>
        <el-form-item label="文案（每行一条）"><el-input v-model="messagesText" type="textarea" :rows="4" /></el-form-item>
        <el-form-item>
          <el-button type="primary" @click="save">保存配置</el-button>
          <el-button :loading="busy" :disabled="!canExecute || currentAccount?.running" @click="doDryRun">Dry Run 测试</el-button>
          <el-button :loading="busy" :disabled="!canExecute || currentAccount?.running" type="danger" @click="doRun">立即执行</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>
