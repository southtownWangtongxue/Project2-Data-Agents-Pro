/**
 * bits/Aurora.tsx —— 呼吸极光背景(ReactBits Aurora 的零依赖 CSS 实现)
 * 仅用于欢迎页/登录页等空态,营造"碳黑驾驶舱里的数据极光"氛围。
 */
export default function Aurora() {
  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none" aria-hidden>
      {/* 三层极光带:不同色相/速度/模糊,叠加出极光漂移感 */}
      <div
        className="absolute -top-[30%] left-[10%] w-[70%] h-[70%] rounded-full opacity-[0.18] blur-[90px]"
        style={{
          background: 'radial-gradient(closest-side, #7056F8, transparent)',
          animation: 'aurora-drift-a 18s ease-in-out infinite',
        }}
      />
      <div
        className="absolute -bottom-[40%] right-[0%] w-[60%] h-[60%] rounded-full opacity-[0.14] blur-[100px]"
        style={{
          background: 'radial-gradient(closest-side, #8B6FFF, transparent)',
          animation: 'aurora-drift-b 22s ease-in-out infinite',
        }}
      />
      <div
        className="absolute top-[20%] right-[25%] w-[45%] h-[45%] rounded-full opacity-[0.10] blur-[80px]"
        style={{
          background: 'radial-gradient(closest-side, #10B981, transparent)',
          animation: 'aurora-drift-a 26s ease-in-out infinite reverse',
        }}
      />
      {/* 极细网格:驾驶舱的"数据栅格"暗示 */}
      <div
        className="absolute inset-0 opacity-[0.35]"
        style={{
          backgroundImage:
            'linear-gradient(var(--aurora-grid) 1px, transparent 1px), linear-gradient(90deg, var(--aurora-grid) 1px, transparent 1px)',
          backgroundSize: '48px 48px',
          maskImage: 'radial-gradient(ellipse at center, black 30%, transparent 75%)',
          WebkitMaskImage: 'radial-gradient(ellipse at center, black 30%, transparent 75%)',
        }}
      />
      <style>{`
        @keyframes aurora-drift-a {
          0%, 100% { transform: translate3d(0, 0, 0) scale(1); }
          33% { transform: translate3d(6%, 4%, 0) scale(1.12); }
          66% { transform: translate3d(-4%, 7%, 0) scale(0.94); }
        }
        @keyframes aurora-drift-b {
          0%, 100% { transform: translate3d(0, 0, 0) scale(1); }
          50% { transform: translate3d(-8%, -6%, 0) scale(1.18); }
        }
      `}</style>
    </div>
  )
}