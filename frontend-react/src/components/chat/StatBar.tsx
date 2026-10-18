/**
 * StatBar.tsx —— 底部读数条:三统计弹窗(等分排布)
 *
 * 2026-10-18 按验收反馈调整:
 * - 移除「配置中心」入口(配置入口统一收在侧栏账户菜单,底部不再重复)
 * - 三段**等分**:每段 flex-1 居中,组间 1px 分隔线(参考 DeepSeek 读数条)
 * - 三项常驻显示(无数据走占位,不整项消失)
 */
import { SessionStatsPopover, TokenUsagePopover, ContextUsagePopover } from './StatPopovers'

export default function StatBar() {
  /* 2026-10-18:dsh 参考——读数条无分隔线、无顶边框,纯文字三段等分 */
  return (
    <div className="w-full px-4 pb-2">
      <div className="mx-auto flex items-stretch" style={{ maxWidth: 840 }}>
        {/* 左 1/3:会话统计 */}
        <span className="flex-1 flex justify-center">
          <SessionStatsPopover />
        </span>
        {/* 中 1/3:Token 用量 */}
        <span className="flex-1 flex justify-center">
          <TokenUsagePopover />
        </span>
        {/* 右 1/3:上下文已用 */}
        <span className="flex-1 flex justify-center">
          <ContextUsagePopover />
        </span>
      </div>
    </div>
  )
}
