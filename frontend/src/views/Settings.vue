<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { CircleCheck, InfoFilled } from '@element-plus/icons-vue'
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

onMounted(() => void load())
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

      <template v-else>
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

  .info-list {
    grid-template-columns: 1fr;
  }

  .info-list > div {
    padding-right: 0;
    padding-left: 0;
  }
}
</style>
