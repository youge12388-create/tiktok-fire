<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { listAccounts } from '@/api/accounts'
import { listContacts, syncContacts } from '@/api/contacts'
import { getTask, putTask } from '@/api/tasks'
import type { Account, Contact } from '@/types'

type CheckableContact = Contact & { checked: boolean }

const accounts = ref<Account[]>([])
const accountId = ref('')
const contacts = ref<CheckableContact[]>([])
const keyword = ref('')
const loading = ref(false)
const syncing = ref(false)
let timer: number | undefined

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return contacts.value
  return contacts.value.filter((c) => (c.name || '').toLowerCase().includes(kw))
})

const selectedCount = computed(() => contacts.value.filter((c) => c.checked).length)

async function loadAccounts() {
  const { data } = await listAccounts()
  accounts.value = data.accounts
  if (!accountId.value && data.accounts.length) accountId.value = data.accounts[0].id
}

async function loadContacts() {
  if (!accountId.value) return
  loading.value = true
  try {
    const [listResp, taskResp] = await Promise.all([
      listContacts(accountId.value),
      getTask(accountId.value)
    ])
    const friends = new Set(taskResp.data.friends || [])
    contacts.value = (listResp.data.contacts || []).map((c) => ({
      ...c,
      checked: friends.has(c.name)
    }))
    if (listResp.data.contacts_error) ElMessage.warning(listResp.data.contacts_error)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '加载联系人失败')
  } finally {
    loading.value = false
  }
}

async function doSync() {
  if (!accountId.value) return
  syncing.value = true
  try {
    await syncContacts(accountId.value)
    ElMessage.success('同步已启动')
    startPolling()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '同步失败')
    syncing.value = false
  }
}

function startPolling() {
  stopPolling()
  let ticks = 0
  timer = window.setInterval(async () => {
    ticks += 1
    try {
      const { data } = await listContacts(accountId.value)
      if (!data.fetching || ticks >= 30) {
        stopPolling()
        syncing.value = false
        await loadContacts()
        ElMessage.success(data.fetching && ticks >= 30 ? '同步仍在进行，已加载当前结果' : '联系人已更新')
      }
    } catch {
      stopPolling()
      syncing.value = false
    }
  }, 2000)
}

function stopPolling() {
  if (timer) {
    window.clearInterval(timer)
    timer = undefined
  }
}

async function applySelection() {
  if (!accountId.value) return
  const friends = contacts.value.filter((c) => c.checked).map((c) => c.name)
  await putTask(accountId.value, { friends })
}

async function onCheck(row: CheckableContact) {
  await applySelection()
  ElMessage.success(row.checked ? `已选择 ${row.name}` : `已取消 ${row.name}`)
}

async function selectAll() {
  contacts.value.forEach((c) => (c.checked = true))
  await applySelection()
  ElMessage.success('已全选')
}

async function clearAll() {
  contacts.value.forEach((c) => (c.checked = false))
  await applySelection()
  ElMessage.success('已清空选择')
}

watch(accountId, loadContacts)
onMounted(() => {
  loadAccounts()
})
onUnmounted(stopPolling)
</script>

<template>
  <div>
    <el-card style="margin-bottom: 16px">
      <el-form inline>
        <el-form-item label="抖音账号">
          <el-select v-model="accountId" style="width: 220px">
            <el-option v-for="a in accounts" :key="a.id" :label="a.name" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-button type="primary" :loading="syncing" @click="doSync">同步联系人</el-button>
        <el-input v-model="keyword" placeholder="搜索联系人" clearable style="width: 200px; margin-left: 12px" />
      </el-form>
    </el-card>

    <el-card>
      <template #header>
        <div class="toolbar">
          <span>聊天联系人</span>
          <div>
            <el-button link @click="selectAll">全选</el-button>
            <el-button link @click="clearAll">取消选择</el-button>
            <el-tag type="info" size="small">已选 {{ selectedCount }} / {{ contacts.length }}</el-tag>
          </div>
        </div>
      </template>
      <el-table v-loading="loading" :data="filtered" empty-text="暂未同步联系人">
        <el-table-column width="48">
          <template #default="{ row }">
            <el-checkbox v-model="row.checked" @change="onCheck(row)" />
          </template>
        </el-table-column>
        <el-table-column width="56">
          <template #default="{ row }">
            <el-avatar :size="36" :src="row.avatar" />
          </template>
        </el-table-column>
        <el-table-column prop="name" label="名称" min-width="160">
          <template #default="{ row }">{{ row.name }}</template>
        </el-table-column>
        <el-table-column label="火花" width="120">
          <template #default="{ row }">{{ row.streak || '—' }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.toolbar { display: flex; align-items: center; justify-content: space-between; }
.toolbar > div { display: flex; align-items: center; gap: 8px; }
</style>
