<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Refresh, Search, UserFilled } from '@element-plus/icons-vue'
import { listAccounts } from '@/api/accounts'
import { withAppBasePath } from '@/api/base'
import { continueSyncContacts, deleteAllContacts, deleteContacts, listContacts, setContactsSelection, syncContacts } from '@/api/contacts'
import { getErrorMessage } from '@/api/errors'
import { getReconcile, retryRun } from '@/api/tasks'
import { statusMeta } from '@/composables/useReconcile'
import type { Account, Contact } from '@/types'

type CheckableContact = Contact & { checked: boolean }

const accounts = ref<Account[]>([])
const accountId = ref('')
const contacts = ref<CheckableContact[]>([])
const keyword = ref('')
const loading = ref(false)
const syncing = ref(false)
const deletingAll = ref(false)
const selectionSaving = ref(false)
const retrying = ref('')
const syncSummary = ref<{ complete?: boolean | null; warning?: string | null }>({})
const todayCounts = ref<{ succeeded: number; failed: number; uncertain: number; skipped: number; pending: number } | null>(null)
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
const selectedCount = computed(() => contacts.value.filter((contact) => contact.checked).length)
const selectedContacts = computed(() => contacts.value.filter((contact) => contact.checked))
const syncStatus = computed(() => {
  if (syncSummary.value.complete === true) return ' · 已完整同步'
  if (syncSummary.value.complete === false) return ' · 同步未确认完整，可继续补充扫描'
  return ''
})
const needsSupplement = computed(() => Boolean(canSync.value && syncSummary.value.complete === false))

/** 今日核对摘要：只统计当前勾选的人。 */
const todaySummary = computed(() => {
  const counts = todayCounts.value
  if (!counts || !selectedCount.value) return ''
  if (!counts.succeeded && !counts.failed && !counts.uncertain && !counts.skipped) return ' · 今日尚未执行'
  const parts = [`今日成功 ${counts.succeeded}/${selectedCount.value}`]
  if (counts.failed) parts.push(`${counts.failed} 人失败`)
  if (counts.uncertain) parts.push(`${counts.uncertain} 人待确认`)
  if (counts.skipped) parts.push(`${counts.skipped} 人跳过`)
  if (counts.pending) parts.push(`${counts.pending} 人未执行`)
  return ` · ${parts.join('，')}`
})
const retryableCount = computed(() => selectedContacts.value.filter((c) => c.today_status === 'failed').length)
const canRetry = computed(() => Boolean(currentAccount.value?.enabled && currentAccount.value.session_status === 'ok' && !currentAccount.value.running))

function accountStatus(account?: Account) {
  if (!account) return { label: '未选择', type: 'info' }
  if (!account.enabled) return { label: '已停用', type: 'info' }
  if (!account.state_file_exists) return { label: '需登录', type: 'danger' }
  if (['expired', 'failed', 'invalid'].includes(account.session_status || '')) return { label: '需重新登录', type: 'danger' }
  if (account.session_status === 'unknown') return { label: '待检测', type: 'warning' }
  return { label: '正常', type: 'success' }
}

/** 未勾选的人不参与今日核对，避免误导。 */
function todayStatus(contact: CheckableContact) {
  if (!contact.checked) return null
  return statusMeta(contact.today_status ?? undefined)
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
    todayCounts.value = null
    loading.value = false
    return
  }
  loading.value = true
  try {
    const { data } = await listContacts(requestedAccountId)
    if (requestId !== contactsRequestId || accountId.value !== requestedAccountId) return
    contacts.value = (data.contacts || []).map((contact) => ({
      ...contact,
      checked: !!contact.selected
    }))
    todayCounts.value = data.today_counts || null
    syncSummary.value = {
      complete: data.contacts_complete,
      warning: data.contacts_warning
    }
    if (data.contacts_error) ElMessage.warning(data.contacts_error)
    if (data.contacts_warning) ElMessage.warning(data.contacts_warning)
  } catch (error: unknown) {
    if (requestId !== contactsRequestId || accountId.value !== requestedAccountId) return
    ElMessage.error(getErrorMessage(error, '联系人加载失败，请稍后重试'))
  } finally {
    if (requestId === contactsRequestId) loading.value = false
  }
}

async function refreshTodayStatus() {
  loadContacts()
}

async function doSync(mode: 'initial' | 'supplement' = 'initial') {
  if (!canSync.value) {
    ElMessage.warning('请先完成账号登录')
    return
  }
  const syncAccountId = accountId.value
  syncing.value = true
  try {
    if (mode === 'supplement') await continueSyncContacts(syncAccountId)
    else await syncContacts(syncAccountId)
    if (accountId.value !== syncAccountId) return
    ElMessage.success(mode === 'supplement' ? '正在补充扫描联系人' : '正在同步联系人')
    startPolling(syncAccountId, mode)
  } catch (error: unknown) {
    if (accountId.value !== syncAccountId) return
    ElMessage.error(getErrorMessage(error, '联系人同步失败'))
    syncing.value = false
  }
}

function startPolling(pollingAccountId: string, mode: 'initial' | 'supplement') {
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
      if (!data.fetching) {
        stopPolling()
        syncing.value = false
        await loadContacts(pollingAccountId)
        if (accountId.value !== pollingAccountId) return
        if (data.contacts_complete === false) {
          ElMessage.warning(mode === 'supplement'
            ? '补充扫描结束但仍未确认完整，已保留结果，可继续补充扫描'
            : '同步结束但未确认完整，已保留结果，可继续补充扫描')
        } else {
          ElMessage.success('联系人同步完成')
        }
      } else if (attempts >= 180) {
        stopPolling()
        syncing.value = false
        ElMessage.warning('同步仍在后台进行，请稍后刷新页面查看进度')
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
  if (!accountId.value || syncing.value || deletingAll.value) return
  selectionSaving.value = true
  try {
    const names = contacts.value
      .filter((contact) => contact.checked)
      .map((contact) => contact.name)
    const contactKeys = contacts.value
      .filter((contact) => contact.checked)
      .map((contact) => contact.id)
    await setContactsSelection(accountId.value, names, contactKeys)
    await refreshTodayStatus()
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

/** 补发：只给指定的人重发；不传名单时补发今日确定失败且已勾选的人。 */
async function retryFailed(names?: string[]) {
  if (!accountId.value || retrying.value) return
  if (!canRetry.value) {
    ElMessage.warning('账号未登录或正在执行，无法补发')
    return
  }
  const { data: report } = await getReconcile(accountId.value).catch(() => ({ data: null }))
  const targets = names?.length ? names : (report?.retry_names ?? []).filter((name) => contacts.value.some((c) => c.name === name && c.checked))
  if (!targets.length) {
    ElMessage.info('今日没有确定失败的联系人需要补发')
    return
  }
  const preview = targets.slice(0, 5).join('、')
  try {
    await ElMessageBox.confirm(
      `将只给「${targets.length} 位」续火失败的联系人重发一次：${preview}${targets.length > 5 ? ' …' : ''}。\n已成功的人不会被重复发送。`,
      '确认补发',
      { type: 'warning', confirmButtonText: '确认补发', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  retrying.value = names?.[0] || '__all__'
  try {
    const { data } = await retryRun(accountId.value, names)
    ElMessage.success(`已开始补发 ${data.count} 人`)
    await loadContacts()
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '补发启动失败'))
  } finally {
    retrying.value = ''
  }
}

async function removeContact(contact: Contact) {
  if (!accountId.value || syncing.value || deletingAll.value) return
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
    await deleteContacts(accountId.value, [], [contact.id])
    ElMessage.success('联系人已删除')
    await loadContacts()
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '联系人删除失败'))
  }
}

async function removeAllContacts() {
  if (!accountId.value || !contacts.value.length || syncing.value || deletingAll.value) return
  try {
    await ElMessageBox.confirm(
      `确认删除当前账号下的全部 ${contacts.value.length} 位联系人？删除后将不再参与自动续火花。`,
      '删除全部联系人',
      { type: 'warning', confirmButtonText: '全部删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  deletingAll.value = true
  try {
    const { data } = await deleteAllContacts(accountId.value)
    ElMessage.success(`已删除 ${data.removed ?? contacts.value.length} 位联系人`)
    await loadContacts()
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '全部联系人删除失败'))
  } finally {
    deletingAll.value = false
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
      <div class="page-actions">
        <el-button v-if="needsSupplement" type="primary" :icon="Refresh" :loading="syncing" :disabled="!canSync" @click="doSync('supplement')">继续补充扫描</el-button>
        <el-button :type="needsSupplement ? 'default' : 'primary'" :icon="Refresh" :loading="syncing" :disabled="!canSync" @click="doSync('initial')">{{ needsSupplement ? '重新同步' : '同步联系人' }}</el-button>
      </div>
    </div>

    <section class="surface">
      <div class="toolbar">
        <div class="account-field"><label class="field-label" for="contact-account">抖音账号</label><el-select id="contact-account" v-model="accountId" placeholder="选择账号"><el-option v-for="account in accounts" :key="account.id" :label="account.display_name || account.name" :value="account.id" /></el-select></div>
        <el-tag v-if="currentAccount" :type="accountStatus(currentAccount).type" size="small">{{ accountStatus(currentAccount).label }}</el-tag>
        <div class="search-field"><label class="field-label" for="contact-search">搜索</label><el-input id="contact-search" v-model="keyword" clearable placeholder="输入联系人名称" :prefix-icon="Search" /></div>
      </div>

      <div class="section-header">
        <div><h2 class="section-title">续火联系人</h2><p class="section-description">已选 {{ selectedCount }} / {{ contacts.length }}{{ selectionSaving ? ' · 正在保存' : '' }}{{ todaySummary || syncStatus }}</p></div>
        <div class="bulk-actions">
          <el-button v-if="retryableCount" text type="primary" size="small" :loading="retrying === '__all__'" :disabled="!canRetry" @click="retryFailed()">补发失败 ({{ retryableCount }})</el-button>
          <el-button text size="small" :disabled="!contacts.length || selectionSaving || syncing || deletingAll" @click="selectAll">全选</el-button>
          <el-button text size="small" :disabled="!contacts.length || selectionSaving || syncing || deletingAll" @click="clearAll">清空</el-button>
          <el-button text type="danger" size="small" :loading="deletingAll" :disabled="!contacts.length || selectionSaving || syncing" @click="removeAllContacts">删除全部</el-button>
        </div>
      </div>

      <el-skeleton v-if="loading" :rows="6" animated class="loading-block" />
      <el-table v-else-if="filtered.length" :data="filtered">
        <el-table-column width="54"><template #default="{ row }"><el-checkbox v-model="row.checked" :disabled="selectionSaving || syncing || deletingAll" aria-label="选择联系人" @change="saveSelection" /></template></el-table-column>
        <el-table-column width="60"><template #default="{ row }"><el-avatar :size="36" :src="row.avatar ? withAppBasePath(row.avatar) : undefined"><el-icon><UserFilled /></el-icon></el-avatar></template></el-table-column>
        <el-table-column prop="name" label="联系人" min-width="180" />
        <el-table-column label="火花" width="120"><template #default="{ row }">{{ row.streak || '—' }}</template></el-table-column>
        <el-table-column label="任务状态" width="130"><template #default="{ row }"><el-tag v-if="row.checked" type="success" size="small">已加入</el-tag><span v-else class="muted-state">未选择</span></template></el-table-column>
        <el-table-column label="今日结果" width="150">
          <template #default="{ row }">
            <template v-if="todayStatus(row)">
              <el-tooltip v-if="row.today_reason" :content="row.today_reason" placement="top">
                <el-tag :type="todayStatus(row)!.tag" size="small">{{ todayStatus(row)!.label }}</el-tag>
              </el-tooltip>
              <el-tag v-else :type="todayStatus(row)!.tag" size="small">{{ todayStatus(row)!.label }}</el-tag>
            </template>
            <span v-else class="muted-state">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="132" align="center">
          <template #default="{ row }">
            <el-button
              v-if="row.checked && todayStatus(row)?.retryable"
              text
              type="primary"
              size="small"
              :loading="retrying === row.name"
              :disabled="!canRetry"
              @click="retryFailed([row.name])"
            >
              补发
            </el-button>
            <el-button text type="danger" :icon="Delete" aria-label="删除联系人" :disabled="selectionSaving || syncing || deletingAll" @click="removeContact(row)" />
          </template>
        </el-table-column>
      </el-table>

      <div v-else-if="!accountId" class="empty-panel"><el-icon><UserFilled /></el-icon><h3>请先选择账号</h3><p>选择一个已登录的账号后，可以同步联系人。</p><el-button @click="$router.push('/accounts')">去账号管理</el-button></div>
      <div v-else-if="!contacts.length" class="empty-panel"><el-icon><UserFilled /></el-icon><h3>还没有联系人</h3><p>{{ canSync ? (needsSupplement ? '本次扫描未确认完整，可以继续补充扫描。' : '点击“同步联系人”获取抖音会话列表。') : '当前账号未登录，请先去账号管理完成登录。' }}</p><div v-if="canSync" class="empty-actions"><el-button v-if="needsSupplement" type="primary" :icon="Refresh" @click="doSync('supplement')">继续补充扫描</el-button><el-button :type="needsSupplement ? 'default' : 'primary'" :icon="Refresh" @click="doSync('initial')">{{ needsSupplement ? '重新同步' : '同步联系人' }}</el-button></div><el-button v-else @click="$router.push('/accounts')">去登录账号</el-button></div>
      <div v-else class="empty-panel search-empty"><el-icon><Search /></el-icon><h3>没有找到联系人</h3><p>请更换关键词后重试。</p><el-button @click="keyword = ''">清除搜索</el-button></div>
    </section>
  </div>
</template>

<style scoped>
.account-field { width: 220px; }
.search-field { width: 220px; margin-left: auto; }
.bulk-actions { display: flex; gap: 2px; }
.empty-actions { display: flex; gap: 8px; }
.loading-block { padding: 24px 20px; }
.muted-state { color: var(--color-text-secondary); font-size: 11px; }
.search-empty { min-height: 220px; }

@media (max-width: 640px) {
  .account-field, .search-field { width: 100%; margin-left: 0; }
  .toolbar > .el-tag { align-self: flex-start; }
}
</style>
