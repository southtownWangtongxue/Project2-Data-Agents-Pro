<script setup lang="ts">
/**
 * 登录页面
 * 深色主题 + 渐变卡片 + 企业级登录表单
 */
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

const formRef = ref()
const form = reactive({
  userName: '',
  password: '',
})
const loading = ref(false)
const errorMsg = ref('')

/* 表单校验规则 */
const rules = {
  userName: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
  ],
}

/* 登录 */
async function handleLogin() {
  if (!formRef.value) return

  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  errorMsg.value = ''

  try {
    await auth.login(form.userName, form.password)
    router.replace('/chat')
  } catch (err: any) {
    const detail = err?.response?.data?.detail || err?.message || '登录失败'
    errorMsg.value = typeof detail === 'string' ? detail : '用户名或密码错误'
  } finally {
    loading.value = false
  }
}

/* Enter 键登录 */
function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter') handleLogin()
}
</script>

<template>
  <div class="login-page">
    <!-- 装饰背景 -->
    <div class="login-bg">
      <div class="bg-blob bg-blob-1" />
      <div class="bg-blob bg-blob-2" />
    </div>

    <!-- 登录卡片 -->
    <div class="login-card">
      <div class="login-header">
        <div class="login-logo">
          <svg width="40" height="40" viewBox="0 0 28 28" fill="none">
            <rect width="28" height="28" rx="6" fill="url(#loginGradient)" />
            <path d="M8 10h12M8 14h8M8 18h10" stroke="white" stroke-width="2" stroke-linecap="round" />
            <defs>
              <linearGradient id="loginGradient" x1="0" y1="0" x2="28" y2="28">
                <stop stop-color="#6366f1" />
                <stop offset="1" stop-color="#818cf8" />
              </linearGradient>
            </defs>
          </svg>
        </div>
        <h1 class="login-title">DataAgent Pro</h1>
        <p class="login-subtitle">智能业务数据分析助手</p>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        class="login-form"
        @keydown="handleKeydown"
      >
        <!-- 错误提示 -->
        <transition name="fade">
          <div v-if="errorMsg" class="login-error">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span>{{ errorMsg }}</span>
          </div>
        </transition>

        <el-form-item prop="userName">
          <el-input
            v-model="form.userName"
            placeholder="用户名"
            size="large"
            :prefix-icon="UserIcon"
            class="dark-input"
          />
        </el-form-item>

        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码"
            size="large"
            show-password
            :prefix-icon="LockIcon"
            class="dark-input"
          />
        </el-form-item>

        <el-button
          type="primary"
          size="large"
          class="login-btn"
          :loading="loading"
          @click="handleLogin"
        >
          {{ loading ? '登录中...' : '登 录' }}
        </el-button>
      </el-form>

      <p class="login-hint">
        请使用您的系统账号登录
      </p>
    </div>
  </div>
</template>

<script lang="ts">
import { h, defineComponent } from 'vue'

/* 输入框图标 */
const UserIcon = defineComponent({
  render() {
    return h('svg', {
      width: '18', height: '18', viewBox: '0 0 24 24',
      fill: 'none', stroke: 'currentColor', 'stroke-width': '1.5',
    }, [
      h('path', { d: 'M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2' }),
      h('circle', { cx: '12', cy: '7', r: '4' }),
    ])
  },
})

const LockIcon = defineComponent({
  render() {
    return h('svg', {
      width: '18', height: '18', viewBox: '0 0 24 24',
      fill: 'none', stroke: 'currentColor', 'stroke-width': '1.5',
    }, [
      h('rect', { x: '3', y: '11', width: '18', height: '11', rx: '2', ry: '2' }),
      h('path', { d: 'M7 11V7a5 5 0 0 1 10 0v4' }),
    ])
  },
})
</script>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  position: relative;
  overflow: hidden;
}

/* === 装饰背景 === */
.login-bg {
  position: absolute;
  inset: 0;
  overflow: hidden;
}

.bg-blob {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.15;
}

.bg-blob-1 {
  width: 500px;
  height: 500px;
  background: var(--color-primary);
  top: -100px;
  left: -100px;
  animation: blobFloat 20s ease-in-out infinite;
}

.bg-blob-2 {
  width: 400px;
  height: 400px;
  background: var(--color-primary-light);
  bottom: -80px;
  right: -80px;
  animation: blobFloat 25s ease-in-out infinite reverse;
}

@keyframes blobFloat {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(30px, -20px) scale(1.05); }
  66% { transform: translate(-20px, 15px) scale(0.95); }
}

/* === 登录卡片 === */
.login-card {
  position: relative;
  width: 400px;
  padding: var(--space-10);
  background-color: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-lg);
  z-index: 1;
}

.login-header {
  text-align: center;
  margin-bottom: var(--space-8);
}

.login-logo {
  display: inline-flex;
  margin-bottom: var(--space-4);
}

.login-title {
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -0.02em;
  margin-bottom: var(--space-2);
  background: linear-gradient(135deg, var(--color-text-primary), var(--color-text-secondary));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.login-subtitle {
  font-size: 14px;
  color: var(--color-text-muted);
}

/* === 表单 === */
.login-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.login-error {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  background-color: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.2);
  border-radius: var(--radius-md);
  color: var(--color-error);
  font-size: 14px;
  margin-bottom: var(--space-2);
}

/* 深色输入框覆写 */
:deep(.dark-input .el-input__wrapper) {
  background-color: var(--color-surface-elevated);
  border-color: var(--color-border);
  box-shadow: none;
}

:deep(.dark-input .el-input__wrapper:hover) {
  border-color: var(--color-border-light);
}

:deep(.dark-input .el-input__wrapper.is-focus) {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 1px var(--color-primary);
}

:deep(.dark-input .el-input__inner) {
  color: var(--color-text-primary);
  font-size: 15px;
}

:deep(.dark-input .el-input__inner::placeholder) {
  color: var(--color-text-muted);
}

:deep(.dark-input .el-input__prefix) {
  color: var(--color-text-muted);
}

/* 登录按钮 */
.login-btn {
  width: 100%;
  height: 48px;
  margin-top: var(--space-4);
  font-size: 16px;
  font-weight: 500;
  letter-spacing: 0.05em;
  border-radius: var(--radius-lg);
  background: linear-gradient(135deg, var(--color-primary), var(--color-primary-dark));
  border: none;
  transition: all var(--transition-normal);
}

.login-btn:hover {
  background: linear-gradient(135deg, var(--color-primary-light), var(--color-primary));
  box-shadow: var(--shadow-glow);
  transform: translateY(-1px);
}

/* 提示文字 */
.login-hint {
  text-align: center;
  margin-top: var(--space-6);
  font-size: 13px;
  color: var(--color-text-muted);
}

/* 过渡动画 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity var(--transition-fast);
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
