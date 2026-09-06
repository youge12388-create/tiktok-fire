<script setup lang="ts">
import BrandFlameIcon from '@/components/BrandFlameIcon.vue'
</script>

<template>
  <header class="brand-header">
    <div class="brand-header__identity" aria-label="抖音续火花助手 DouYin Spark Flow">
      <span class="brand-header__mark"><BrandFlameIcon /></span>
      <span class="brand-header__name">
        <strong>抖音续火花助手</strong>
        <small>DOUYIN SPARK FLOW</small>
      </span>
    </div>

    <div class="brand-header__descriptor" aria-hidden="true">
      <span class="brand-header__swatches">
        <i class="is-red"></i><i class="is-cyan"></i><i class="is-yellow"></i>
      </span>
      <span>// KEEP EVERY SPARK ALIVE</span>
    </div>

    <div class="brand-header__edition" aria-hidden="true">
      <span>ADMIN / PRIVATE</span>
      <i></i>
    </div>
  </header>
</template>

<style scoped>
.brand-header {
  position: relative;
  z-index: 20;
  display: grid;
  height: 64px;
  padding: 0 clamp(24px, 3vw, 48px);
  color: var(--login-text-light);
  background: rgba(8, 10, 12, 0.42);
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: clamp(28px, 4vw, 64px);
  animation: brand-enter 450ms var(--login-ease) both;
}

.brand-header::after {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.09) 16%, rgba(255, 255, 255, 0.09) 84%, transparent);
  content: "";
  pointer-events: none;
}

.brand-header__identity,
.brand-header__descriptor,
.brand-header__edition,
.brand-header__swatches {
  display: flex;
  align-items: center;
}

.brand-header__identity { gap: 11px; }

.brand-header__mark {
  display: grid;
  width: 32px;
  height: 32px;
  color: #fff;
  background: var(--login-brand);
  place-items: center;
  clip-path: polygon(0 0, calc(100% - 5px) 0, 100% 5px, 100% 100%, 5px 100%, 0 calc(100% - 5px));
}

.brand-header__mark :deep(svg) { width: 18px; height: 18px; }

.brand-header__name strong,
.brand-header__name small { display: block; white-space: nowrap; }

.brand-header__name strong {
  font-size: 13px;
  font-weight: 750;
  letter-spacing: -0.01em;
}

.brand-header__name small,
.brand-header__descriptor,
.brand-header__edition {
  font-family: var(--login-mono);
  letter-spacing: 0.14em;
}

.brand-header__name small {
  margin-top: 2px;
  color: #73777d;
  font-size: 7px;
}

.brand-header__descriptor {
  min-width: 0;
  gap: 22px;
  color: #989ca1;
  font-size: 9px;
}

.brand-header__swatches { gap: 6px; }
.brand-header__swatches i { width: 8px; height: 8px; }
.brand-header__swatches .is-red { background: var(--login-brand); }
.brand-header__swatches .is-cyan { background: var(--login-cyan); }
.brand-header__swatches .is-yellow { background: var(--login-yellow); }

.brand-header__edition {
  gap: 11px;
  color: #7d8187;
  font-size: 8px;
}

.brand-header__edition i {
  width: 6px;
  height: 6px;
  background: var(--login-brand);
}

@keyframes brand-enter {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}

@media (max-width: 767px) {
  .brand-header {
    height: 58px;
    padding: 0 18px;
    grid-template-columns: 1fr auto;
  }

  .brand-header__descriptor { display: none; }
  .brand-header__edition span { display: none; }
}

@media (prefers-reduced-motion: reduce) {
  .brand-header { animation: none; }
}
</style>
