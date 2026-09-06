<script setup lang="ts">
const features = [
  '定时续火花',
  '多账号管理',
  '登录状态同步',
  '异常目标监控'
]
</script>

<template>
  <ul class="feature-list" aria-label="主要能力">
    <li v-for="feature in features" :key="feature">
      <span aria-hidden="true"></span>
      <strong>{{ feature }}</strong>
    </li>
  </ul>
</template>

<style scoped>
.feature-list {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 24px;
  margin: 30px 0 0;
  padding: 0;
  list-style: none;
}

.feature-list li {
  display: inline-flex;
  color: #aeb2b7;
  align-items: center;
  gap: 9px;
}

.feature-list span {
  width: 5px;
  height: 5px;
  background: var(--login-brand);
  opacity: 0.86;
}

.feature-list li:nth-child(2) span { background: var(--login-cyan); opacity: 0.72; }
.feature-list li:nth-child(3) span { background: #7f848a; }
.feature-list li:nth-child(4) span { background: var(--login-yellow); opacity: 0.7; }

.feature-list strong {
  font-size: 11px;
  font-weight: 580;
  letter-spacing: 0.03em;
  white-space: nowrap;
}

@media (max-width: 980px) and (min-width: 768px) {
  .feature-list { max-width: 300px; }
}

@media (max-width: 767px) {
  .feature-list { gap: 9px 18px; margin-top: 20px; }
  .feature-list strong { font-size: 10px; }
}
</style>
