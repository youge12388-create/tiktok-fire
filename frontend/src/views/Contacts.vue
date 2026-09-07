<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Search, UserFilled } from '@element-plus/icons-vue'
import { listAccounts } from '@/api/accounts'
import { withAppBasePath } from '@/api/base'
import { listContacts, syncContacts } from '@/api/contacts'
import { getErrorMessage } from '@/api/errors'
import { getTask, putTask } from '@/api/tasks'
import type { Account, Contact } from '@/types'

type CheckableContact = Contact & { checked: boolean }

const accounts = ref<Account[]>([])
const accountId = ref('')
const contacts = ref<CheckableContact[]>([])
const keyword = ref('')
const loading = ref(false)
const syncing = ref(false)
const selectionSaving = ref(false)
let timer: number | undefined

const currentAccount = computed(() => accounts.value.find((account) => account.id === accountId.value))
const canSync = computed(() => Boolean(currentAccount.value?.enabled && currentAccount.value.state_file_exists))
const filtered = computed(() => {
  const search = keyword.value.trim().toLowerCase()
  if (!search) return contacts.value
  return contacts.value.filter((contact) => (contact.name || '').toLowerCase().includes(search))
})
const selectedCount = computed(() => contacts.value.filter((contact) => contact.checked).length)

function accountStatus(account?: Account) {
  if (!account) return { label: '未选择', type: 'info' }
  if (!account.enabled) return { label: '已停用', type: 'info' }
  if (!account.state_file_exists || ['unknown', 'expired', 'failed', 'invalid'].includes(account.session_status || '')) return { label: '需登录', type: 'danger' }
  return { label: '正常', type: 'success' }
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

async function loadContacts() {
  if (!accountId.value) {
    contacts.value = []
    return
  }
  loading.value = true
  try {
    const [listResponse, taskResponse] = await Promise.all([listContacts(accountId.value), getTask(accountId.value)])
    const selected = new Set(taskResponse.data.friends || [])
    contacts.value = (listResponse.data.contacts || []).map((contact) => ({ ...contact, checked: selected.has(contact.name) }))
    if (listResponse.data.contacts_error) ElMessage.warning(listResponse.data.contacts_error)
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '联系人加载失败，请稍后重试'))
  } finally {
    loading.value = false
  }
}

async function doSync() {
  if (!canSync.value) {
    ElMessage.warning('请先完成账号登录')
    return
  }
  syncing.value = true
  try {
    await syncContacts(accountId.value)
    ElMessage.success('正在同步联系人')
    startPolling()
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '联系人同步失败'))
    syncing.value = false
  }
}

function startPolling() {
  stopPolling()
  let attempts = 0
  timer = window.setInterval(async () => {
    attempts += 1
    try {
      const { data } = await listContacts(accountId.value)
      if (!data.fetching || attempts >= 30) {
        stopPolling()
        syncing.value = false
        await loadContacts()
        ElMessage.success(data.fetching ? '已显示当前同步结果' : '联系人同步完成')
      }
    } catch {
      stopPolling()
      syncing.value = false
      ElMessage.error('同步状态查询失败，请稍后重试')
    }
  }, 2000)
}

function stopPolling() {
  if (timer) {
    window.clearInterval(timer)
    timer = undefined
  }
}

async function saveSelection() {
  if (!accountId.value) return
  selectionSaving.value = true
  try {
    await putTask(accountId.value, { friends: contacts.value.filter((contact) => contact.checked).map((contact) => contact.name) })
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '联系人选择保存失败'))
    await loadContacts()
  } finally {
    selectionSaving.value = false
  }
}

async function selectAll() {
  contacts.value.forEach((contact) => (contact.checked = true))
  await saveSelection()
}

async function clearAll() {
  contacts.value.forEach((contact) => (contact.checked = false))
  await saveSelection()
}

watch(accountId, loadContacts)
onMounted(loadAccounts)
onUnmounted(stopPolling)
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div><h1 class="page-title">联系人</h1><p class="page-description">同步抖音会话，并勾选需要自动续火的联系人。</p></div>
      <div class="page-actions"><el-button type="primary" :icon="Refresh" :loading="syncing" :disabled="!canSync" @click="doSync">同步联系人</el-button></div>
    </div>

    <section class="surface">
      <div class="toolbar">
        <div class="account-field"><label class="field-label" for="contact-account">抖音账号</label><el-select id="contact-account" v-model="accountId" placeholder="选择账号"><el-option v-for="account in accounts" :key="account.id" :label="account.display_name || account.name" :value="account.id" /></el-select></div>
        <el-tag v-if="currentAccount" :type="accountStatus(currentAccount).type" size="small">{{ accountStatus(currentAccount).label }}</el-tag>
        <div class="search-field"><label class="field-label" for="contact-search">搜索</label><el-input id="contact-search" v-model="keyword" clearable placeholder="输入联系人名称" :prefix-icon="Search" /></div>
      </div>

      <div class="section-header">
        <div><h2 class="section-title">续火联系人</h2><p class="section-description">已选 {{ selectedCount }} / {{ contacts.length }}{{ selectionSaving ? ' · 正在保存' : '' }}</p></div>
        <div class="bulk-actions"><el-button text size="small" :disabled="!contacts.length || selectionSaving" @click="selectAll">全选</el-button><el-button text size="small" :disabled="!contacts.length || selectionSaving" @click="clearAll">清空</el-button></div>
      </div>

      <el-skeleton v-if="loading" :rows="6" animated class="loading-block" />
      <el-table v-else-if="filtered.length" :data="filtered">
        <el-table-column width="54"><template #default="{ row }"><el-checkbox v-model="row.checked" :disabled="selectionSaving" aria-label="选择联系人" @change="saveSelection" /></template></el-table-column>
        <el-table-column width="60"><template #default="{ row }"><el-avatar :size="36" :src="row.avatar ? withAppBasePath(row.avatar) : undefined"><el-icon><UserFilled /></el-icon></el-avatar></template></el-table-column>
        <el-table-column prop="name" label="联系人" min-width="180" />
        <el-table-column label="火花" width="120"><template #default="{ row }">{{ row.streak || '—' }}</template></el-table-column>
        <el-table-column label="任务状态" width="110"><template #default="{ row }"><el-tag v-if="row.checked" type="success" size="small">已加入</el-tag><span v-else class="muted-state">未选择</span></template></el-table-column>
      </el-table>

      <div v-else-if="!accountId" class="empty-panel"><el-icon><UserFilled /></el-icon><h3>请先选择账号</h3><p>选择一个已登录的账号后，可以同步联系人。</p><el-button @click="$router.push('/accounts')">去账号管理</el-button></div>
      <div v-else-if="!contacts.length" class="empty-panel"><el-icon><UserFilled /></el-icon><h3>还没有联系人</h3><p>{{ canSync ? '点击“同步联系人”获取抖音会话列表。' : '当前账号未登录，请先去账号管理完成登录。' }}</p><el-button v-if="canSync" type="primary" :icon="Refresh" @click="doSync">同步联系人</el-button><el-button v-else @click="$router.push('/accounts')">去登录账号</el-button></div>
      <div v-else class="empty-panel search-empty"><el-icon><Search /></el-icon><h3>没有找到联系人</h3><p>请更换关键词后重试。</p><el-button @click="keyword = ''">清除搜索</el-button></div>
    </section>
  </div>
</template>

<style scoped>
.account-field { width: 220px; }
.search-field { width: 220px; margin-left: auto; }
.bulk-actions { display: flex; gap: 2px; }
.loading-block { padding: 24px 20px; }
.muted-state { color: var(--color-text-secondary); font-size: 11px; }
.search-empty { min-height: 220px; }

@media (max-width: 640px) {
  .account-field, .search-field { width: 100%; margin-left: 0; }
  .toolbar > .el-tag { align-self: flex-start; }
}
</style>
