/**
 * theme/tokens.ts —— antd ConfigProvider 主题令牌(双模式工厂)
 *
 * 设计语言:「碳黑驾驶舱 + 紫磷光」
 * - 暗色(默认):三层碳黑 #0D0D0F / #18181B / #1F1F23,品牌紫 #7056F8 为唯一强调色
 * - 亮色:同一套语义令牌映射到浅色三层,保证切换时层级关系不变
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
  colorSuccess: '#10B981',
  colorWarning: '#F59E0B',
  colorError: '#EF4444',
  borderRadius: 8,
  fontFamily: "'PingFang SC', 'Noto Sans SC', 'Microsoft YaHei', sans-serif",
  fontSize: 14,
  wireframe: false,
}

export function buildTheme(mode: ThemeMode): ThemeConfig {
  const dark = mode === 'dark'
  return {
    algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm,
    token: {
      ...SHARED,
      colorBgBase: dark ? '#0D0D0F' : '#F2F2F5',
      colorBgLayout: dark ? '#0D0D0F' : '#FAFAFB',
      colorBgContainer: dark ? '#18181B' : '#FFFFFF',
      colorBgElevated: dark ? '#1F1F23' : '#FFFFFF',
      colorText: dark ? 'rgba(255, 255, 255, 0.88)' : 'rgba(0, 0, 0, 0.88)',
      colorTextSecondary: dark ? 'rgba(255, 255, 255, 0.65)' : 'rgba(0, 0, 0, 0.62)',
      colorTextTertiary: dark ? 'rgba(255, 255, 255, 0.45)' : 'rgba(0, 0, 0, 0.45)',
      colorBorder: dark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.10)',
      colorBorderSecondary: dark ? 'rgba(255, 255, 255, 0.06)' : 'rgba(0, 0, 0, 0.06)',
    },
  }
}

/** 兼容旧引用:默认暗色主题 */
export const cockpitTheme = buildTheme('dark')