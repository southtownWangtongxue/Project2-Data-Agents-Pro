/**
 * SpotlightCard.tsx —— React Bits 官方组件（源码移植，TS 化）
 *
 * 来源：github.com/DavidHDev/react-bits → src/content/Components/SpotlightCard
 * 鼠标跟随的聚光卡片：指针靠近时光斑掠过卡面、描边亮起（proximity 半
 * 径内激活），离开平滑消退。本项目将其作为「碳黑驾驶舱」卡片的统一
 * 表面（结果表/图表/SQL/工具卡），替代平面 1px 描边。
 * 配套样式见 index.css 的 .spotlight-card 段（padding 归零，由使用方控制）。
 *
 * 性能：RAF 仅在指针进入 proximity 范围或按压时运行，离开即停。
 */
'use client'

import { useEffect, useRef } from 'react'
import type { CSSProperties, MouseEvent, ReactNode } from 'react'

const THEMES = {
  dark: {
    surface: '#111111',
    border: 'rgba(255, 255, 255, 0.08)',
    shadow: '0 24px 48px -24px rgba(0, 0, 0, 0.6)',
    light: '#ffffff',
    fill: 1,
    edge: 1,
  },
  light: {
    surface: '#ffffff',
    border: 'rgba(24, 24, 27, 0.1)',
    shadow: '0 1px 2px rgba(24, 24, 27, 0.04), 0 18px 40px -20px rgba(24, 24, 27, 0.16)',
    light: '#18181b',
    fill: 0.28,
    edge: 0.7,
  },
} as const

type ThemeName = keyof typeof THEMES

const SHAPES = ['circle', 'beam']

const NOISE =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")"

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value))

const falloff = (color: string, softness: number): string => {
  const soft = clamp(softness, 0, 1)
  const core = (1 - soft) ** 1.5 * 0.85
  const stop = (alpha: number, at: number) =>
    `color-mix(in srgb, ${color} ${(alpha * 100).toFixed(2)}%, transparent) ${(at * 100).toFixed(2)}%`
  const list = [stop(1, 0)]
  for (let i = 0; i <= 14; i++) {
    const t = core + ((1 - core) * i) / 14
    const g = (t - core) / (1 - core)
    const smooth = 1 - g * g * (3 - 2 * g)
    const glow = Math.exp(-4.6 * g * g) * (1 - g ** 6)
    list.push(stop(smooth + (glow - smooth) * soft, t))
  }
  return list.join(', ')
}

export interface SpotlightCardProps {
  children?: ReactNode
  className?: string
  style?: CSSProperties
  /** 聚光灯颜色，默认随主题 */
  spotlightColor?: string
  /** 光斑强度 0~1，默认 0.15 */
  intensity?: number
  /** 光斑半径（px），默认 240 */
  spotlightSize?: number
  /** 边缘柔和度 0~1，默认 0.7 */
  softness?: number
  /** 光斑形状，默认 circle */
  shape?: 'circle' | 'beam'
  /** 描边辉光强度 0~1，默认 0.6 */
  borderGlow?: number
  /** 指针靠近多少 px 内激活，默认 80 */
  proximity?: number
  /** 跟随平滑 0~1（越大越迟缓），默认 0.3 */
  smoothing?: number
  /** 无指针时环境漂移光，默认 false */
  ambient?: boolean
  /** 按压增亮，默认 true */
  flare?: boolean
  /** 噪点强度 0~1，默认 0 */
  grain?: number
  /** 主题，默认 dark */
  theme?: ThemeName
  /** 点击回调（透传根节点，ToolCard 等可点击卡片用） */
  onClick?: (event: MouseEvent<HTMLDivElement>) => void
}

export default function SpotlightCard({
  children,
  className = '',
  style,
  spotlightColor,
  intensity = 0.15,
  spotlightSize = 240,
  softness = 0.7,
  shape = 'circle',
  borderGlow = 0.6,
  proximity = 80,
  smoothing = 0.3,
  ambient = false,
  flare = true,
  grain = 0,
  theme = 'dark',
  ...rest
}: SpotlightCardProps) {
  const rootRef = useRef<HTMLDivElement>(null)
  const lightRef = useRef<HTMLSpanElement>(null)
  const grainRef = useRef<HTMLSpanElement>(null)
  const edgeRef = useRef<HTMLSpanElement>(null)
  const wakeRef = useRef<(() => void) | null>(null)
  const palette = THEMES[theme] ?? THEMES.dark
  const color = spotlightColor ?? palette.light
  const form = SHAPES.includes(shape) ? shape : 'circle'
  const settings = {
    shape: form,
    fill: falloff(color, softness),
    edge: falloff(color, 1),
    size: Math.max(20, spotlightSize),
    intensity: clamp(intensity, 0, 1) * palette.fill,
    borderGlow: clamp(borderGlow, 0, 1) * palette.edge,
    proximity: Math.max(0, proximity),
    smoothing: clamp(smoothing, 0, 1),
    ambient,
    flare,
    grain: clamp(grain, 0, 1),
  }
  const settingsRef = useRef(settings)
  settingsRef.current = settings

  useEffect(() => {
    wakeRef.current?.()
  })

  useEffect(() => {
    const root = rootRef.current
    const light = lightRef.current
    const noise = grainRef.current
    const edge = edgeRef.current
    if (!root || !light || !noise || !edge) return undefined

    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
    const state = { x: 0, y: 0, presence: 0, flare: 0, time: Math.random() * 60, pressed: false, visible: true }
    const pointer = { x: 0, y: 0, active: false }
    const drawn = { light: '', edge: '', noise: '' }
    let focus: Element | null = null
    let raf = 0
    let last = 0
    let alive = true

    const gradient = (s: typeof settings, size: number, x: number, y: number, stops: string) => {
      if (s.shape === 'beam') {
        const reach = Math.max(size * 0.6, y + size * 0.55)
        return `radial-gradient(${(size * 0.55).toFixed(1)}px ${reach.toFixed(1)}px at ${x.toFixed(1)}px 0px, ${stops})`
      }
      return `radial-gradient(circle ${size.toFixed(1)}px at ${x.toFixed(1)}px ${y.toFixed(1)}px, ${stops})`
    }

    const paint = (s: typeof settings) => {
      const size = s.size * (1 + 0.2 * state.flare)
      const boost = 1 + 0.7 * state.flare
      const fill = gradient(s, size, state.x, state.y, s.fill)
      const rim = gradient(s, size * 0.6, state.x, s.shape === 'beam' ? 0 : state.y, s.edge)
      if (fill !== drawn.light) {
        drawn.light = fill
        light.style.background = fill
      }
      if (rim !== drawn.edge) {
        drawn.edge = rim
        edge.style.background = rim
      }
      light.style.opacity = String(Math.min(1, state.presence * s.intensity * boost))
      edge.style.opacity = String(Math.min(1, state.presence * s.borderGlow * boost))
      const grainy = s.grain > 0 ? gradient(s, size, state.x, state.y, '#000 0%, transparent 100%') : 'none'
      if (grainy !== drawn.noise) {
        drawn.noise = grainy
        noise.style.webkitMaskImage = grainy
        noise.style.maskImage = grainy
      }
      noise.style.opacity = String(state.presence * s.grain)
    }

    const tick = (now: number) => {
      raf = 0
      if (!alive) return
      const s = settingsRef.current
      const dt = Math.min(0.05, Math.max(0.001, (now - last) / 1000))
      last = now
      const rect = root.getBoundingClientRect()
      let tx = state.x
      let ty = state.y
      let target = 0
      if (focus && root.contains(focus)) {
        const box = focus.getBoundingClientRect()
        tx = box.left + box.width / 2 - rect.left
        ty = box.top + box.height / 2 - rect.top
        target = 1
      } else if (pointer.active) {
        tx = pointer.x - rect.left
        ty = pointer.y - rect.top
        const gap = Math.hypot(Math.max(0, -tx, tx - rect.width), Math.max(0, -ty, ty - rect.height))
        if (gap === 0) target = 1
        else if (s.proximity > 0) target = Math.max(0, 1 - gap / s.proximity) ** 2
      }
      if (target < 0.6 && s.ambient && state.visible) {
        if (!reduce) state.time += dt
        const drift = 0.6 - target
        tx += (rect.width * (0.5 + 0.34 * Math.sin(state.time * 0.43)) - tx) * (drift / 0.6)
        ty += (rect.height * (0.5 + 0.3 * Math.sin(state.time * 0.61 + 1.3)) - ty) * (drift / 0.6)
        target = 0.6
      }
      if (state.presence < 0.02 && target > 0 && !s.ambient) {
        state.x = tx
        state.y = ty
      }
      const follow = reduce || s.smoothing === 0 ? 1 : 1 - Math.exp(-dt / (0.015 + s.smoothing * 0.22))
      state.x += (tx - state.x) * follow
      state.y += (ty - state.y) * follow
      const fade = reduce ? 1 : 1 - Math.exp(-dt / (target > state.presence ? 0.1 : 0.32))
      state.presence += (target - state.presence) * fade
      if (Math.abs(target - state.presence) < 0.002) state.presence = target
      const press = state.pressed && s.flare && !reduce ? 1 : 0
      state.flare += (press - state.flare) * (1 - Math.exp(-dt / (press ? 0.05 : 0.28)))
      if (Math.abs(press - state.flare) < 0.002) state.flare = press
      paint(s)
      const moving = Math.abs(tx - state.x) > 0.1 || Math.abs(ty - state.y) > 0.1
      const settled = !moving && state.presence === target && state.flare === press
      if (!settled || (s.ambient && state.visible && !reduce)) raf = requestAnimationFrame(tick)
    }

    const wake = () => {
      if (raf || !alive) return
      last = performance.now()
      raf = requestAnimationFrame(tick)
    }
    wakeRef.current = wake

    const onMove = (event: PointerEvent) => {
      pointer.x = event.clientX
      pointer.y = event.clientY
      pointer.active = true
      if (state.presence > 0 || settingsRef.current.proximity > 0 || root.contains(event.target as Node | null)) wake()
    }
    const onOut = (event: PointerEvent) => {
      if (event.relatedTarget) return
      pointer.active = false
      wake()
    }
    const onDown = (event: PointerEvent) => {
      pointer.x = event.clientX
      pointer.y = event.clientY
      pointer.active = true
      state.pressed = true
      wake()
    }
    const onUp = (event: PointerEvent) => {
      if (event.pointerType !== 'mouse') pointer.active = false
      if (!state.pressed && event.pointerType === 'mouse') return
      state.pressed = false
      wake()
    }
    const onFocusIn = (event: FocusEvent) => {
      if (!(event.target instanceof Element) || !event.target.matches(':focus-visible')) return
      focus = event.target
      wake()
    }
    const onFocusOut = (event: FocusEvent) => {
      if (root.contains(event.relatedTarget as Node | null)) return
      focus = null
      wake()
    }
    const onScroll = () => {
      if (pointer.active || state.presence > 0) wake()
    }

    const observer = new IntersectionObserver(entries => {
      state.visible = entries.some(entry => entry.isIntersecting)
      if (state.visible) wake()
    })
    observer.observe(root)
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    window.addEventListener('pointercancel', onUp)
    window.addEventListener('scroll', onScroll, { capture: true, passive: true })
    document.addEventListener('pointerout', onOut)
    root.addEventListener('pointerdown', onDown)
    root.addEventListener('focusin', onFocusIn)
    root.addEventListener('focusout', onFocusOut)
    wake()

    return () => {
      alive = false
      cancelAnimationFrame(raf)
      observer.disconnect()
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      window.removeEventListener('pointercancel', onUp)
      window.removeEventListener('scroll', onScroll, { capture: true })
      document.removeEventListener('pointerout', onOut)
      root.removeEventListener('pointerdown', onDown)
      root.removeEventListener('focusin', onFocusIn)
      root.removeEventListener('focusout', onFocusOut)
      wakeRef.current = null
    }
  }, [])

  return (
    <div
      ref={rootRef}
      className={`spotlight-card${className ? ` ${className}` : ''}`}
      style={
        {
          '--spotlight-card-surface': palette.surface,
          '--spotlight-card-border': palette.border,
          '--spotlight-card-shadow': palette.shadow,
          ...style,
        } as CSSProperties
      }
      {...rest}
    >
      <span ref={lightRef} className="spotlight-card__light" aria-hidden="true" />
      <span ref={grainRef} className="spotlight-card__grain" style={{ backgroundImage: NOISE }} aria-hidden="true" />
      {children}
      <span className="spotlight-card__border" aria-hidden="true" />
      <span ref={edgeRef} className="spotlight-card__edge" aria-hidden="true" />
    </div>
  )
}
