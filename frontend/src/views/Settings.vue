<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Bell, CircleCheck, InfoFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/api/http'
import { getErrorMessage } from '@/api/errors'
import { getNotificationStatus, testNotification, updateNotificationConfig } from '@/api/system'
import type { NotificationStatus } from '@/api/system'

interface Summary {
  version?: string
  uptime_seconds?: number
  max_concurrent?: number
  browser_slots_available?: number
  accounts?: { total?: number; enabled?: number; disabled?: number }
}

const summary = ref<Summary | null>(null)
const loading = ref(true)
const errorMessage = ref('')
const notification = ref<NotificationStatus | null>(null)
const notificationLoading = ref(true)
const notificationError = ref('')
const notificationTesting = ref(false)
const savingNotification = ref(false)
const form = reactive({ webhook_url: '', secret: '' })

const notificationConfigured = computed(() => Boolean(notification.value?.configured))
const sourceLabel = computed(() => {
  if (notification.value?.source === 'settings') return '已在后台保存，优先于环境变量'
  if (notification.value?.source === 'env') return '来自服务器环境变量（可在下方覆盖）'
  return '尚未配置'
})
/** 地址留空的提示：接口只返回脱敏地址，不能把它当新值提交。 */
const webhookPlaceholder = computed(() => (notification.value?.webhook_url
  ? `当前：${notification.value.webhook_url}（留空则不修改）`
  : 'https://oapi.dingtalk.com/robot/send?access_token=...'))

function fmtUptime(seconds?: number) {
  if (seconds == null) return '—'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  return hours > 0 ? `${hours} 小时 ${minutes} 分钟` : `${minutes} 分钟`
}

async function load() {
  loading.value = true
  errorMessage.value = ''
  try {
    const { data } = await http.get<Summary>('/system/summary')
    summary.value = data
  } catch (error: unknown) {
    errorMessage.value = getErrorMessage(error, '系统信息加载失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

async function loadNotificationStatus() {
  notificationLoading.value = true
  notificationError.value = ''
  try {
    const { data } = await getNotificationStatus()
    notification.value = data.dingtalk
    // 地址与密钥都不回显：留空保存即保持原值，避免把脱敏值写回真正的配置。
    form.webhook_url = ''
    form.secret = ''
  } catch (error: unknown) {
    notificationError.value = getErrorMessage(error, '无法读取钉钉告警状态')
  } finally {
    notificationLoading.value = false
  }
}

async function saveDingtalk() {
  const webhook = form.webhook_url.trim()
  if (!webhook && !notification.value?.webhook_url) {
    ElMessage.warning('请填写钉钉机器人 Webhook 地址')
    return
  }
  savingNotification.value = true
  try {
    const { data } = await updateNotificationConfig({
      webhook_url: webhook || undefined,
      secret: form.secret.trim() || undefined
    })
    notification.value = data.dingtalk
    form.webhook_url = ''
    form.secret = ''
    ElMessage.success('钉钉配置已保存，建议发送一条测试消息确认')
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '钉钉配置保存失败'))
  } finally {
    savingNotification.value = false
  }
}

async function clearDingtalk() {
  try {
    await ElMessageBox.confirm('将清除后台保存的钉钉配置，回退到服务器环境变量。', '清除配置', {
      type: 'warning',
      confirmButtonText: '清除',
      cancelButtonText: '取消'
    })
  } catch {
    return
  }
  savingNotification.value = true
  try {
    const { data } = await updateNotificationConfig({ clear: true })
    notification.value = data.dingtalk
    form.webhook_url = ''
    form.secret = ''
    ElMessage.success('已清除后台配置')
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '清除配置失败'))
  } finally {
    savingNotification.value = false
  }
}

async function testDingtalk() {
  notificationTesting.value = true
  try {
    const { data } = await testNotification()
    ElMessage.success(data.message || '测试消息已发送，请检查钉钉群')
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '钉钉测试消息发送失败'))
  } finally {
    notificationTesting.value = false
  }
}

onMounted(() => {
  void load()
  void loadNotificationStatus()
})
</script>

<template>
  <div class="page settings-page">
    <header class="page-header">
      <div>
        <h1 class="page-title">系统信息</h1>
        <p class="page-description">查看服务是否正常，以及当前可用资源。</p>
      </div>
    </header>

    <el-alert
      v-if="errorMessage"
      class="page-alert"
      type="error"
      :title="errorMessage"
      show-icon
      :closable="false"
    >
      <template #default>
        <el-button link type="primary" @click="load">重新加载</el-button>
      </template>
    </el-alert>

    <section class="surface system-surface">
      <template v-if="loading">
        <el-skeleton :rows="5" animated />
      </template>

      <template v-else-if="summary">
        <div class="service-status">
          <span class="status-icon"><el-icon><CircleCheck /></el-icon></span>
          <div>
            <h2>服务运行正常</h2>
            <p>已连续运行 {{ fmtUptime(summary?.uptime_seconds) }}</p>
          </div>
          <el-tag type="success" effect="light">在线</el-tag>
        </div>

        <dl class="info-list">
          <div>
            <dt>已启用账号</dt>
            <dd>{{ summary?.accounts?.enabled ?? 0 }} 个</dd>
          </div>
          <div>
            <dt>已停用账号</dt>
            <dd>{{ summary?.accounts?.disabled ?? 0 }} 个</dd>
          </div>
          <div>
            <dt>当前可用任务名额</dt>
            <dd>{{ summary?.browser_slots_available ?? '—' }} 个</dd>
          </div>
          <div>
            <dt>同时执行上限</dt>
            <dd>{{ summary?.max_concurrent ?? '—' }} 个</dd>
          </div>
        </dl>

        <el-collapse class="technical-info">
          <el-collapse-item name="details">
            <template #title>
              <span class="collapse-title"><el-icon><InfoFilled /></el-icon>技术信息</span>
            </template>
            <dl class="technical-list">
              <div><dt>服务版本</dt><dd>v{{ summary?.version ?? '1.0.0' }}</dd></div>
              <div><dt>账号数据</dt><dd><code>data/accounts/</code></dd></div>
              <div><dt>数据库</dt><dd><code>data/app.db</code></dd></div>
            </dl>
            <p class="deployment-note">部署到公网时，请使用 HTTPS，并避免直接暴露应用端口。</p>
          </el-collapse-item>
        </el-collapse>
      </template>
      <div v-else class="empty-panel status-unavailable">
        <el-icon><InfoFilled /></el-icon>
        <h3>暂时无法读取服务状态</h3>
        <p>请确认后端服务和网络连接正常后重试。</p>
        <el-button type="primary" @click="load">重新加载</el-button>
      </div>
    </section>

    <section class="surface notification-surface" aria-labelledby="notification-title">
      <div class="notification-heading">
        <span class="notification-icon"><el-icon><Bell /></el-icon></span>
        <div>
          <h2 id="notification-title">账号掉线通知</h2>
          <p>账号确认退出时，通过钉钉机器人发送一次告警。可直接在下方修改机器人配置。</p>
        </div>
        <el-tag
          v-if="!notificationLoading && !notificationError"
          :type="notificationConfigured ? 'success' : 'warning'"
          effect="light"
        >
          {{ notificationConfigured ? '通道已配置' : '尚未配置' }}
        </el-tag>
      </div>

      <div v-if="notificationLoading" class="notification-loading">
        <el-skeleton :rows="3" animated />
      </div>
      <el-alert
        v-else-if="notificationError"
        class="notification-alert"
        type="error"
        :title="notificationError"
        :closable="false"
        show-icon
      />
      <div v-else class="notification-body">
        <div class="signal-line" :class="{ 'is-ready': notificationConfigured }" aria-hidden="true">
          <i />
          <span>{{ notificationConfigured ? 'DINGTALK ALERT READY' : 'DINGTALK ALERT OFFLINE' }}</span>
        </div>

        <el-form label-position="top" class="notification-form" @submit.prevent>
          <el-form-item label="机器人 Webhook 地址">
            <el-input
              v-model="form.webhook_url"
              type="password"
              show-password
              autocomplete="off"
              :placeholder="webhookPlaceholder"
            />
            <p class="field-help">从钉钉群机器人设置页复制完整地址（必须包含 access_token）。出于安全考虑，地址与密钥都不会回显；留空保存表示不修改。</p>
          </el-form-item>
          <el-form-item label="加签密钥">
            <el-input
              v-model="form.secret"
              type="password"
              show-password
              autocomplete="new-password"
              :placeholder="notification?.secret_set ? '已设置，留空表示不修改' : '填写机器人「加签」安全设置里的密钥'"
            />
            <p class="field-help">留空保存时保持原密钥不变。</p>
          </el-form-item>
        </el-form>

        <p class="config-source">当前来源：{{ sourceLabel }}</p>
        <p class="notification-hint">
          {{ notificationConfigured
            ? '保存后建议发送一条测试消息，确认机器人、加签密钥和群消息接收都正常。'
            : '填写地址和加签密钥并保存后即可发送测试消息。' }}
        </p>

        <div class="notification-actions">
          <el-button v-if="notification?.source === 'settings'" @click="clearDingtalk">清除后台配置</el-button>
          <el-button :loading="savingNotification" @click="saveDingtalk">保存配置</el-button>
          <el-button
            type="primary"
            :loading="notificationTesting"
            :disabled="!notificationConfigured"
            @click="testDingtalk"
          >
            发送测试消息
          </el-button>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.settings-page {
  max-width: 840px;
}

.system-surface {
  padding: 24px;
}

.notification-surface {
  margin-top: 16px;
  padding: 24px;
}

.notification-heading {
  display: flex;
  align-items: center;
  gap: 14px;
}

.notification-heading h2 {
  margin: 0;
  font-size: 17px;
}

.notification-heading p,
.notification-body p {
  margin: 5px 0 0;
  color: var(--color-text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.notification-heading .el-tag {
  margin-left: auto;
}

.notification-icon {
  display: grid;
  width: 40px;
  height: 40px;
  flex: 0 0 40px;
  place-items: center;
  border-radius: 10px;
  color: var(--color-primary);
  background: var(--color-primary-soft);
  font-size: 20px;
}

.notification-loading,
.notification-alert,
.notification-body {
  margin-top: 20px;
  padding-top: 18px;
  border-top: 1px solid var(--color-border);
}

.notification-body {
  display: grid;
  gap: 4px;
}

.notification-form {
  margin-top: 14px;
}

.notification-form :deep(.el-input) {
  max-width: 520px;
}

.field-help,
.config-source {
  margin: 6px 0 0;
  color: var(--color-text-tertiary);
  font-size: 12px;
  line-height: 1.6;
}

.notification-hint {
  margin-top: 2px;
}

.notification-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.signal-line {
  display: inline-flex;
  grid-column: 1 / -1;
  align-items: center;
  gap: 8px;
  color: var(--color-warning);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 10px;
  letter-spacing: 0.08em;
}

.signal-line i {
  width: 7px;
  height: 7px;
  background: currentcolor;
  box-shadow: 10px 0 0 color-mix(in srgb, currentcolor 45%, transparent);
}

.signal-line.is-ready {
  color: var(--color-success);
}

.service-status {
  display: flex;
  align-items: center;
  gap: 14px;
  padding-bottom: 24px;
  border-bottom: 1px solid var(--color-border);
}

.status-icon {
  display: grid;
  width: 40px;
  height: 40px;
  flex: 0 0 40px;
  place-items: center;
  border-radius: 50%;
  color: var(--color-success);
  background: var(--color-success-soft);
  font-size: 21px;
}

.service-status h2 {
  margin: 0;
  font-size: 17px;
}

.service-status p {
  margin: 5px 0 0;
  color: var(--color-text-secondary);
  font-size: 13px;
}

.service-status .el-tag {
  margin-left: auto;
}

.info-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin: 8px 0 24px;
}

.info-list > div {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 24px;
  padding: 16px 12px;
  border-bottom: 1px solid var(--color-border);
}

.info-list dt,
.technical-list dt {
  color: var(--color-text-secondary);
  font-size: 13px;
}

.info-list dd,
.technical-list dd {
  margin: 0;
  color: var(--color-text);
  font-size: 14px;
  font-weight: 600;
}

.technical-info {
  border-top: 0;
}

.collapse-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--color-text-secondary);
  font-size: 13px;
}

.technical-list {
  margin: 0;
}

.technical-list > div {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  padding: 8px 0;
}

code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
}

.deployment-note {
  margin: 12px 0 0;
  padding: 12px;
  border-radius: 8px;
  color: var(--color-text-secondary);
  background: var(--color-bg);
  font-size: 12px;
  line-height: 1.6;
}

@media (max-width: 640px) {
  .system-surface {
    padding: 20px 16px;
  }

  .notification-surface {
    padding: 20px 16px;
  }

  .notification-heading {
    align-items: flex-start;
  }

  .notification-heading .el-tag {
    flex: 0 0 auto;
  }

  .notification-form :deep(.el-input) {
    max-width: none;
  }

  .notification-actions {
    flex-direction: column;
  }

  .notification-actions .el-button {
    width: 100%;
    margin-left: 0;
  }

  .info-list {
    grid-template-columns: 1fr;
  }

  .info-list > div {
    padding-right: 0;
    padding-left: 0;
  }
}
</style>
