/**
 * App.tsx —— 路由表
 * 登录 / 对话(默认) / 配置中心(模型/技能/MCP/审批)
 */
import { Routes, Route, Navigate } from 'react-router-dom'
import Login from './pages/Login'
import Chat from './pages/Chat'
import AdminLayout from './pages/AdminLayout'
import LlmConfig from './pages/admin/LlmConfig'
import SkillConfig from './pages/admin/SkillConfig'
import McpConfig from './pages/admin/McpConfig'
import ApprovalConfig from './pages/admin/ApprovalConfig'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/chat" element={<Chat />} />
      <Route path="/admin" element={<AdminLayout />}>
        <Route index element={<Navigate to="/admin/llm" replace />} />
        <Route path="llm" element={<LlmConfig />} />
        <Route path="skills" element={<SkillConfig />} />
        <Route path="mcp" element={<McpConfig />} />
        <Route path="approval" element={<ApprovalConfig />} />
      </Route>
      <Route path="/" element={<Navigate to="/chat" replace />} />
      <Route path="*" element={<Navigate to="/chat" replace />} />
    </Routes>
  )
}