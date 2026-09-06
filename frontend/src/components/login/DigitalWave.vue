<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

interface FlowCell {
  detailA: number
  detailB: number
  gate: number
  phase: number
  shade: number
  spark: number
  shapeA: number
  shapeB: number
  x: number
  y: number
}


const canvas = ref<HTMLCanvasElement | null>(null)
const neutralPalette = ['#2c2c2c', '#353535', '#505050', '#6d6d6d']
const blushPalette = ['#63414a', '#8b5a67', '#bd7887', '#efaaba']

let context: CanvasRenderingContext2D | null = null
let animationFrame = 0
let animationTime = 0
let previousTime = 0
let frameElapsed = 0
let canvasWidth = 0
let canvasHeight = 0
let pixelRatio = 1
let pixelSize = 5
let cells: FlowCell[] = []
const noiseSize = 32
const noiseValues = Float32Array.from({ length: noiseSize ** 3 }, (_, index) => pseudoRandom(index + 41))
let resizeObserver: ResizeObserver | null = null
let motionQuery: MediaQueryList | null = null

function pseudoRandom(seed: number) {
  const value = Math.sin(seed * 12.9898 + 78.233) * 43758.5453
  return value - Math.floor(value)
}

function createCells(step: number) {
  const output: FlowCell[] = []
  const columns = Math.ceil(canvasWidth / step)
  const rows = Math.ceil(canvasHeight / step)

  for (let row = 0; row <= rows; row += 1) {
    for (let column = 0; column <= columns; column += 1) {
      const x = column * step
      const y = row * step
      const seed = row * (columns + 1) + column + 1
      output.push({
        detailA: noise(x / 58 + 3, y / 58 + 11, 17),
        detailB: noise(x / 54 + 19, y / 54 + 5, 23),
        gate: pseudoRandom(seed * 5.9),
        phase: noise(x / 220 + 7, y / 220 + 13, 9),
        shade: pseudoRandom(seed * 7.3),
        spark: pseudoRandom(seed * 11.9 + 101),
        shapeA: noise(x / 145 + 2, y / 145 + 5, 3),
        shapeB: noise(x / 155 + 17, y / 155 + 2, 13),
        x,
        y
      })
    }
  }

  return output
}

function smooth(value: number) {
  return value * value * (3 - 2 * value)
}

function mix(a: number, b: number, weight: number) {
  return a + (b - a) * weight
}

function clamp(value: number) {
  return Math.max(0, Math.min(1, value))
}

// A small seeded 3D lattice evolves continuously: regions appear and dissolve
// locally, without predefined ribbons or independent random pixel flashing.
function noise(x: number, y: number, z: number) {
  const ix = Math.floor(x)
  const iy = Math.floor(y)
  const iz = Math.floor(z)
  const u = smooth(x - ix)
  const v = smooth(y - iy)
  const w = smooth(z - iz)
  const x0 = ix & 31
  const x1 = (ix + 1) & 31
  const y0 = (iy & 31) * 32
  const y1 = ((iy + 1) & 31) * 32
  const z0 = (iz & 31) * 1024
  const z1 = ((iz + 1) & 31) * 1024
  return mix(
    mix(mix(noiseValues[x0 + y0 + z0], noiseValues[x1 + y0 + z0], u),
      mix(noiseValues[x0 + y1 + z0], noiseValues[x1 + y1 + z0], u), v),
    mix(mix(noiseValues[x0 + y0 + z1], noiseValues[x1 + y0 + z1], u),
      mix(noiseValues[x0 + y1 + z1], noiseValues[x1 + y1 + z1], u), v), w)
}

function flowIntensity(cell: FlowCell, seconds: number) {
  const time = seconds * 0.78 + cell.phase * 0.85
  const driftX = Math.sin(cell.y / 138 + time * 1.4) * 22
    + (noise(cell.x / 310 + 3, cell.y / 280 + 7, time * 0.7 + 11) - 0.5) * 34
  const driftY = Math.cos(cell.x / 176 - time * 1.1) * 18
    + (noise(cell.x / 270 + 19, cell.y / 250 + 5, time * 0.74 + 23) - 0.5) * 30
  const x = cell.x + driftX
  const y = cell.y + driftY
  const broad = noise(x / 205 + 2, y / 178 + 5, time * 0.42 + 3)
  const detail = noise(x / 76 + 13, y / 72 + 17, time * 0.9 + cell.shapeA * 2)
  const grain = noise(x / 31 + 29, y / 34 + 7, time * 1.85 + cell.shapeB * 3)

  return broad * 0.42 + detail * 0.48 + grain * 0.1
}

function draw(time: number) {
  if (!context || !canvasWidth || !canvasHeight) return

  context.clearRect(0, 0, canvasWidth, canvasHeight)
  context.imageSmoothingEnabled = false
  const seconds = time * 0.001

  for (let cellIndex = 0; cellIndex < cells.length; cellIndex += 1) {
    const cell = cells[cellIndex]
    const intensity = flowIntensity(cell, seconds)
    const gate = 0.47 + cell.gate * 0.18
    const reveal = smooth(clamp((intensity - gate) * 8.5))
    if (reveal < 0.14) continue

    let level = intensity > 0.72 ? 3 : intensity > 0.66 ? 2 : intensity > 0.6 ? 1 : 0
    if (cell.shade < 0.12) level = Math.max(0, level - 1)
    if (cell.shade > 0.92) level = Math.min(3, level + 1)

    const blush = cell.spark > 0.9 && reveal > 0.34

    context.globalAlpha = reveal
    context.fillStyle = (blush ? blushPalette : neutralPalette)[level]
    context.fillRect(Math.round(cell.x), Math.round(cell.y), pixelSize, pixelSize)
  }

  context.globalAlpha = 1
}

function animate(time: number) {
  const delta = time - previousTime
  previousTime = time
  animationTime += delta
  frameElapsed += delta
  const interval = 1000 / (canvasWidth < 768 ? 30 : 60)

  if (frameElapsed >= interval) {
    draw(animationTime)
    frameElapsed %= interval
  }
  animationFrame = window.requestAnimationFrame(animate)
}

function updateMotion() {
  window.cancelAnimationFrame(animationFrame)
  if (!context || document.hidden) return

  previousTime = performance.now()
  frameElapsed = 0
  draw(motionQuery?.matches ? 0 : animationTime)
  if (!motionQuery?.matches) animationFrame = window.requestAnimationFrame(animate)
}

function resizeCanvas() {
  if (!canvas.value) return

  const rect = canvas.value.getBoundingClientRect()
  canvasWidth = Math.max(1, Math.round(rect.width))
  canvasHeight = Math.max(1, Math.round(rect.height))
  pixelRatio = Math.min(window.devicePixelRatio || 1, 1.5)

  canvas.value.width = Math.round(canvasWidth * pixelRatio)
  canvas.value.height = Math.round(canvasHeight * pixelRatio)
  context = canvas.value.getContext('2d', { alpha: true })
  context?.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0)

  const gridStep = Math.max(7, Math.sqrt(canvasWidth * canvasHeight / 48000))
  pixelSize = Math.max(5, Math.round(gridStep * 5 / 7))
  cells = createCells(gridStep)
  draw(motionQuery?.matches ? 0 : animationTime)
}

onMounted(() => {
  motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  resizeCanvas()
  resizeObserver = new ResizeObserver(resizeCanvas)
  if (canvas.value) resizeObserver.observe(canvas.value)
  motionQuery.addEventListener('change', updateMotion)
  document.addEventListener('visibilitychange', updateMotion)
  updateMotion()
})

onBeforeUnmount(() => {
  window.cancelAnimationFrame(animationFrame)
  resizeObserver?.disconnect()
  motionQuery?.removeEventListener('change', updateMotion)
  document.removeEventListener('visibilitychange', updateMotion)
})
</script>

<template>
  <div class="digital-wave" aria-hidden="true">
    <canvas ref="canvas"></canvas>
    <div class="digital-wave__veil"></div>
  </div>
</template>

<style scoped>
.digital-wave {
  position: absolute;
  inset: 0;
  overflow: hidden;
  background: #090b0d;
  pointer-events: none;
}

.digital-wave canvas {
  display: block;
  width: 100%;
  height: 100%;
  image-rendering: pixelated;
}

.digital-wave__veil {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(180deg, rgba(9, 11, 13, 0.1), transparent 18%, transparent 86%, rgba(9, 11, 13, 0.08));
}
</style>
