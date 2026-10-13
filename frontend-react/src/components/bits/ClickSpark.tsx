/**
 * bits/ClickSpark.tsx —— 点击火花(ReactBits ClickSpark 的轻量实现)
 * 在被包裹元素上叠加一次性射线 + 圆环扩散,600ms 内消散。
 * 用于高价值点击点(建议 chip / 新建会话),克制使用。
 */
import { useCallback, useRef, useState } from 'react'

interface Props {
  children: React.ReactNode
  className?: string
  /** 射线数量 */
  rays?: number
  color?: string
}

interface Spark {
  id: number
  x: number
  y: number
  angle: number
  distance: number
}

let sparkSeq = 0

export default function ClickSpark({ children, className = '', rays = 6, color = '#8B6FFF' }: Props) {
  const ref = useRef<HTMLSpanElement>(null)
  const [sparks, setSparks] = useState<Spark[]>([])

  const fire = useCallback(
    (e: React.MouseEvent) => {
      const rect = ref.current?.getBoundingClientRect()
      if (!rect) return
      const x = e.clientX - rect.left
      const y = e.clientY - rect.top
      const created = Array.from({ length: rays }, (_, i) => ({
        id: ++sparkSeq,
        x,
        y,
        angle: (360 / rays) * i + Math.random() * 18,
        distance: 22 + Math.random() * 16,
      }))
      setSparks(s => [...s, ...created])
      setTimeout(() => {
        const ids = new Set(created.map(c => c.id))
        setSparks(s => s.filter(sp => !ids.has(sp.id)))
      }, 620)
    },
    [rays],
  )

  return (
    <span ref={ref} className={`relative inline-block ${className}`} onClick={fire}>
      {children}
      {/* 射线 */}
      {sparks.map(s => (
        <span
          key={s.id}
          className="pointer-events-none absolute z-10"
          style={{
            left: s.x,
            top: s.y,
            width: 2,
            height: 8,
            borderRadius: 2,
            background: color,
            transformOrigin: 'center',
            animation: `spark-ray 600ms ease-out forwards`,
            // @ts-expect-error CSS 自定义变量
            '--spark-angle': `${s.angle}deg`,
            '--spark-distance': `${s.distance}px`,
          }}
        />
      ))}
      {/* 扩散环 */}
      {sparks.length > 0 && (
        <span
          key={`ring-${sparks[0].id}`}
          className="pointer-events-none absolute z-0 rounded-full"
          style={{
            left: sparks[sparks.length - rays].x - 4,
            top: sparks[sparks.length - rays].y - 4,
            width: 8,
            height: 8,
            border: `1px solid ${color}`,
            animation: 'spark-ring 600ms ease-out forwards',
          }}
        />
      )}
      <style>{`
        @keyframes spark-ray {
          0% { transform: rotate(var(--spark-angle)) translateY(0) scaleY(0.4); opacity: 1 }
          100% { transform: rotate(var(--spark-angle)) translateY(calc(var(--spark-distance) * -1)) scaleY(1); opacity: 0 }
        }
        @keyframes spark-ring {
          0% { transform: scale(0.4); opacity: 0.9 }
          100% { transform: scale(6); opacity: 0 }
        }
      `}</style>
    </span>
  )
}