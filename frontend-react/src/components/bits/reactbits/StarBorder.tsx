/**
 * StarBorder.tsx —— 星轨描边容器（React Bits `animations/star-border` 的 CSS 等效版）
 *
 * 官方实现用 canvas 逐帧绘制沿圆角矩形运动的光点与拖尾；这里改用
 * conic-gradient + @property 角度动画做「光点绕边」，视觉同源但零 RAF 开销，
 * 适合消息流内多实例（思考卡等）。
 *
 * 用法：<StarBorder color="#8b7bff" radius={12} duration={5}><div>...</div></StarBorder>
 */
import type { CSSProperties, ReactNode } from 'react'

export interface StarBorderProps {
  children: ReactNode
  /** 星轨颜色,默认品牌紫 */
  color?: string
  /** 圆角(px),默认 12 */
  radius?: number
  /** 绕行一圈耗时(秒),默认 5 */
  duration?: number
  /** 描边粗细(px),默认 1 */
  thickness?: number
  /** 容器底色,默认 --cockpit-800 */
  surface?: string
  /** 是否显示外发光,默认 true */
  glow?: boolean
  className?: string
  style?: CSSProperties
}

export default function StarBorder({
  children,
  color = '#8b7bff',
  radius = 12,
  duration = 5,
  thickness = 1,
  surface = 'var(--cockpit-800)',
  glow = true,
  className = '',
  style,
}: StarBorderProps) {
  return (
    <div
      className={`star-border${className ? ` ${className}` : ''}`}
      style={
        {
          '--sb-color': color,
          '--sb-radius': `${radius}px`,
          '--sb-duration': `${duration}s`,
          '--sb-thickness': `${thickness}px`,
          '--sb-surface': surface,
          ...style,
        } as CSSProperties
      }
    >
      {glow && <span className="star-border__glow" aria-hidden="true" />}
      <span className="star-border__ring" aria-hidden="true" />
      {children}
    </div>
  )
}
