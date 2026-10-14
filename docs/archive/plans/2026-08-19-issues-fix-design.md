# 三问题 + 两遗留修复设计（2026-08-19）

对照基准：DeepSeek Harness（127.0.0.1:3080）实测界面逻辑与交互。

## 问题 1：14 天前历史会话无法加载

### 根因
- `session_events`（事件溯源）Phase1（8/17）才启用，14 天前会话无事件记录（实测 `session_events=0`）。
- Redis checkpoint TTL 仅 7 天（`CKPT_TTL = 86400*7`），14 天前会话快照已过期。
- `get_session_messages` 两者皆空 → `messages=[]` → 前端渲染空白。

### 修复
`get_session_messages` 末尾：当事件日志与 Redis 都无消息时，从 `chat_nodes` 的 `question` 构建最低限度消息：
```python
if not all_messages and nodes:
    all_messages = [
        {"role": "user", "type": "text", "content": n["question"]}
        for n in nodes if n.get("question")
    ]
```

## 问题 2：工具调用渲染混乱，未对齐 Harness

### 根因
- 前端 `tool_call`/`tool_result`/`tool_chain` 三种类型割裂渲染：`toolInfo` 返回 `调用: xxx`/`完成: xxx` 前缀。
- `onToolResult` 按「最近同名 tool_call」配对，多工具连续调用时最近同名可能非本调用 → 错配。
- Harness 渲染：每个工具一行紧凑折叠行（`Read docs\architecture.md`），点击展开详情。

### 修复（前端）
1. `toolInfo`：统一 label 为 `工具名 + 摘要`（无「调用:/完成:」前缀），icon 统一 `🔧`（tool_call）/`✅`（tool_result）/`🔗`（tool_chain）。
2. `onToolResult` 配对改为「最近**未合并**的 tool_call」：用 `type === 'tool_call'` 而非已升级的 `tool_chain`，并记录已配对集合避免错配。

## 问题 3：切换会话后工具调用输出不见

### 根因
- `_project()`（event_sourcing.py:241-242）不投影 `tool_chain`（过程态事件不投影）。
- DeepAgent 模式已记录 `TOOL_CHAIN` 事件（chat.py:957，payload 含 name/status/content），但投影被丢弃。
- SSE 实时推送的 `tool_call`/`tool_result` 在历史恢复时全部丢失。

### 修复（后端 `_project()`）
增加 `EventType.TOOL_CHAIN` 投影：
```python
if etype == EventType.TOOL_CHAIN:
    name = payload.get("name", "") or evt.content or "tool"
    result = payload.get("content", "") or evt.content or ""
    return {
        "role": "system",
        "type": "tool_chain",
        "toolName": name,
        "toolMeta": {"result": result[:500]},
        "collapsed": True,
    }
```
同时为 SQL/图表事件增强投影元数据（`sql` 字段保留完整 SQL、`chart` 保留 chartConfig），使历史会话 SQL/图表卡片可展开。

## 遗留 1：首轮问候耗时过长（misc_agent 多余轮询）

### 待查
- misc_agent 是「通用任务」兜底节点，首轮问候可能触发不必要的工具调用循环。
- 修复：misc_agent 节点对纯文本问候（无工具需求）直接走 `analysis_text` 路径，跳过工具调用。

## 遗留 2：新建/切换会话后输入框未自动聚焦

### 修复
`ChatInput.vue`：props 变化（`currentThreadId`/`isNewSession`）时 `nextTick(() => inputRef.value?.focus())`；或在 `Chat.vue` 切换会话后调用。
