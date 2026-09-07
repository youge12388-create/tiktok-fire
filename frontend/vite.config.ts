import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const configuredBase = process.env.VITE_BASE_PATH?.trim() || '/'
const baseSegments = configuredBase.replace(/^\/+|\/+$/g, '')
const base = baseSegments ? `/${baseSegments}/` : '/'

export default defineConfig({
  base,
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src')
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: false
      }
    }
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks: {
          'framework': ['vue', 'vue-router', 'pinia', 'axios']
        }
      }
    }
  }
})
