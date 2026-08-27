<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import {
  Document,
  Menu,
  Message,
  Odometer,
  Setting,
  SwitchButton,
  Timer,
  User
} from '@element-plus/icons-vue'

const route = useRoute()
const auth = useAuthStore()
const isMobile = ref(false)
const drawerOpen = ref(false)

function onResize() {
  isMobile.value = window.innerWidth < 992
}

onMounted(() => {
  onResize()
  window.addEventListener('resize', onResize)
})
onUnmounted(() => window.removeEventListener('resize', onResize))
</script>

<template>
  <el-container class="layout">
    <el-aside v-if="!isMobile" width="220px" class="aside">
      <div class="brand">抖音私信助手</div>
      <el-menu :default-active="route.path" router class="menu">
        <el-menu-item index="/dashboard"><el-icon><Odometer /></el-icon><span>仪表盘</span></el-menu-item>
        <el-menu-item index="/accounts"><el-icon><User /></el-icon><span>抖音账号</span></el-menu-item>
        <el-menu-item index="/contacts"><el-icon><Message /></el-icon><span>好友管理</span></el-menu-item>
        <el-menu-item index="/tasks"><el-icon><Timer /></el-icon><span>续火任务</span></el-menu-item>
        <el-menu-item index="/logs"><el-icon><Document /></el-icon><span>执行日志</span></el-menu-item>
        <el-menu-item index="/settings"><el-icon><Setting /></el-icon><span>系统设置</span></el-menu-item>
      </el-menu>
    </el-aside>

    <el-drawer v-model="drawerOpen" direction="ltr" size="230px" :with-header="false" class="drawer">
      <div class="brand">抖音私信助手</div>
      <el-menu :default-active="route.path" router class="menu" @select="drawerOpen = false">
        <el-menu-item index="/dashboard"><el-icon><Odometer /></el-icon><span>仪表盘</span></el-menu-item>
        <el-menu-item index="/accounts"><el-icon><User /></el-icon><span>抖音账号</span></el-menu-item>
        <el-menu-item index="/contacts"><el-icon><Message /></el-icon><span>好友管理</span></el-menu-item>
        <el-menu-item index="/tasks"><el-icon><Timer /></el-icon><span>续火任务</span></el-menu-item>
        <el-menu-item index="/logs"><el-icon><Document /></el-icon><span>执行日志</span></el-menu-item>
        <el-menu-item index="/settings"><el-icon><Setting /></el-icon><span>系统设置</span></el-menu-item>
      </el-menu>
    </el-drawer>

    <el-container>
      <el-header class="header">
        <div class="header-left">
          <el-button v-if="isMobile" text class="burger" @click="drawerOpen = true">
            <el-icon size="22"><Menu /></el-icon>
          </el-button>
          <span class="title">抖音私信自动化助手 V1</span>
        </div>
        <div class="user">
          <span>{{ auth.username }}</span>
          <el-button link type="danger" @click="auth.logout()">
            <el-icon><SwitchButton /></el-icon><span>退出</span>
          </el-button>
        </div>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.layout { height: 100vh; }
.aside { background: #0f172a; color: #e2e8f0; }
.brand { height: 60px; display: flex; align-items: center; padding: 0 20px; font-weight: 700; font-size: 16px; color: #e2e8f0; }
.menu { border-right: none; background: transparent; }
:deep(.el-menu-item) { color: #cbd5e1; }
:deep(.el-menu-item.is-active) { color: #fff; background: #1e293b; }
:deep(.el-menu-item:hover) { background: #1e293b; }
.header { display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #e2e8f0; padding: 0 16px; }
.header-left { display: flex; align-items: center; gap: 8px; }
.burger { color: #334155; padding: 4px; }
.title { font-weight: 600; }
.user { display: flex; align-items: center; gap: 12px; }
.main { background: #f8fafc; padding: 16px; }
.drawer :deep(.el-drawer__body) { background: #0f172a; padding: 0; }
@media (max-width: 768px) {
  .main { padding: 10px; }
  .header { padding: 0 10px; }
  .title { font-size: 14px; }
}
</style>
