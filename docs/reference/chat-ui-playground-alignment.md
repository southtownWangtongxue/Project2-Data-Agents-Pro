# 对话界面对齐官方样板间规范

> 基线：Ant Design X 2.9 官方「模型样板间 → 独立式（独立 WebApp 模式）」
> 文档地址：<https://x.ant.design/docs/playground/independent-cn>
> 适用范围：`frontend-react/src/pages/Chat.tsx` 及其 `components/chat/*`

本文档记录对话工作台与官方独立式样板间的对应关系，以及本项目的业务扩展点。新增 UI 前请先在此确认落点，避免同一职责出现两套实现。

## 1. 布局结构

官方为「三段式」：左侧会话栏 + 右侧对话区（消息区在上、输入区在下），**不设顶栏**。

| 官方结构 | 本项目实现 | 说明 |
|---|---|---|
| `layout`（100vh flex） | `pages/Chat.tsx` 最外层 `h-screen flex` | 主区背景取 `colorBgContainer` |
| `side`（280px） | `components/chat/ChatSidebar.tsx` | `colorBgLayout` 80% 透明，可折叠为 48px 图标条；<1024px 默认折叠 |
| logo 区 | 侧栏顶部品牌标识 + 折叠按钮 | 官方为 logo + 名称 |
| `Conversations` | 同名组件（`groupable` + `creation` + `menu`） | 会话按「今天/昨天/更早」分组；菜单扩展「重命名 / 长期目标 / 删除」 |
| `sideFooter` | 侧栏底部账户区 | 头像 + 用户名 + 明暗主题切换 |
| `chat`（flex column, justify-between） | `pages/Chat.tsx` 中列 | — |
| `chatList`（flex-1，overflow-y auto，居中） | `MessageList` / `WelcomePanel` | 消息容器 `max-width: 940` |
| `chatSender`（底部固定区） | `SenderInput` + `StatBar` | 读数条贴近输入区下方，宽度与 Sender 对齐（840） |

## 2. 消息气泡

| 能力 | 官方 | 本项目 |
|---|---|---|
| 容器 | `Bubble.List` + `role` 配置 | 同（`MessageList.tsx`），`autoScroll` |
| 用户消息 | `placement: end` | `variant: filled` + `shape: corner` |
| AI 正文 | `contentRender` → `XMarkdown` | `MessageItem.tsx` 中 `Bubble` + `XMarkdown`，`streaming.hasNextChunk` 跟随流式状态 |
| 流式提示 | `.ant-bubble-content-updating` 底部渐变线 | 保留官方类名，渐变改品牌紫（`index.css`） |
| footer | `Actions`（分页/重试/复制/语音/反馈） | `MessageActions.tsx`：重新生成 / 复制 / 点赞点踩（反馈仅本地，见下） |
| 领域富卡片 | 官方无 | SQL / 结果表 / 图表 / 工具 / 审批 / 计划 / 追问等以 `variant: borderless` item 承载 |

### 步骤链

官方用 `ThoughtChain` 表达执行过程；本项目按 `step_id` 分组，每个步骤块是一个 `ThoughtChain`（单 item，`line={false}`）：

- 状态：`loading`（运行中）/ `success`（完成）；
- 折叠语义（**已确认，不得回退**）：运行中展开 → 完成 2s 自动折叠 → 用户点击优先；
- 组内固定类型序：思考（reasoning/thinking）→ 工具（tool）→ 正文 / SQL / 结果 / 图表。

## 3. 思考与工具

| 组件 | 官方 | 本项目 |
|---|---|---|
| 思考内容 | `Think` | `ReasoningCard`（推理增量）与 `MessageItem.ThinkingBlock`（节点状态）均使用 `Think` |
| 工具调用 | 官方无专门组件 | `ToolCard.tsx`（折叠态存组件本地 state，不改写 store 对象） |

## 4. 输入区

官方结构：`Prompts`（建议，空输入时可见）在上，`Sender` 在下。

| 能力 | 本项目实现 |
|---|---|
| 建议 | `Prompts`（来自 `/chat/suggestions`，最多 4 条，点击直接发送；生成中与有输入时隐藏） |
| 输入 | `Sender`（`submitType=enter`、`autoSize` 2~6 行、生成中显示停止按钮） |
| 模式切换 | `Sender.Header` 内 antd `Segmented`（数据分析 / 研究报告 / 文档智读 / 通用任务） |
| 联网搜索 | `Sender.Header` 内 antd `Switch` |
| 思考指示 | 模型开启思考模式时显示 `THINKING` 标记 |
| 模型选择 | `Sender.Header` 右侧 `ModelSelector` |
| 附件上传 | **未启用**：后端暂无对话侧上传端点，`Attachments` 不接入（`image_input` 仅作模型能力声明） |

## 5. 空态

官方：`Welcome`（`variant="borderless"`）+ 双列 `Prompts`。

本项目：`WelcomePanel.tsx` —— `Welcome`（打字机标题 + Aurora 背景 + 文档入口）+ 双列 `Prompts`（热门问题 / 使用指南）。动效仅限空态。

## 6. 主题与暗色适配

| 层 | 实现 |
|---|---|
| antd 令牌 | `theme/tokens.ts` 的 `buildTheme(mode)`：`darkAlgorithm` / `defaultAlgorithm` 两套语义令牌 |
| CSS 变量 | `index.css` 中 `:root[data-theme='dark']` 与 `:root[data-theme='light']` 两套（`--cockpit-*` / `--text-*` / `--border` / `--panel` / `--code-bg` / `--aurora-grid`） |
| 状态 | `stores/theme.ts`（localStorage + `<html data-theme>`），入口在侧栏底部与配置中心 |
| x-markdown | 官方 `themes/dark.css` / `themes/light.css` 以 class 作用域，切换时同步 `<html>` 上的 `x-markdown-dark/light` |
| 图表 | `ChartView.tsx` 按模式注入轴标签/图例/分隔线配色 |
| 语言包 | `locale/index.ts` 合并 antd 与 Ant Design X 官方 zh_CN，注入 `ConfigProvider` 与 `XProvider` |

暗色为默认，亮色为可切换增强；所有颜色一律走 CSS 变量或 antd 令牌，禁止组件内硬编码色值。

## 7. 与官方不同的业务扩展（有意为之）

1. **无顶栏**：模式 / 模型 / 联网开关统一放在 `Sender.Header`，与官方「输入区承载上下文」一致。
2. **步骤链替代 header 状态条**：官方在气泡 header 用 `ThoughtChain.Item` 显示模型状态，本项目用步骤链表达更细粒度的节点进度。
3. **反馈仅本地**：`Actions.Feedback` 的结果保存在 `stores/chat.ts` 的 `feedbacks`，后端暂无上报端点，UI 已标注；如需上报需先补后端接口。
4. **审批在对话内**：审批卡（`ApprovalCard`）渲染在消息流中，SSE 在断点挂起，审批后同一条流续跑。

## 8. 修改 UI 时的检查清单

- [ ] 是否复用了 antd / Ant Design X 现成组件，而非自绘按钮或输入框
- [ ] 新颜色是否走 CSS 变量 / antd 令牌（明暗两套都要成立）
- [ ] 是否影响步骤链折叠语义与并行 `step_id` 分槽
- [ ] 流式态（`streaming` / `ant-bubble-content-updating`）是否仍然正确
- [ ] 窄屏（<1024px）侧栏折叠后是否仍可用
- [ ] `npx tsc -b`、`npx vitest run`、`npm run build` 通过