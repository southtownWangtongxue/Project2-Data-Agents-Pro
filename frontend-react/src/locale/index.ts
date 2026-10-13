/**
 * locale/index.ts —— antd + Ant Design X 的中文语言包合并
 * XProvider 的 locale 类型要求同时满足 antdLocale 与 xLocale,故在此合并。
 */
import zhCN from 'antd/locale/zh_CN'
/* Ant Design X 未在 package exports 中暴露子路径,只能按 es 目录引入官方语言包 */
import xZhCN from '@ant-design/x/es/locale/zh_CN'

export const appLocale = {
  ...zhCN,
  ...xZhCN,
}

export default appLocale