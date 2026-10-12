import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    host: '0.0.0.0',
    allowedHosts: true,
    port: 5173,
    proxy: {
      '/api': {
        // 后端地址可经环境变量覆盖(公司电脑 8000 被系统占用时改用 8100/8001)
        target: `http://localhost:${process.env.BACKEND_PORT || 8000}`,
        changeOrigin: true,
      },
    },
  },
})
