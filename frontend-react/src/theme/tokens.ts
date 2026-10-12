/**
 * theme/tokens.ts —— antd ConfigProvider 主题令牌
 * 碳黑驾驶舱 + 紫磷光:唯一强调色 #7056F8,大面积碳黑层次
 */
import { theme } from 'antd'

export const cockpitTheme = {
  algorithm: theme.darkAlgorithm,
  token: {
    colorPrimary: '#7056F8',
    colorInfo: '#7056F8',
    colorBgBase: '#0D0D0F',
    colorBgContainer: '#18181B',
    colorBgElevated: '#1F1F23',
    colorText: 'rgba(255, 255, 255, 0.88)',
    colorTextSecondary: 'rgba(255, 255, 255, 0.65)',
    colorBorder: 'rgba(255, 255, 255, 0.08)',
    colorBorderSecondary: 'rgba(255, 255, 255, 0.06)',
    colorSuccess: '#10B981',
    colorWarning: '#F59E0B',
    colorError: '#EF4444',
    borderRadius: 8,
    fontFamily: "'PingFang SC', 'Noto Sans SC', 'Microsoft YaHei', sans-serif",
  },
}
