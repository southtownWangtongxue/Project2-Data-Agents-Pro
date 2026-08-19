---
name: add-reference-nav-entry
overview: 在 docs/.vitepress/config.mts 的顶部导航栏 nav 中新增"参考"下拉分组，内含"DeepSeek Harness 研读笔记"子项，使该文档从顶部导航栏可直接点击进入。
todos:
  - id: add-nav-dropdown
    content: 在 config.mts 的 nav 追加"参考"下拉项，含研读笔记子链接
    status: completed
  - id: verify-config
    content: 用 read_lints 校验 config.mts 语法并核对链接一致性
    status: completed
    dependencies:
      - add-nav-dropdown
---

## 用户需求

`docs/reference/deepseek-harness-notes.md` 在文档站点界面没有点击入口，用户无法从导航进入该文档。

## 产品概述

在 VitePress 文档站点的顶部导航栏新增一个"参考"下拉分组，使已落盘的 DeepSeek Harness 研读笔记可通过导航栏点击访问，并为后续扩展更多参考文档预留结构。

## 核心功能

- 在顶部导航栏（nav）新增"参考"下拉菜单项
- 下拉菜单内含"DeepSeek Harness 研读笔记"子项，点击直达 `/reference/deepseek-harness-notes`
- 侧边栏已有的 `/reference/` 分组保持不变，进入该页后顶部导航栏高亮"参考"父级

## 技术栈

- 文档框架：VitePress（基于 `docs/.vitepress/config.mts` 的 `themeConfig` 配置）
- 配置文件：TypeScript（`config.mts`）

## 实现方案

### 策略

在 `themeConfig.nav` 数组中追加一个含 `items` 的下拉分组项（VitePress 标准下拉结构），复用侧边栏已注册且已验证一致的链接路径，不新建文件、不改侧边栏。

### 关键技术决策

- 采用 VitePress 原生 nav 下拉语法 `{ text, items: [{ text, link }] }`，与现有单链接 nav 项共存，风格统一、零额外依赖。
- 链接值 `/reference/deepseek-harness-notes` 直接复用侧边栏已落盘路径，避免路径不一致导致 404。
- 不修改已有的 `sidebar['/reference/']`，保持"导航栏入口 + 侧边栏分组"双层可达。

### 性能与可靠性

- 纯配置改动，无运行时开销；VitePress 构建期校验链接与 frontmatter，无新增性能瓶颈。
- 改动面极小（仅追加 1 个 nav 项），不影响现有页面与导航高亮逻辑。

## 实现注意

- 追加位置放在现有 nav 项之后（如"项目文档"项之后），保持导航顺序合理。
- 链接必须与 `docs/reference/deepseek-harness-notes.md` 文件名严格一致（已确认文件存在）。
- 改完用 `read_lints` 校验 `config.mts` 无 TypeScript 语法错误。
- 文档类配置改动，无应用功能代码，不触发 Chrome DevTools 浏览器端到端验证规则。

## 目录结构

```
docs/
└── .vitepress/
    └── config.mts   # [MODIFY] 在 themeConfig.nav 数组追加"参考"下拉分组项，
                     # 内含 { text: 'DeepSeek Harness 研读笔记', link: '/reference/deepseek-harness-notes' }。
                     # 保持其余 nav 与 sidebar 配置不变，确保链接与已落盘文件一致。
```