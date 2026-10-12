import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        // 后端地址可经环境变量覆盖（如本机 8000 被系统服务占用时改用 8100）
        target: `http://localhost:${process.env.BACKEND_PORT || 8000}`,
        changeOrigin: true,
      },
      '/docs': {
        target: 'http://localhost:5174',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/docs/, ''),
      },
    },
  },
})
