/**
 * pages/Login.tsx —— 登录页(碳黑驾驶舱风格)
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Input, Form, App as AntApp } from 'antd'
import Aurora from '@/components/bits/Aurora'
import { useAuthStore } from '@/stores/auth'

export default function Login() {
  const [form] = Form.useForm()
  const navigate = useNavigate()
  const { login, loading } = useAuthStore()
  const { message } = AntApp.useApp()

  const onFinish = async (values: { user_name: string; password: string }) => {
    try {
      await login(values.user_name, values.password)
      navigate('/chat', { replace: true })
    } catch (e) {
      message.error((e as Error).message || '登录失败')
    }
  }

  return (
    <div className="h-full flex items-center justify-center relative overflow-hidden">
      <Aurora />
      <div className="relative w-[400px] rise-in">
        <div className="flex items-center gap-3 mb-8">
          <div
            className="w-9 h-9 rounded-lg flex items-center justify-center text-white font-bold"
            style={{ background: 'linear-gradient(135deg, #7056F8, #8B6FFF)' }}
          >
            D
          </div>
          <div>
            <div className="text-lg font-semibold text-[var(--text-1)]">DataAgent Pro</div>
            <div className="text-xs text-[var(--text-3)]">智能业务数据交互平台</div>
          </div>
        </div>
        <div className="bg-[var(--cockpit-800)] border border-[var(--border)] rounded-2xl p-8 shadow-2xl backdrop-blur">
          <Form form={form} layout="vertical" onFinish={onFinish} initialValues={{ user_name: 'admin' }}>
            <Form.Item
              name="user_name"
              label={<span className="text-[var(--text-2)]">账号</span>}
              rules={[{ required: true, message: '请输入账号' }]}
            >
              <Input size="large" placeholder="用户名" autoFocus />
            </Form.Item>
            <Form.Item
              name="password"
              label={<span className="text-[var(--text-2)]">密码</span>}
              rules={[{ required: true, message: '请输入密码' }]}
            >
              <Input.Password size="large" placeholder="密码" />
            </Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              size="large"
              block
              loading={loading}
              style={{ background: '#7056F8', borderColor: '#7056F8' }}
            >
              登 录
            </Button>
          </Form>
        </div>
        <div className="text-center text-xs text-[var(--text-3)] mt-6 mono tracking-widest">
          NATURAL LANGUAGE → DATA → INSIGHT
        </div>
      </div>
    </div>
  )
}
