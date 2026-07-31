import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import VueECharts from 'vue-echarts'
import * as echarts from 'echarts'
import App from './App.vue'
import router from './router'
// 引入 Element Plus 深色主题适配样式
import '@/styles/element-dark-theme.css'

const app = createApp(App)

// 为 vue-echarts 提供 echarts 实例
app.provide('ec', echarts)

// 安装路由
app.use(router)

// 安装状态管理
const pinia = createPinia()
app.use(pinia)

// 安装 Element Plus UI 组件库
app.use(ElementPlus)

// 注册 ECharts 组件（全局可按需引入，此处直接注册）
app.component('VChart', VueECharts)

// 应用启动后初始化认证状态
router.isReady().then(async () => {
  const token = localStorage.getItem('token')
  if (token) {
    const { useAuthStore } = await import('@/stores/auth')
    const auth = useAuthStore()
    await auth.fetchUser()
  }
  app.mount('#app')
})

