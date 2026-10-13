/**
 * bits/TypeText.tsx —— 打字机文本(ReactBits TextType 的轻量实现)
 * 逐字打字 + 光标闪烁,用于欢迎页标题与空态副标题。
 */
import { useEffect, useState } from 'react'

interface Props {
  text: string
  /** 每字间隔(ms) */
  speed?: number
  className?: string
  cursorClassName?: string
  /** 完成后是否保留光标 */
  keepCursor?: boolean
}

export default function TypeText({ text, speed = 90, className = '', cursorClassName = '', keepCursor = false }: Props) {
  const [shown, setShown] = useState('')
  const [done, setDone] = useState(false)

  useEffect(() => {
    setShown('')
    setDone(false)
    let i = 0
    const timer = setInterval(() => {
      i += 1
      setShown(text.slice(0, i))
      if (i >= text.length) {
        clearInterval(timer)
        setDone(true)
      }
    }, speed)
    return () => clearInterval(timer)
  }, [text, speed])

  const showCursor = keepCursor || !done

  return (
    <span className={className}>
      {shown}
      {showCursor && (
        <span
          className={`inline-block w-[2px] h-[1em] translate-y-[2px] ml-0.5 bg-[var(--brand)] align-middle ${cursorClassName}`}
          style={{ animation: 'cursor-blink 1s steps(2) infinite' }}
        />
      )}
      <style>{`
        @keyframes cursor-blink { 0%, 100% { opacity: 1 } 50% { opacity: 0 } }
      `}</style>
    </span>
  )
}