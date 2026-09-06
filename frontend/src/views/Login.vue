<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import BrandHeader from '@/components/login/BrandHeader.vue'
import DigitalWave from '@/components/login/DigitalWave.vue'
import HeroSection from '@/components/login/HeroSection.vue'
import LoginForm from '@/components/login/LoginForm.vue'
import SystemStatus from '@/components/login/SystemStatus.vue'
import { getErrorMessage } from '@/api/errors'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const loading = ref(false)
const formError = ref('')
const form = reactive({ username: 'admin', password: '' })

function clearError() {
  formError.value = ''
}

async function submit() {
  if (!form.username.trim() || !form.password) {
    formError.value = '请输入管理员用户名和密码后再继续。'
    ElMessage.warning('请输入用户名和密码')
    return
  }

  formError.value = ''
  loading.value = true
  try {
    await auth.login(form.username.trim(), form.password)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/dashboard'
    await router.push(redirect)
  } catch (error: unknown) {
    const message = getErrorMessage(error, '登录失败，请检查用户名和密码')
    formError.value = `${message}。请核对后重试。`
    ElMessage.error(message)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="login-page">
    <DigitalWave class="login-page__wave" />
    <BrandHeader />

    <div class="login-page__main">
      <HeroSection />

      <section class="login-page__auth" aria-label="管理员登录">
        <div class="login-page__registration" aria-hidden="true">
          <i></i><i></i><i></i>
        </div>

        <div class="login-page__auth-inner">
          <LoginForm
            v-model:username="form.username"
            v-model:password="form.password"
            :loading="loading"
            :error="formError"
            @change="clearError"
            @submit="submit"
          />
        </div>

        <SystemStatus class="login-page__status" />
      </section>
    </div>
  </main>
</template>

<style scoped>
.login-page {
  position: relative;
  isolation: isolate;
  --login-dark: #090b0d;
  --login-light: #f2efe7;
  --login-text-dark: #111111;
  --login-text-light: #f4f4f4;
  --login-muted: #8a8d91;
  --login-brand: #f43f5e;
  --login-cyan: #15c7e8;
  --login-yellow: #f5c842;
  --login-mono: "Cascadia Mono", "SFMono-Regular", Consolas, monospace;
  --login-ease: cubic-bezier(0.22, 1, 0.36, 1);
  min-width: 320px;
  min-height: 100vh;
  min-height: 100dvh;
  overflow-x: clip;
  color: var(--login-text-light);
  background: var(--login-dark);
}

.login-page__main {
  position: relative;
  display: grid;
  height: calc(100vh - 64px);
  height: calc(100dvh - 64px);
  min-height: 650px;
  overflow: hidden;
  background: transparent;
  grid-template-columns: minmax(0, 56fr) minmax(0, 44fr);
  isolation: isolate;
}

.login-page__wave {
  z-index: 0;
}

.login-page__auth {
  position: relative;
  z-index: 2;
  display: grid;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  background: transparent;
  place-items: center;
}

.login-page__auth::before {
  position: absolute;
  inset: 12% 8%;
  background: radial-gradient(ellipse at center, rgba(9, 11, 13, 0.38), rgba(9, 11, 13, 0.12) 60%, transparent 78%);
  content: "";
  pointer-events: none;
}

.login-page__auth-inner {
  position: relative;
  z-index: 2;
  width: min(420px, calc(100% - 64px));
  margin-top: -28px;
}

.login-page__registration {
  position: absolute;
  top: 31px;
  right: clamp(28px, 4vw, 62px);
  display: flex;
  gap: 7px;
  pointer-events: none;
}

.login-page__registration i { width: 5px; height: 5px; background: #34383d; }
.login-page__registration i:nth-child(1) { background: var(--login-cyan); }
.login-page__registration i:nth-child(3) { background: var(--login-yellow); }

.login-page__status {
  position: absolute;
  z-index: 2;
  right: clamp(28px, 4vw, 62px);
  bottom: 24px;
  left: clamp(28px, 4vw, 62px);
}

@media (max-width: 1200px) and (min-width: 768px) {
  .login-page__main { grid-template-columns: minmax(0, 51fr) minmax(0, 49fr); }
  .login-page__auth-inner { width: min(420px, calc(100% - 64px)); }
}

@media (max-width: 767px) {
  .login-page__main {
    display: flex;
    height: auto;
    min-height: 0;
    flex-direction: column;
  }

  .login-page__wave { position: absolute; inset: 0; }

  .login-page__auth {
    order: 2;
    display: block;
    min-height: 540px;
    padding: 36px 22px 82px;
  }

  .login-page__auth::before {
    inset: 0;
    background: radial-gradient(ellipse at center, rgba(9, 11, 13, 0.36), transparent 78%);
  }

  .login-page__auth-inner {
    width: 100%;
    margin: 0 auto;
  }

  .login-page__registration { top: 22px; right: 22px; }
  .login-page__status { right: 22px; bottom: 28px; left: 22px; }
}

@media (max-width: 390px) {
  .login-page__auth { padding-right: 20px; padding-left: 20px; }
  .login-page__status { right: 20px; left: 20px; }
}

</style>
