<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Refresh, Search, UserFilled } from '@element-plus/icons-vue'
import { listAccounts } from '@/api/accounts'
import { withAppBasePath } from '@/api/base'
import { deleteContacts, listContacts, setContactsSelection, syncContacts } from '@/api/contacts'
import { getErrorMessage } from '@/api/errors'
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
let contactsRequestId = 0

const currentAccount = computed(() => accounts.value.find((account) => account.id === accountId.value))
const canSync = computed(() => Boolean(
  currentAccount.value?.enabled
    && currentAccount.value.state_file_exists
    && !['expired', 'failed', 'invalid'].includes(currentAccount.value.session_status || '')
))
const filtered = computed(() => {
  const search = keyword.value.trim().toLowerCase()
  if (!search) return contacts.value
  return contacts.value.filter((contact) => (contact.name || '').toLowerCase().includes(search))
})
const selectedCount = computed(() => contacts.value.filter((contact) => contact.checked && !contact.identity_ambiguous).length)

function accountStatus(account?: Account) {
  if (!account) return { label: '未选择', type: 'info' }
  if (!account.enabled) return { label: '已停用', type: 'info' }
  if (!account.state_file_exists) return { label: '需登录', type: 'danger' }
  if (['expired', 'failed', 'invalid'].includes(account.session_status || '')) return { label: '需重新登录', type: 'danger' }
  if (account.session_status === 'unknown') return { label: '待检测', type: 'warning' }
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

async function loadContacts(requestedAccountId = accountId.value) {
  const requestId = ++contactsRequestId
  if (!requestedAccountId) {
    contacts.value = []
    loading.value = false
    return
  }
  loading.value = true
  try {
    const { data } = await listContacts(requestedAccountId)
    if (requestId !== contactsRequestId || accountId.value !== requestedAccountId) return
    contacts.value = (data.contacts || []).map((contact) => ({
      ...contact,
      checked: !!contact.selected && !contact.identity_ambiguous
    }))
    if (data.contacts_error) ElMessage.warning(data.contacts_error)
  } catch (error: unknown) {
    if (requestId !== contactsRequestId || accountId.value !== requestedAccountId) return
    ElMessage.error(getErrorMessage(error, '联系人加载失败，请稍后重试'))
  } finally {
    if (requestId === contactsRequestId) loading.value = false
  }
}

async function doSync() {
  if (!canSync.value) {
    ElMessage.warning('请先完成账号登录')
    return
  }
  const syncAccountId = accountId.value
  syncing.value = true
  try {
    await syncContacts(syncAccountId)
    if (accountId.value !== syncAccountId) return
    ElMessage.success('正在同步联系人')
    startPolling(syncAccountId)
  } catch (error: unknown) {
    if (accountId.value !== syncAccountId) return
    ElMessage.error(getErrorMessage(error, '联系人同步失败'))
    syncing.value = false
  }
}

function startPolling(pollingAccountId: string) {
  stopPolling()
  let attempts = 0
  timer = window.setInterval(async () => {
    if (accountId.value !== pollingAccountId) {
      stopPolling()
      syncing.value = false
      return
    }
    attempts += 1
    try {
      const { data } = await listContacts(pollingAccountId)
      if (accountId.value !== pollingAccountId) return
      if (!data.fetching || attempts >= 30) {
        stopPolling()
        syncing.value = false
        await loadContacts(pollingAccountId)
        if (accountId.value !== pollingAccountId) return
        ElMessage.success(data.fetching ? '已显示当前同步结果' : '联系人同步完成')
      }
    } catch {
      if (accountId.value !== pollingAccountId) return
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
    const names = contacts.value
      .filter((contact) => contact.checked && !contact.identity_ambiguous)
      .map((contact) => contact.name)
    await setContactsSelection(accountId.value, names)
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '联系人选择保存失败'))
    await loadContacts()
  } finally {
    selectionSaving.value = false
  }
}

async function selectAll() {
  contacts.value.forEach((contact) => {
    if (!contact.identity_ambiguous) contact.checked = true
  })
  await saveSelection()
}

async function clearAll() {
  contacts.value.forEach((contact) => (contact.checked = false))
  await saveSelection()
}

async function removeContact(contact: Contact) {
  if (!accountId.value) return
  try {
    await ElMessageBox.confirm(
      `确认删除联系人「${contact.name}」？删除后将不再参与自动续火花。`,
      '删除联系人',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  try {
    await deleteContacts(accountId.value, [contact.name])
    ElMessage.success('联系人已删除')
    await loadContacts()
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '联系人删除失败'))
  }
}

watch(accountId, (nextAccountId) => {
  stopPolling()
  syncing.value = false
  void loadContacts(nextAccountId)
})
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
        <el-table-column width="54"><template #default="{ row }"><el-checkbox v-model="row.checked" :disabled="selectionSaving || row.identity_ambiguous" :title="row.identity_ambiguous ? '同名联系人需先确认唯一会话' : undefined" aria-label="选择联系人" @change="saveSelection" /></template></el-table-column>
        <el-table-column width="60"><template #default="{ row }"><el-avatar :size="36" :src="row.avatar ? withAppBasePath(row.avatar) : undefined"><el-icon><UserFilled /></el-icon></el-avatar></template></el-table-column>
        <el-table-column prop="name" label="联系人" min-width="180" />
        <el-table-column label="火花" width="120"><template #default="{ row }">{{ row.streak || '—' }}</template></el-table-column>
        <el-table-column label="任务状态" width="130"><template #default="{ row }"><el-tag v-if="row.identity_ambiguous" type="warning" size="small">同名待确认</el-tag><el-tag v-else-if="row.checked" type="success" size="small">已加入</el-tag><span v-else class="muted-state">未选择</span></template></el-table-column>
        <el-table-column label="操作" width="72" align="center"><template #default="{ row }"><el-button text type="danger" :icon="Delete" aria-label="删除联系人" :disabled="selectionSaving" @click="removeContact(row)" /></template></el-table-column>
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
