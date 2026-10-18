/**
 * highlight-js.d.ts —— highlight.js 子路径导入的本地类型声明
 *
 * highlight.js 10.x 仅为主入口提供类型(types/index.d.ts),`lib/core` 与
 * `lib/languages/*` 子路径无声明。@types/highlight.js 已停止维护且不覆盖
 * 全部语言子路径,故用最小本地声明收口(any 化,避免为第三方库扩类型)。
 */
declare module 'highlight.js/lib/core' {
  const hljs: {
    getLanguage(name: string): unknown
    registerLanguage(name: string, def: unknown): void
    highlight(code: string, { language }: { language: string }): { value: string }
    highlightAuto(code: string): { value: string }
  }
  export default hljs
}

declare module 'highlight.js/lib/languages/*' {
  const def: unknown
  export default def
}
