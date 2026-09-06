<script setup lang="ts">
const props = defineProps<{
  username: string
  password: string
  loading: boolean
  error: string
}>()

const emit = defineEmits<{
  'update:username': [value: string]
  'update:password': [value: string]
  submit: []
  change: []
}>()

function updateUsername(value: string) {
  emit('update:username', value)
  emit('change')
}

function updatePassword(value: string) {
  emit('update:password', value)
  emit('change')
}
</script>

<template>
  <section class="login-form" aria-labelledby="login-title">
    <div class="login-form__heading">
      <p><i></i> CONTROL PANEL</p>
      <h2 id="login-title">控制台登录</h2>
      <span>登录后可管理账号、目标好友、发送任务与运维配置。</span>
    </div>

    <el-form label-position="top" @submit.prevent="emit('submit')">
      <el-form-item label="管理员用户名">
        <el-input
          :model-value="props.username"
          autocomplete="username"
          placeholder="请输入管理员用户名"
          @update:model-value="updateUsername"
        />
      </el-form-item>

      <el-form-item label="管理员密码">
        <el-input
          :model-value="props.password"
          type="password"
          show-password
          autocomplete="current-password"
          placeholder="请输入管理员密码"
          @update:model-value="updatePassword"
          @keyup.enter="emit('submit')"
        />
      </el-form-item>

      <p class="login-form__feedback" :class="{ 'is-error': props.error }" aria-live="polite">
        {{ props.error || '请输入管理员凭证以继续。' }}
      </p>

      <el-button
        class="login-form__submit"
        type="primary"
        native-type="submit"
        :loading="props.loading"
      >
        <span>{{ props.loading ? '正在验证身份' : '登录控制台' }}</span>
        <svg v-if="!props.loading" viewBox="0 0 16 16" aria-hidden="true">
          <path d="M3 8h9M8.5 4.5 12 8l-3.5 3.5" fill="none" stroke="currentColor" stroke-linecap="square" stroke-width="1.5" />
        </svg>
      </el-button>
    </el-form>

    <p class="login-form__security">
      <svg viewBox="0 0 18 18" aria-hidden="true">
        <path d="M9 2.25 15 4.7v4.05c0 3.34-2.26 5.8-6 7-3.74-1.2-6-3.66-6-7V4.7L9 2.25Z" fill="none" stroke="currentColor" stroke-width="1.2" />
        <path d="m6.7 8.9 1.45 1.45 3.15-3.2" fill="none" stroke="currentColor" stroke-width="1.2" />
      </svg>
      认证页面不会展示服务器敏感登录态数据。
    </p>
  </section>
</template>

<style scoped>
.login-form {
  width: min(420px, 100%);
  text-shadow: 0 1px 3px #090b0d;
  animation: login-enter 560ms 90ms var(--login-ease) both;
}

.login-form__heading > p {
  display: flex;
  margin: 0 0 14px;
  color: #a7a9ad;
  font-family: var(--login-mono);
  font-size: 10px;
  letter-spacing: 0.17em;
  align-items: center;
  gap: 9px;
}

.login-form__heading > p i {
  width: 8px;
  height: 8px;
  background: var(--login-brand);
}

.login-form h2 {
  margin: 0;
  color: var(--login-text-light);
  font-size: clamp(30px, 2.25vw, 37px);
  font-weight: 780;
  line-height: 1.16;
  letter-spacing: -0.045em;
}

.login-form__heading > span {
  display: block;
  margin-top: 11px;
  color: var(--login-muted);
  font-size: 13px;
  line-height: 1.7;
}

.login-form :deep(.el-form) { margin-top: 34px; }
.login-form :deep(.el-form-item) { margin-bottom: 19px; }

.login-form :deep(.el-form-item__label) {
  height: auto;
  margin-bottom: 8px;
  padding: 0;
  color: #d4d5d6;
  font-size: 11px;
  font-weight: 650;
  line-height: 1.4;
}

.login-form :deep(.el-input__wrapper) {
  min-height: 52px;
  padding: 0 15px;
  border-radius: 8px;
  color: var(--login-text-light);
  background: #11151a;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.12) inset;
  transition: background-color 180ms ease, box-shadow 180ms ease;
}

.login-form :deep(.el-input__wrapper:hover) {
  background: #14191f;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.22) inset;
}

.login-form :deep(.el-input__wrapper.is-focus) {
  background: #14191f;
  box-shadow: 0 0 0 1px rgba(244, 63, 94, 0.7) inset;
}

.login-form :deep(.el-input__inner) {
  color: var(--login-text-light);
  font-size: 14px;
}

.login-form :deep(.el-input__inner::placeholder) { color: #5f646b; }
.login-form :deep(.el-input__password) { color: #8d9298; }

.login-form__feedback {
  min-height: 18px;
  margin: -5px 0 13px;
  color: #92979f;
  font-size: 10px;
  line-height: 1.7;
}

.login-form__feedback.is-error { color: #ff8298; }

.login-form__submit {
  position: relative;
  width: 100%;
  height: 52px;
  overflow: visible;
  border: 0;
  border-radius: 8px;
  color: #fff;
  background: var(--login-brand);
  font-size: 14px;
  font-weight: 700;
  box-shadow: none;
  transition: filter 160ms ease, transform 120ms steps(2, end);
}

.login-form__submit::after {
  position: absolute;
  right: -2px;
  bottom: -2px;
  width: 8px;
  height: 8px;
  background: #8f1f37;
  content: "";
  pointer-events: none;
  clip-path: polygon(50% 0, 100% 0, 100% 100%, 0 100%, 0 50%);
}

.login-form__submit:hover,
.login-form__submit:focus-visible { color: #fff; background: var(--login-brand); filter: brightness(1.08); }
.login-form__submit:active { transform: translate(1px, 1px); }

.login-form__submit span { display: inline-flex; align-items: center; }
.login-form__submit svg { width: 16px; height: 16px; margin-left: 10px; }

.login-form__security {
  display: flex;
  margin: 25px 0 0;
  padding-top: 4px;
  color: #92979f;
  font-size: 10px;
  line-height: 1.6;
  align-items: center;
  gap: 9px;
}

.login-form__security svg { flex: 0 0 auto; width: 17px; height: 17px; }

@keyframes login-enter {
  from { opacity: 0; transform: translateX(10px); }
  to { opacity: 1; transform: translateX(0); }
}

@media (max-width: 767px) {
  .login-form h2 { font-size: 32px; }
  .login-form :deep(.el-form) { margin-top: 26px; }
}

@media (prefers-reduced-motion: reduce) {
  .login-form { animation: none; }
  .login-form__submit { transition: none; }
  .login-form__submit:active { transform: none; }
}
</style>
