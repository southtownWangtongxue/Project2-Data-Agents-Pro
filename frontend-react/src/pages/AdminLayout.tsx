/**
 * pages/AdminLayout.tsx —— 管理后台框架(脚手架占位,admin-config 阶段实现)
 */
import { Outlet } from 'react-router-dom'

export default function AdminLayout() {
  return (
    <div className="h-full p-6">
      <div className="text-lg font-semibold mb-4">配置中心</div>
      <div className="text-[var(--text-2)] text-sm">管理后台搭建中(React 重构进行时)</div>
      <Outlet />
    </div>
  )
}
