<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ChatDotRound } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getErrorMessage } from '@/api/errors'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const loading = ref(false)
const form = reactive({ username: 'admin', password: '' })

async function submit() {
  if (!form.username.trim() || !form.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }

  loading.value = true
  try {
    await auth.login(form.username.trim(), form.password)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/dashboard'
    await router.push(redirect)
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '登录失败，请检查用户名和密码'))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="login-page">
    <section class="login-box" aria-labelledby="login-title">
      <div class="product-mark" aria-hidden="true">
        <el-icon><ChatDotRound /></el-icon>
      </div>
      <div class="product-name">抖音私信助手</div>
      <h1 id="login-title">登录</h1>
      <p class="login-description">登录后管理抖音账号和续火任务。</p>

      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="用户名">
          <el-input
            v-model="form.username"
            size="large"
            autocomplete="username"
            placeholder="请输入用户名"
          />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            size="large"
            type="password"
            show-password
            autocomplete="current-password"
            placeholder="请输入密码"
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-button
          type="primary"
          size="large"
          class="submit-button"
          :loading="loading"
          native-type="submit"
        >
          登录
        </el-button>
      </el-form>

      <p class="login-note">仅限授权管理员使用</p>
    </section>
  </main>
</template>

<style scoped>
.login-page {
  display: grid;
  min-height: 100vh;
  place-items: center;
  padding: 32px 20px;
  background: var(--color-bg);
}

.login-box {
  width: min(100%, 400px);
  padding: 42px;
  border: 1px solid var(--color-border-strong);
  border-radius: 16px;
  background: var(--color-surface);
}

.product-mark {
  display: grid;
  width: 42px;
  height: 42px;
  margin-bottom: 16px;
  place-items: center;
  border-radius: 12px;
  color: #fff;
  background: var(--color-primary);
  font-size: 22px;
}

.product-name {
  color: var(--color-text-secondary);
  font-size: 13px;
  font-weight: 600;
}

h1 {
  margin: 10px 0 0;
  color: var(--color-text);
  font-size: 30px;
  line-height: 1.3;
  letter-spacing: -0.03em;
}

.login-description {
  margin: 10px 0 32px;
  color: var(--color-text-secondary);
  font-size: 14px;
}

.login-box :deep(.el-form-item) {
  margin-bottom: 20px;
}

.login-box :deep(.el-form-item__label) {
  color: var(--color-text);
  font-size: 13px;
  font-weight: 600;
}

.submit-button {
  width: 100%;
  height: 44px;
}

.login-note {
  margin: 20px 0 0;
  color: var(--color-text-tertiary);
  font-size: 12px;
  text-align: center;
}

@media (max-width: 480px) {
  .login-page {
    align-items: start;
    padding: 56px 16px 24px;
    background: var(--color-surface);
  }

  .login-box {
    padding: 0 4px;
    border: 0;
  }
}
</style>
