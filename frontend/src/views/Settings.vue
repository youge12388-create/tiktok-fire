<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Bell, CircleCheck, InfoFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'
import { getErrorMessage } from '@/api/errors'

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
const notificationConfigured = ref(false)
const notificationLoading = ref(true)
const notificationError = ref('')
const notificationTesting = ref(false)

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
    const { data } = await http.get<{ dingtalk?: { configured?: boolean } }>('/system/notifications/status')
    notificationConfigured.value = Boolean(data.dingtalk?.configured)
  } catch (error: unknown) {
    notificationError.value = getErrorMessage(error, '无法读取钉钉告警状态')
  } finally {
    notificationLoading.value = false
  }
}

async function testDingtalk() {
  notificationTesting.value = true
  try {
    const { data } = await http.post<{ message?: string }>('/system/notifications/test')
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
          <p>账号确认退出时，通过钉钉机器人发送一次告警。</p>
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
        <el-skeleton :rows="1" animated />
      </div>
      <el-alert
        v-else-if="notificationError"
        class="notification-alert"
        type="error"
        :title="notificationError"
        :closable="false"
        show-icon
      />
      <div v-else class="notification-action">
        <div class="signal-line" :class="{ 'is-ready': notificationConfigured }" aria-hidden="true">
          <i />
          <span>{{ notificationConfigured ? 'DINGTALK ALERT READY' : 'DINGTALK ALERT OFFLINE' }}</span>
        </div>
        <p v-if="notificationConfigured">发送一条测试消息，确认机器人、加签密钥和群消息接收都正常。</p>
        <p v-else>请先在服务器环境变量中配置钉钉 Webhook 地址和加签密钥，然后重启服务。</p>
        <el-button
          type="primary"
          :loading="notificationTesting"
          :disabled="!notificationConfigured"
          @click="testDingtalk"
        >
          发送测试消息
        </el-button>
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
.notification-action p {
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
.notification-action {
  margin-top: 20px;
  padding-top: 18px;
  border-top: 1px solid var(--color-border);
}

.notification-action {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
  column-gap: 24px;
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

  .notification-action {
    grid-template-columns: 1fr;
  }

  .notification-action .el-button {
    width: 100%;
    margin-top: 16px;
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
