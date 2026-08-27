<script setup lang="ts">
import { onMounted, ref } from 'vue'
import http from '@/api/http'

const summary = ref<any>(null)

onMounted(async () => {
  try {
    const { data } = await http.get('/system/summary')
    summary.value = data
  } catch {
    /* 未登录或后端不可用时保持占位 */
  }
})

function fmtUptime(sec?: number) {
  if (sec == null) return '—'
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  return h > 0 ? `${h}小时 ${m}分` : `${m}分钟`
}
</script>

<template>
  <el-row :gutter="16">
    <el-col :xs="24" :sm="12">
      <el-card header="运行信息">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="版本">{{ summary?.version ?? '1.0.0' }}</el-descriptions-item>
          <el-descriptions-item label="运行时间">{{ fmtUptime(summary?.uptime_seconds) }}</el-descriptions-item>
          <el-descriptions-item label="并发上限">{{ summary?.max_concurrent ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="可用浏览器名额">{{ summary?.browser_slots_available ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="账号总数">{{ summary?.accounts?.total ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="启用 / 停用">{{ summary?.accounts?.enabled ?? 0 }} / {{ summary?.accounts?.disabled ?? 0 }}</el-descriptions-item>
        </el-descriptions>
      </el-card>
    </el-col>
    <el-col :xs="24" :sm="12">
      <el-card header="系统说明">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="运行模式">单管理员模式</el-descriptions-item>
          <el-descriptions-item label="数据库">SQLite（data/app.db）</el-descriptions-item>
          <el-descriptions-item label="数据目录">data/accounts/（每账号独立 state/config/台账）</el-descriptions-item>
          <el-descriptions-item label="生产部署">建议 Nginx + HTTPS + Docker，8000 仅绑定 127.0.0.1</el-descriptions-item>
          <el-descriptions-item label="敏感信息">Cookie / Storage State / 密码不出现在日志与 Git</el-descriptions-item>
        </el-descriptions>
      </el-card>
    </el-col>
  </el-row>
</template>
