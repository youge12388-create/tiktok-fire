<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

type SystemPhase = 'connecting' | 'syncing' | 'online'

const phase = ref<SystemPhase>('connecting')
const label = computed(() => {
  if (phase.value === 'connecting') return 'CONNECTING...'
  if (phase.value === 'syncing') return 'SYNCING...'
  return 'SYSTEM ONLINE'
})

const timers: number[] = []
let motionQuery: MediaQueryList | null = null

function beginSequence() {
  timers.splice(0).forEach((timer) => window.clearTimeout(timer))
  if (motionQuery?.matches) {
    phase.value = 'online'
    return
  }

  phase.value = 'connecting'
  timers.push(window.setTimeout(() => { phase.value = 'syncing' }, 760))
  timers.push(window.setTimeout(() => { phase.value = 'online' }, 1650))
}

onMounted(() => {
  motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  beginSequence()
  motionQuery.addEventListener('change', beginSequence)
})

onBeforeUnmount(() => {
  timers.forEach((timer) => window.clearTimeout(timer))
  motionQuery?.removeEventListener('change', beginSequence)
})
</script>

<template>
  <div class="system-status" :class="`is-${phase}`" aria-live="polite">
    <span class="system-status__label">
      <i></i>{{ label }}
    </span>
    <span class="system-status__meta">NODE 01 · AUTH READY</span>
    <span class="system-status__bars" aria-hidden="true"><i></i><i></i><i></i><i></i></span>
  </div>
</template>

<style scoped>
.system-status {
  display: grid;
  padding-top: 4px;
  color: #6b6f75;
  font-family: var(--login-mono);
  font-size: 8px;
  letter-spacing: 0.12em;
  grid-template-columns: 1fr auto auto;
  align-items: center;
  gap: 20px;
}

.system-status__label { display: inline-flex; align-items: center; gap: 8px; color: #a2a5a9; }
.system-status__label i { width: 6px; height: 6px; background: var(--login-yellow); }
.system-status.is-online .system-status__label { color: #d8dadc; }
.system-status.is-online .system-status__label i { background: var(--login-cyan); }

.system-status__bars { display: flex; height: 8px; align-items: flex-end; gap: 3px; }
.system-status__bars i { width: 2px; height: 3px; background: #3f444a; }
.system-status__bars i:nth-child(2) { height: 6px; }
.system-status__bars i:nth-child(3) { height: 8px; background: var(--login-brand); }
.system-status__bars i:nth-child(4) { height: 5px; }

@media (max-width: 900px) {
  .system-status__meta { display: none; }
}
</style>
