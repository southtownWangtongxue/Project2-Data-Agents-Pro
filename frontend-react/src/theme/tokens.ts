/**
 * theme/tokens.ts —— antd ConfigProvider 主题令牌(双模式工厂)
 *
 * 设计语言:中性色体系对齐 GitHub Dark / GitHub Light(2026-10-18),
 * 产品强调色保留品牌紫 #7056F8(交互态/渐变/进度),功能色取 GitHub 语义色。
 * - 暗色(默认):canvas #0D1117 / subtle #161B22 / inset #21262D
 * - 亮色:canvas #FFFFFF / subtle #F6F8FA / neutral #EAEEF2
 *
 * 组件基线对齐 Ant Design X 2.9 官方独立式样板间:
 * layout 背景取 colorBgContainer,侧栏取 colorBgLayout。
 */
import { theme, type ThemeConfig } from 'antd'

export type ThemeMode = 'dark' | 'light'

export const BRAND = '#7056F8'
export const BRAND_LIGHT = '#8B6FFF'

const SHARED = {
  colorPrimary: BRAND,
  colorInfo: BRAND,
  borderRadius: 8,
  fontFamily: "'MiSans VF', 'MiSans', 'PingFang SC', 'Noto Sans SC', 'Microsoft YaHei', sans-serif",
  fontSize: 14,
  wireframe: false,
}

export function buildTheme(_mode: ThemeMode = 'dark'): ThemeConfig {
  /* 2026-10-18 定版:只保留深色(dsh 近黑层级 + 弱描边),mode 参数保留兼容 */
  return {
    algorithm: theme.darkAlgorithm,
    token: {
      ...SHARED,
      colorSuccess: '#3FB950',
      colorWarning: '#D29922',
      colorError: '#F85149',
      colorBgBase: '#0A0A0B',
      colorBgLayout: '#0A0A0B',
      colorBgContainer: '#141416',
      colorBgElevated: '#1C1C1F',
      colorText: '#ECECF1',
      colorTextSecondary: '#A2A2AD',
      colorTextTertiary: '#71717C',
      colorBorder: 'rgba(255, 255, 255, 0.07)',
      colorBorderSecondary: 'rgba(255, 255, 255, 0.05)',
      colorLink: '#7AA2FF',
    },
  }
}

/** 兼容旧引用:默认暗色主题 */
export const cockpitTheme = buildTheme('dark')