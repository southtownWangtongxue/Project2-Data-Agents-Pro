import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { App as AntdApp, ConfigProvider } from 'antd'
import { XProvider } from '@ant-design/x'
import App from './App'
import { buildTheme } from './theme/tokens'
import { appLocale } from './locale'
import './index.css'
/* MiSans 可变字体(小米开源,unicode-range 切片按需加载,中文显示更清晰) */
import 'misans/lib/Normal/MiSansVF.min.css'
/* JetBrains Mono(读数/代码等宽,自托管 400/500 两档) */
import '@fontsource/jetbrains-mono/400.css'
import '@fontsource/jetbrains-mono/500.css'
/* x-markdown 官方主题:2026-10-18 定版只保留深色 */
import '@ant-design/x-markdown/themes/dark.css'

function Root() {
  return (
    <ConfigProvider theme={buildTheme('dark')} locale={appLocale}>
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