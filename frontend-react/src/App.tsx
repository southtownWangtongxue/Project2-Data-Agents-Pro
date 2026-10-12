/**
 * App.tsx —— 路由表
 * 登录 / 对话(默认) / 管理后台(LLM/技能/MCP/定时/审批配置)
 */
import { Routes, Route, Navigate } from 'react-router-dom'
import Login from './pages/Login'
import Chat from './pages/Chat'
import AdminLayout from './pages/AdminLayout'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/chat" element={<Chat />} />
      <Route path="/admin" element={<AdminLayout />} />
      <Route path="/" element={<Navigate to="/chat" replace />} />
      <Route path="*" element={<Navigate to="/chat" replace />} />
    </Routes>
  )
}
