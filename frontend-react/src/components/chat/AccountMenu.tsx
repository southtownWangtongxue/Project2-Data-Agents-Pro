/**
 * AccountMenu.tsx —— 侧栏底部账户菜单(参考 dsh 样式)
 *
 * 2026-10-18 重做:
 * - 自定义 popupRender 菜单(不用 antd Menu 默认样式):圆角 12 玻璃面、
 *   整行 hover 背景高亮、图标 16px、字号 13.5px(对齐 dsh 的「设置/退出登录」)
 * - 触发行为账户行胶囊:hover 背景色变化,点击展开
 * - 配置中心仅管理员可见(后端口径 user_type==='00',兼容旧值 'admin')
 */
import { Dropdown } from 'antd'
import { useNavigate } from 'react-router-dom'
import Icon, { type IconName } from '@/components/bits/Icon'
import { useAuthStore } from '@/stores/auth'

const ROLE_LABEL: Record<string, string> = {
  '00': '管理员',
  admin: '管理员',
}

/** 菜单行:图标 + 文案,hover 整行背景(与 dsh 一致) */
function MenuRow({ icon, label, danger, onClick }: {
  icon: IconName
  label: string
  danger?: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg border-none bg-transparent cursor-pointer text-left transition-colors"
      style={{ color: danger ? 'var(--danger)' : 'var(--text-1)' }}
      onMouseEnter={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.06)' }}
      onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
    >
      <Icon name={icon} size={16} />
      <span className="text-[14px]">{label}</span>
    </button>
  )
}

export default function AccountMenu() {
  const auth = useAuthStore()
  const navigate = useNavigate()
  const user = auth.user
  const isAdmin = user?.user_type === '00' || user?.user_type === 'admin'
  const displayName = user?.user_name || user?.nick_name || '未登录'

  return (
    <Dropdown
      trigger={['click']}
      placement="topLeft"
      styles={{ root: { zIndex: 60 } }}
      popupRender={() => (
        <div
          className="w-[228px] p-1.5 rounded-xl"
          style={{ background: 'var(--cockpit-700)', border: '1px solid var(--border)', boxShadow: 'var(--shadow-card)' }}
        >
          {/* 账户信息:昵称 + 角色(弱化,不做成可点击项) */}
          <div className="px-3 py-2 mb-1">
            <div className="flex items-center gap-1.5 text-[14px] font-medium text-[var(--text-1)]">
              <Icon name="userSmile" size={15} color="var(--brand-light)" />
              <span className="truncate">{user?.nick_name || user?.user_name || '未登录'}</span>
              {isAdmin && (
                <span
                  className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[12px] mono flex-shrink-0"
                  style={{ color: 'var(--brand-light)', background: 'rgba(109,94,246,0.14)' }}
                >
                  <Icon name="shieldCheck" size={11} />
                  {ROLE_LABEL[user?.user_type || ''] || '管理员'}
                </span>
              )}
            </div>
            <div className="mono text-[12px] text-[var(--text-3)] mt-0.5 truncate">{user?.user_name || '—'}</div>
          </div>
          {isAdmin && <MenuRow icon="settings" label="配置中心" onClick={() => navigate('/admin/llm')} />}
          <MenuRow icon="logout" label="退出登录" danger onClick={() => auth.logout()} />
        </div>
      )}
    >
      <button
        type="button"
        title="账户菜单"
        className="flex items-center gap-2.5 min-w-0 w-full px-2.5 py-2 rounded-lg bg-transparent border-none cursor-pointer text-left transition-colors"
        onMouseEnter={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.05)' }}
        onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
      >
        <span
          className="w-7 h-7 rounded-full flex items-center justify-center text-[12px] text-white flex-shrink-0"
          style={{ background: 'linear-gradient(135deg,#2a2a30,#3a3a42)' }}
        >
          {(displayName || 'U').slice(0, 1).toUpperCase()}
        </span>
        <span className="mono text-[14px] text-[var(--text-1)] truncate flex-1">{displayName}</span>
        <Icon name="arrowDown" size={13} className="flex-shrink-0 text-[var(--text-3)]" />
      </button>
    </Dropdown>
  )
}
