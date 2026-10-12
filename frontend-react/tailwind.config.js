import tailwindcssAnimate from 'tailwindcss-animate'

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        /* 碳黑驾驶舱三层底 + 紫磷光强调 + 功能色 */
        cockpit: {
          900: '#0D0D0F',
          800: '#18181B',
          700: '#1F1F23',
          600: '#27272A',
        },
        brand: {
          DEFAULT: '#7056F8',
          light: '#8B6FFF',
        },
        success: '#10B981',
        warning: '#F59E0B',
        danger: '#EF4444',
      },
      fontFamily: {
        sans: ['PingFang SC', 'Noto Sans SC', 'Microsoft YaHei', 'sans-serif'],
        mono: ['DIN Next', 'JetBrains Mono', 'SFMono-Regular', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [tailwindcssAnimate],
}
