<script setup lang="ts">
import FeatureList from './FeatureList.vue'
</script>

<template>
  <section class="hero-section" aria-labelledby="hero-title">
    <div class="hero-section__copy">
      <h1 id="hero-title">
        <span>火花因人而亮，</span>
        <span class="hero-section__accent">不因打卡而生。</span>
      </h1>
      <p class="hero-section__statement">别让死板的形式，框住本该自由的友谊。</p>
      <FeatureList />
    </div>

    <div class="hero-section__signal" aria-hidden="true">
      <span></span><span></span><span></span>
    </div>
  </section>
</template>

<style scoped>
.hero-section {
  position: relative;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  color: var(--login-text-light);
  background: transparent;
  isolation: isolate;
}

.hero-section__copy {
  position: relative;
  text-shadow: 0 1px 3px #090b0d;
  z-index: 3;
  display: flex;
  height: 100%;
  padding: clamp(52px, 7vh, 78px) clamp(38px, 5vw, 88px);
  justify-content: center;
  flex-direction: column;
  animation: hero-enter 560ms 55ms var(--login-ease) both;
}

h1 {
  margin: 0;
  max-width: 820px;
  font-size: clamp(52px, 4.55vw, 82px);
  font-weight: 860;
  line-height: 1.04;
  letter-spacing: -0.045em;
  text-wrap: balance;
}

h1 span { display: block; }

.hero-section__accent {
  margin-top: 8px;
  color: var(--login-brand);
}

.hero-section__statement {
  max-width: 620px;
  margin: 28px 0 0;
  color: #c4c7cb;
  font-size: clamp(16px, 1.25vw, 20px);
  font-weight: 430;
  line-height: 1.7;
  letter-spacing: -0.01em;
}

.hero-section__signal {
  position: absolute;
  z-index: 4;
  bottom: 26px;
  left: clamp(38px, 5vw, 88px);
  display: flex;
  gap: 8px;
  pointer-events: none;
}

.hero-section__signal span { width: 6px; height: 6px; background: #363a40; }
.hero-section__signal span:first-child { background: var(--login-brand); }
.hero-section__signal span:nth-child(2) { background: var(--login-cyan); opacity: 0.72; }
.hero-section__signal span:last-child { background: var(--login-yellow); opacity: 0.68; }

@keyframes hero-enter {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

@media (max-width: 1200px) and (min-width: 768px) {
  .hero-section__copy { padding-right: 28px; padding-left: 40px; }
  h1 { font-size: clamp(44px, 4.8vw, 60px); }
}

@media (max-height: 790px) and (min-width: 768px) {
  h1 { font-size: clamp(44px, 4vw, 64px); }
  .hero-section__statement { margin-top: 22px; }
}

@media (max-width: 767px) {
  .hero-section {
    position: relative;
    z-index: 1;
    order: 1;
    min-height: 286px;
  }

  .hero-section__copy {
    padding: 34px 22px 28px;
    background: transparent;
  }

  h1 { font-size: clamp(40px, 11.5vw, 52px); line-height: 1.06; }
  .hero-section__statement { margin-top: 18px; font-size: 14px; line-height: 1.65; }
  .hero-section__signal { display: none; }
}

@media (prefers-reduced-motion: reduce) {
  .hero-section__copy { animation: none; }
}
</style>
