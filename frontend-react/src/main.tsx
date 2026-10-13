import React, { useEffect } from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { App as AntdApp, ConfigProvider } from 'antd'
import { XProvider } from '@ant-design/x'
import App from './App'
import { buildTheme } from './theme/tokens'
import { useThemeStore } from './stores/theme'
import { appLocale } from './locale'
import './index.css'
/* x-markdown 官方主题:暗色/亮色两份样式,按 html class 作用域切换 */
import '@ant-design/x-markdown/themes/dark.css'
import '@ant-design/x-markdown/themes/light.css'

function Root() {
  const mode = useThemeStore(s => s.mode)

  /* 切换主题时同步 <html data-theme> 与 x-markdown class */
  useEffect(() => {
    const root = document.documentElement
    root.dataset.theme = mode
    root.classList.toggle('x-markdown-dark', mode === 'dark')
    root.classList.toggle('x-markdown-light', mode === 'light')
  }, [mode])

  return (
    <ConfigProvider theme={buildTheme(mode)} locale={appLocale}>
      {/* AntdApp 提供 App.useApp() 上下文(message/notification 等 hook) */}
      <AntdApp>
        {/* XProvider 统一 Ant Design X 组件的 locale 与主题上下文 */}
        <XProvider locale={appLocale}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </XProvider>
      </AntdApp>
    </ConfigProvider>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
)