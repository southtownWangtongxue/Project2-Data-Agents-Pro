/**
 * pages/AdminLayout.tsx —— 配置中心(侧边导航 + 子路由)
 * 审批配置并入此处(对话内审批的权限范围由管理员在此配置)
 */
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { Alert } from 'antd'
import { api, getToken } from '@/api/client'
import { useThemeStore } from '@/stores/theme'

const MENU = [
  { to: '/admin/llm', label: '模型配置', icon: '◈', desc: '多模型接入 · 全模态能力 · 思考强度' },
  { to: '/admin/skills', label: '技能管理', icon: '◆', desc: 'Skills 安装与启停' },
  { to: '/admin/mcp', label: 'MCP 服务', icon: '◇', desc: 'MCP Server 接入与连通性测试' },
  { to: '/admin/approval', label: '审批策略', icon: '⊘', desc: '高危操作审批档位(对话内审批)' },
]

type SetupStatus = {
  setup_required: boolean
  hints: string[]
  mcp_optional_hint?: string
}

export default function AdminLayout() {
  const navigate = useNavigate()
  const theme = useThemeStore()
  const [setup, setSetup] = useState<SetupStatus | null>(null)

  useEffect(() => {
    if (!getToken()) {
      navigate('/login', { replace: true })
      return
    }
    api<SetupStatus>('/config/setup-status')
      .then(setSetup)
      .catch(() => setSetup(null))
  }, [navigate])

  return (
    <div className="h-full flex bg-[var(--cockpit-900)]">
      {/* 侧边导航 */}
      <aside className="w-60 flex-shrink-0 border-r flex flex-col" style={{ borderColor: 'var(--border)', background: 'var(--panel)' }}>
        <div className="h-12 flex items-center gap-2 px-4 border-b" style={{ borderColor: 'var(--border)' }}>
          <span className="font-semibold text-[13px]">配置中心</span>
          <button type="button" onClick={theme.toggle} title="切换明暗主题"
            className="w-7 h-7 rounded-md border bg-transparent cursor-pointer text-[var(--text-2)] hover:text-[var(--text-1)] transition-colors"
            style={{ borderColor: 'var(--border)' }}>
            {theme.mode === 'dark' ? '☾' : '☀'}
          </button>
          <button type="button" onClick={() => navigate('/chat')}
            className="ml-auto text-[11px] text-[var(--text-3)] hover:text-[var(--brand-light)] bg-transparent border-none cursor-pointer transition-colors">
            ← 返回对话
          </button>
        </div>
        <nav className="flex-1 py-2">
          {MENU.map(m => (
            <NavLink
              key={m.to}
              to={m.to}
              className={({ isActive }) =>
                `block mx-2 mb-0.5 px-3 py-2.5 rounded-lg border transition-colors ${
                  isActive
                    ? 'border-brand/30 bg-brand/10'
                    : 'border-transparent hover:bg-[var(--cockpit-800)]'
                }`
              }
            >
              <div className={`text-[13px] ${'text-[var(--text-1)]'}`}>
                <span className="mr-2 text-brand-light">{m.icon}</span>
                {m.label}
              </div>
              <div className="text-[10px] text-[var(--text-3)] mt-0.5 ml-5">{m.desc}</div>
            </NavLink>
          ))}
        </nav>
      </aside>
      {/* 内容区 */}
      <main className="flex-1 min-w-0 overflow-y-auto p-6">
        {setup?.setup_required && (
          <Alert
            type="warning"
            showIcon
            className="mb-4"
            message={setup.hints?.[0] || '请先配置可用的 LLM 模型'}
            description={
              <span>
                {setup.mcp_optional_hint}
                {' · '}
                <button
                  type="button"
                  className="text-brand-light bg-transparent border-none cursor-pointer underline"
                  onClick={() => navigate('/admin/llm')}
                >
                  前往模型配置
                </button>
              </span>
            }
          />
        )}
        <Outlet />
      </main>
    </div>
  )
}
