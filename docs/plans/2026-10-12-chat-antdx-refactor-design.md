# 对话渲染层整体重构设计(ant-design-x-vue + vue-bits)

> 日期:2026-10-12
> 状态:设计已确认(对话中逐项确认:ThoughtChain 折叠语义、思考模式语义、provider 参数覆盖策略)
> 关联:思考模式/全模态配置设计(同日会话)、Harness 落地差距分析

## 1. 背景与目标

现有 Chat.vue(1800+ 行)的自研消息渲染被判定"达不到可用状态"。本次重构:

- **渲染层整体替换**为 ant-design-x-vue(官方 AI 对话组件库,Vue ≥3.5);
- **数据层(SSE 管线/取消/排队/多轮上下文)允许按官方文档要求调整**——以官方模式为准做适配;
- vue-bits 仅作动效点缀(其定位是动效库,无 AI 聊天组件——已核实);
- 美学方向(frontend-design):**碳黑驾驶舱 + 紫磷光**——大面积碳黑层次,品牌紫 #7056f8 为唯一强调色,技术感等宽字体用于数据读数,拒绝通用 AI 观感。

## 2. 架构映射

| 现有自研实现 | 重构后 | 说明 |
|---|---|---|
| 手写 14 类消息模板 | Bubble.List + #message 插槽 → `MessageRenderer.vue` | 按 ChatMessage.type 分发 |
| 手写步骤分组头 | **ThoughtChain**(step→item,title/status/content) | 完成后自动折叠、运行中展开(已确认) |
| ChatInput 自研输入框 | **Sender**(loading/cancel/submitType)+ header 插槽(模式/联网/模型 chips) | P3 预留 Attachments 图片输入 |
| 静态空态 | **Welcome + Prompts** + vue-bits(Text Type / Aurora) | 空态氛围 |
| 滚动逻辑 | Bubble.List 内建自动滚动 + scrollTo | 保留发送到底语义 |
| 主题 | XProvider darkAlgorithm + 紫 token | 暗色统一 |

**数据层调整边界**(按官方模式适配,不推翻语义):
- `useSSE` 的手工 buffer 切分行解析 → **XStream** 替换(R2),事件 dispatch 逻辑保留;
- `useXChat` 不采用——其消息模型无法承载 step_id/channel/工具卡片等扩展事件,store 仍是唯一状态源;
- 取消(/cancel + AbortController)、排队、多轮 thread_id 复用语义不变。

## 3. 组件与文件规划

| 文件 | 动作 |
|---|---|
| `components/chat/MessageRenderer.vue` | 新建:按 ChatMessage.type 分发 14 类渲染(从 Chat.vue 平移) |
| `components/chat/StepThoughtChain.vue` | 新建:steps + 分组消息 → ThoughtChain items(折叠语义:运行中展开,完成自动折叠) |
| `views/Chat.vue` | 消息区 + 输入区替换为 antdx;保留 sidebar/statbar/轨迹面板 |
| `components/ChatInput.vue` | 输入内核换 Sender,chips 迁移 |
| `composables/useSSE.ts` | R2:XStream 替换行解析 |
| 空态 | `XWelcome`/`Prompts` + vue-bits 点缀 |

## 4. 关键语义(全部已确认)

- **ThoughtChain 折叠**:运行中展开,完成后自动折叠(对齐现有任务清单 2s 自动折叠习惯);用户手动展开优先于自动行为;
- **思考模式**:provider.thinking_mode 开启→渲染 ReasoningBlock;关闭→仅隐藏不丢弃(切回可见);后端全 Agent 推送 reasoning,字段兼容 `reasoning_content`/`reasoning`(OpenRouter);
- **配置参数**:provider `capabilities`(tools/image_input/thinking)+ `params`(temperature/top_p/max_tokens/penalties/**reasoning_effort** low|medium|high);agent 语义覆盖 provider 基准;思考强度按 api_base 域名映射(OpenAI 原生/OpenRouter/DashScope/vLLM);
- **配置界面**:列表页删除统计卡;弹窗加高级配置复选框组(工具调用/图片输入/思考模式+思考强度),对齐 WorkBuddy。

## 5. 阶段与验收

| 阶段 | 内容 | 验收 |
|---|---|---|
| R1 | 依赖恢复 + MessageRenderer 抽取 + Bubble.List/ThoughtChain 接入 | 历史会话/新对话渲染等价,build 通过 |
| R2 | Sender 输入区 + useSSE→XStream + 流式光标/滚动回归 | 简单对话+查询对话全链路 |
| R3 | 空态 + vue-bits 动效 + 视觉打磨(frontend-design 方向) | 观感验收 |
| R4 | 配置层:P1 Schema/capabilities/思考强度/去统计卡 + P2 Agent 调用点接入 | 配置闭环 + pytest/build |

## 6. 风险与对策

- Bubble.List 高频流式更新:items 用 computed 缓存,同一 message 就地变更避免重挂载;必要时步骤折叠降低渲染量;
- ThoughtChain 嵌套流式 Markdown:折叠态不渲染 content;
- antdv 暗色 token 与 design-system.css 共存:scoped 隔离,颜色统一走 CSS 变量;
- 回滚:R1 起每阶段独立 commit,Chat.vue 旧模板留存于 git 历史。
