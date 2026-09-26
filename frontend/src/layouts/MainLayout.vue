<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useTheme } from '@/composables/useTheme'
import BrandFlameIcon from '@/components/BrandFlameIcon.vue'
import DigitalWave from '@/components/login/DigitalWave.vue'
import { ChatDotRound, Document, HomeFilled, Menu, Moon, Setting, Sunny, SwitchButton, Timer, User, UserFilled } from '@element-plus/icons-vue'

const route = useRoute()
const auth = useAuthStore()
const { theme, toggleTheme } = useTheme()
const isMobile = ref(false)
const drawerOpen = ref(false)

const primaryNav = [
  { path: '/dashboard', label: '总览', icon: HomeFilled },
  { path: '/accounts', label: '账号管理', icon: User, step: 1 },
  { path: '/contacts', label: '联系人', icon: ChatDotRound, step: 2 },
  { path: '/tasks', label: '任务配置', icon: Timer, step: 3 },
  { path: '/logs', label: '执行记录', icon: Document }
]
const secondaryNav = [{ path: '/settings', label: '系统信息', icon: Setting }]
const currentPage = computed(() => [...primaryNav, ...secondaryNav].find((item) => item.path === route.path))

function onResize() {
  isMobile.value = window.innerWidth < 900
  if (!isMobile.value) drawerOpen.value = false
}

onMounted(() => {
  onResize()
  window.addEventListener('resize', onResize)
})
onUnmounted(() => window.removeEventListener('resize', onResize))
</script>

<template>
  <div class="app-layout">
    <aside v-if="!isMobile" class="sidebar">
      <router-link to="/dashboard" class="brand">
        <span class="brand-icon"><el-icon><BrandFlameIcon /></el-icon></span>
        <span><strong>抖音续火花助手</strong><small>续火任务管理</small></span>
      </router-link>

      <nav class="nav" aria-label="主导航">
        <router-link v-for="item in primaryNav" :key="item.path" :to="item.path" class="nav-item" :class="{ active: route.path === item.path }">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
          <small v-if="item.step">{{ item.step }}</small>
        </router-link>
      </nav>

      <nav class="nav nav-secondary" aria-label="系统导航">
        <router-link v-for="item in secondaryNav" :key="item.path" :to="item.path" class="nav-item" :class="{ active: route.path === item.path }">
          <el-icon><component :is="item.icon" /></el-icon><span>{{ item.label }}</span>
        </router-link>
      </nav>

      <div class="sidebar-foot" aria-label="当前工作模式">
        <span class="signal-dot"></span>
        <span><strong>本地工作台</strong><small>LOCAL CONTROL</small></span>
      </div>
    </aside>

    <el-drawer v-model="drawerOpen" direction="ltr" size="260px" :with-header="false" class="mobile-drawer">
      <div class="mobile-menu">
        <div class="brand">
          <span class="brand-icon"><el-icon><BrandFlameIcon /></el-icon></span>
          <span><strong>抖音续火花助手</strong><small>续火任务管理</small></span>
        </div>
        <nav class="nav" aria-label="移动端导航">
          <router-link v-for="item in [...primaryNav, ...secondaryNav]" :key="item.path" :to="item.path" class="nav-item" :class="{ active: route.path === item.path }" @click="drawerOpen = false">
            <el-icon><component :is="item.icon" /></el-icon><span>{{ item.label }}</span><small v-if="item.step">{{ item.step }}</small>
          </router-link>
        </nav>
      </div>
    </el-drawer>

    <div class="content-area">
      <header class="topbar">
        <div class="topbar-title">
          <el-button v-if="isMobile" text aria-label="打开导航" @click="drawerOpen = true"><el-icon size="21"><Menu /></el-icon></el-button>
          <span>{{ currentPage?.label || '工作台' }}</span>
        </div>
        <div class="user-area">
          <el-tooltip :content="theme === 'dark' ? '切换为日间模式' : '切换为夜间模式'" placement="bottom">
            <el-button text class="theme-toggle" :aria-label="theme === 'dark' ? '切换为日间模式' : '切换为夜间模式'" @click="toggleTheme">
              <el-icon><Moon v-if="theme === 'dark'" /><Sunny v-else /></el-icon>
              <span class="theme-label">{{ theme === 'dark' ? '夜间' : '日间' }}</span>
            </el-button>
          </el-tooltip>
          <span class="user-icon"><el-icon><UserFilled /></el-icon></span>
          <span class="user-name">{{ auth.username || '管理员' }}</span>
          <el-button text class="logout" @click="auth.logout()"><el-icon><SwitchButton /></el-icon><span>退出</span></el-button>
        </div>
      </header>
      <main class="main-content">
        <DigitalWave class="workbench-wave" />
        <div class="main-content__view"><router-view /></div>
      </main>
    </div>
  </div>
</template>

<style scoped>
.app-layout { position: relative; display: flex; min-height: 100vh; background: var(--color-bg); }
.sidebar { position: sticky; z-index: 2; top: 0; display: flex; width: 240px; height: 100vh; flex: 0 0 240px; flex-direction: column; padding: 24px 16px; border-right: 1px solid var(--color-border); background: var(--color-sidebar); }
.brand { display: flex; align-items: center; gap: 11px; padding: 2px 9px 28px; }
.brand-icon { display: grid; width: 36px; height: 36px; place-items: center; border-radius: 11px; color: var(--color-on-primary); background: var(--color-primary); }
.brand-icon .el-icon { font-size: 19px; }
.brand strong, .brand small { display: block; color: var(--color-sidebar-text); }
.brand strong { font-size: 14px; font-weight: 700; }
.brand small { margin-top: 4px; color: var(--color-sidebar-muted); font-size: 10px; }
.nav { display: grid; gap: 4px; }
.nav-item { position: relative; display: flex; align-items: center; gap: 11px; min-height: 44px; padding: 0 12px; border-radius: 10px; color: var(--color-sidebar-muted); font-size: 13px; transition: color 160ms ease, background 160ms ease; }
.nav-item:hover { color: var(--color-sidebar-text); background: var(--color-nav-hover); }
.nav-item.active { color: var(--color-sidebar-text); background: var(--color-sidebar-surface); font-weight: 700; }
.nav-item.active .el-icon { color: var(--color-primary); }
.nav-item .el-icon { font-size: 17px; }
.nav-item span { flex: 1; }
.nav-item small { display: grid; width: 20px; height: 20px; place-items: center; border: 1px solid currentColor; border-radius: 50%; font-size: 10px; font-weight: 700; opacity: 0.7; }
.nav-secondary { margin-top: auto; padding-top: 16px; border-top: 1px solid var(--color-sidebar-divider); }
.sidebar-foot { display: flex; align-items: center; gap: 9px; padding: 22px 12px 0; color: var(--color-sidebar-text); }
.signal-dot { width: 7px; height: 7px; flex: 0 0 7px; border-radius: 50%; background: var(--color-success); box-shadow: 0 0 0 4px rgba(93, 184, 151, 0.12); }
.sidebar-foot strong, .sidebar-foot small { display: block; }
.sidebar-foot strong { font-size: 11px; font-weight: 650; }
.sidebar-foot small { margin-top: 3px; color: var(--color-sidebar-muted); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 9px; letter-spacing: 0.08em; }
.content-area { min-width: 0; flex: 1; }
.workbench-wave { z-index: -1; --digital-wave-background: transparent; opacity: 0.28; }
.topbar { position: sticky; z-index: 10; top: 0; display: flex; height: 72px; align-items: center; justify-content: space-between; padding: 0 36px; border-bottom: 1px solid var(--color-glass-border); background: var(--color-topbar); background-image: var(--color-glass-sheen); box-shadow: inset 0 1px 0 var(--color-glass-highlight), 0 10px 30px rgba(0, 0, 0, 0.08); }
.topbar-title { display: flex; align-items: center; gap: 6px; font-size: 14px; font-weight: 700; }
.user-area { display: flex; align-items: center; gap: 8px; }
.theme-toggle { min-width: 68px; color: var(--color-text-secondary); }
.theme-toggle:hover { color: var(--color-primary); }
.theme-toggle .el-icon { font-size: 16px; }
.theme-label { margin-left: 4px; font-size: 12px; }
.user-icon { display: grid; width: 30px; height: 30px; place-items: center; border-radius: 50%; color: var(--color-text-secondary); background: var(--color-surface-muted); }
.user-name { font-size: 12px; }
.logout { margin-left: 4px; color: var(--color-text-secondary); }
.logout:hover { color: var(--color-primary); }
.main-content { position: relative; z-index: 1; isolation: isolate; min-height: calc(100vh - 72px); padding: 34px 36px 60px; }
.main-content__view { position: relative; }
.mobile-drawer :deep(.el-drawer__body) { padding: 0; }
.mobile-menu { min-height: 100%; padding: 24px 16px; background: var(--color-sidebar); }
.mobile-menu .brand { padding-bottom: 28px; }

@media (max-width: 899px) {
  .topbar { padding: 0 20px; }
  .main-content { padding: 26px 20px 48px; }
}

@media (max-width: 520px) {
  .user-name, .logout span, .theme-label { display: none; }
  .theme-toggle { min-width: 32px; padding: 8px; }
  .topbar { height: 60px; }
  .main-content { min-height: calc(100vh - 60px); padding: 22px 14px 42px; }
}
</style>
