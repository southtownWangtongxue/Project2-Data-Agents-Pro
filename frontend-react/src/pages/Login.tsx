/**
 * pages/Login.tsx —— 登录页(碳黑驾驶舱风格 + React Bits 视觉)
 *
 * 2026-10 重做:体现项目简介与真实 LOGO(参考根目录 README 定位)——
 * 品牌区(LOGO+标题+副标题)→ 项目简介 → 特性 chips → 登录表单。
 * 阶段 B 视觉:品牌标题 ShinyText 扫光、简介 BlurText 逐词浮现、
 * 登录卡 SpotlightCard 鼠标跟随聚光(组件源码移植自 reactbits.dev)。
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Input, Form, App as AntApp } from 'antd'
import Aurora from '@/components/bits/Aurora'
import ShinyText from '@/components/bits/reactbits/ShinyText'
import BlurText from '@/components/bits/reactbits/BlurText'
import SpotlightCard from '@/components/bits/reactbits/SpotlightCard'
import { useAuthStore } from '@/stores/auth'

/** README 项目定位与特性标签 */
const INTRO = '面向业务人员的多智能体数据分析平台 · 用自然语言对话即可查询、分析与可视化企业数据'
const FEATURES = ['Text-to-SQL', '多智能体协作', '人工审批', '流式响应']

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
    <div className="h-full flex items-center justify-center relative overflow-hidden px-4 py-8">
      <Aurora />
      <div className="relative w-[440px] max-w-full rise-in">
        {/* 🌟 品牌区:真实 LOGO + 扫光标题 + 副标题 */}
        <div className="flex flex-col items-center gap-3 mb-7">
          <img
            src="/logo.png"
            alt="DataAgent Pro"
            width={64}
            height={64}
            className="rounded-2xl shadow-lg"
            style={{ boxShadow: '0 8px 28px rgba(112,86,248,0.35)' }}
          />
          <div className="text-center">
            <ShinyText
              text="DataAgent Pro"
              color="#E6EDF3"
              shineColor="#C4B5FD"
              speed={2.6}
              delay={1.2}
              shineWidth={28}
              softness={0.9}
              glow={0.35}
              className="text-[22px] font-semibold tracking-tight"
            />
            <div className="text-xs text-[var(--text-3)] mt-1">智能业务数据交互平台</div>
          </div>
        </div>

        {/* 登录卡:SpotlightCard 聚光表面(品牌紫光斑 + 描边辉光) */}
        <SpotlightCard
          spotlightColor="#8B6FFF"
          intensity={0.22}
          spotlightSize={380}
          proximity={140}
          borderGlow={0.75}
          className="p-8 shadow-2xl backdrop-blur"
          style={{
            ['--spotlight-card-surface' as string]: 'var(--cockpit-800)',
            ['--spotlight-card-border' as string]: 'var(--border)',
            borderRadius: 16,
          }}
        >
          {/* 项目简介:BlurText 逐词浮现(挂载即播,reduce 动效时直出) */}
          <BlurText
            className="text-[13px] leading-relaxed text-[var(--text-2)] text-center mb-5"
            text={INTRO}
            trigger="load"
            animateBy="words"
            delay={90}
            stepDuration={0.4}
            blur={8}
            distance={24}
            effect="blur"
            staggerFrom="start"
          />

          {/* 特性 chips */}
          <div className="flex flex-wrap justify-center gap-2 mb-7">
            {FEATURES.map(f => (
              <span
                key={f}
                className="mono text-[10px] px-2.5 py-1 rounded-full transition-colors"
                style={{
                  color: 'var(--brand-light)',
                  background: 'rgba(112,86,248,0.10)',
                  border: '1px solid rgba(112,86,248,0.28)',
                }}
              >
                {f}
              </span>
            ))}
          </div>

          <Form form={form} layout="vertical" onFinish={onFinish}>
            <Form.Item
              name="user_name"
              label={<span className="text-[var(--text-2)]">账号</span>}
              rules={[{ required: true, message: '请输入账号' }]}
            >
              <Input size="large" placeholder="用户名" autoFocus autoComplete="username" />
            </Form.Item>
            <Form.Item
              name="password"
              label={<span className="text-[var(--text-2)]">密码</span>}
              rules={[{ required: true, message: '请输入密码' }]}
            >
              <Input.Password size="large" placeholder="密码" autoComplete="current-password" />
            </Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              size="large"
              block
              loading={loading}
              style={{
                background: 'linear-gradient(135deg, #7056F8, #8B6FFF)',
                borderColor: 'transparent',
                marginTop: 4,
              }}
            >
              登 录
            </Button>
          </Form>
        </SpotlightCard>
      </div>
    </div>
  )
}
