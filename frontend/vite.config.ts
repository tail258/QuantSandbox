import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

const apiTarget = `http://127.0.0.1:${loadEnv('development', '.', 'QUANT_').QUANT_API_PORT || '8000'}`

export default defineConfig({
  plugins: [vue()],
  server: { host: '127.0.0.1', port: 5173, strictPort: true, proxy: { '/api': apiTarget } },
  preview: { host: '127.0.0.1', port: 4173, proxy: { '/api': apiTarget } },
})
