# Phase 7: Multi-mode Workflow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将现有单模式 LangGraph 工作流重构为 4 模式（data/report/doc/task），前端新增模式切换栏 + 联网搜索开关。

**Architecture:** 后端 ModeRouter 根据 `mode` 字段动态加载 StateGraph；前端 Chat.vue 新增模式 TabBar + 全局搜索 Toggle；API 入口 `ChatRequest` 新增 `mode` 和 `web_search` 字段。

**Tech Stack:** Python 3.11+ / FastAPI / LangGraph / Vue 3 / Pinia / Element Plus

---

### Task 1: Backend — ChatRequest 新增 mode + web_search 字段

**Files:**
- Modify: `backend/app/api/v1/chat.py:47-61`

**Step 1: 扩展 ChatRequest 模型**

```python
# backend/app/api/v1/chat.py
class ChatRequest(BaseModel):
    """聊天请求体"""
    messages: list[ChatMessage] = Field(default_factory=list)
    stream: bool = Field(default=True)
    thread_id: str | None = Field(default=None)
    mode: str = Field(              # ← 新增
        default="data",
        description="工作模式: data | report | doc | task",
        pattern="^(data|report|doc|task)$",
    )
    web_search: bool = Field(        # ← 新增
        default=False,
        description="是否启用联网搜索",
    )
```

**Step 2: 测试 curl 请求验证**

```bash
curl -X POST http://localhost:8000/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"测试"}], "mode":"report", "web_search":true, "stream":true}'
```

---

### Task 2: Backend — ModeRouter 模块

**Files:**
- Create: `backend/app/graph/mode_router.py`
- Modify: `backend/app/__init__.py` (if needed)

**Step 1: 创建 ModeRouter**

```python
# backend/app/graph/mode_router.py
"""
ModeRouter — 根据 mode 参数动态加载对应的 LangGraph StateGraph。

支持 4 种模式:
  - data: 数据分析（现有 13 节点工作流）
  - report: 研究报告（RAG 检索 + LLM 报告生成）
  - doc: 文档智读（文档上传 + 向量化 + RAG 问答）
  - task: 通用任务（deepagents 通用 Agent，阶段 10 实现）
"""
from typing import Callable
from langgraph.graph import StateGraph
from app.graph.state import AgentState
from app.utils.log_utils import log


MODE_REGISTRY: dict[str, Callable[[], StateGraph]] = {}


def register_mode(name: str):
    """装饰器：注册工作流模式"""
    def decorator(fn: Callable[[], StateGraph]):
        MODE_REGISTRY[name] = fn
        return fn
    return decorator


def get_graph(mode: str = "data") -> StateGraph:
    """根据 mode 获取编译后的 StateGraph，默认 data 模式向后兼容"""
    builder_fn = MODE_REGISTRY.get(mode)
    if builder_fn is None:
        log.warning(f"[ModeRouter] 未找到 mode='{mode}'，回退到 'data'")
        builder_fn = MODE_REGISTRY["data"]
    from app.graph.checkpointer import get_checkpointer
    return builder_fn().compile(checkpointer=get_checkpointer())
```

**Step 2: 在 workflow.py 中注册 data 模式**

```python
# backend/app/graph/workflow.py 末尾添加:
from app.graph.mode_router import register_mode

@register_mode("data")
def get_data_workflow() -> StateGraph:
    """数据分析模式（现有 13 节点）"""
    return _build_graph()  # 将现有 build_graph 内部逻辑提取为 _build_graph()
```

**Step 3: 验证** 

```bash
python -c "from app.graph.mode_router import get_graph; g = get_graph('data'); print('data mode OK:', g is not None)"
python -c "from app.graph.mode_router import get_graph; g = get_graph('unknown'); print('fallback OK:', g is not None)"
```

---

### Task 3: Backend — workflow.py 解耦（提取 _build_graph）

**Files:**
- Modify: `backend/app/graph/workflow.py`

**Step 1: 将 build_graph 内部逻辑提取为 `_build_graph`**

```python
# 当前 build_graph() 内容重命名为 _build_graph()
def _build_graph() -> StateGraph:
    # ... 现有 13 节点注册 + 边定义 ...

def build_graph() -> StateGraph:
    """向后兼容：编译并返回 data 模式工作流"""
    return _build_graph().compile(checkpointer=get_checkpointer())

@register_mode("data")
def get_data_workflow() -> StateGraph:
    return _build_graph()
```

**Step 2: 验证现有测试不变**

```bash
python -c "from app.graph.workflow import build_graph; g = build_graph(); print('backward compat OK')"
```

---

### Task 4: Backend — 研究报告模式（report workflow）

**Files:**
- Create: `backend/app/graph/report_workflow.py`

**Step 1: 创建 report 工作流**

```python
# backend/app/graph/report_workflow.py
"""研究报告模式：RAG 检索 → LLM 报告生成"""
from langgraph.graph import StateGraph, START, END
from app.graph.state import AgentState
from app.graph.mode_router import register_mode
from app.agents.orchestrator import clarify_and_plan
from app.agents.rag_agent import generate_with_rag
from app.graph.workflow import _push_node_started


async def report_planner_node(state: AgentState) -> dict:
    await _push_node_started("report_planner")
    user_question = state.get("user_question", "")
    history = state.get("messages", [])
    result = await clarify_and_plan(user_question, history)
    return {
        "is_clear": result["is_clear"],
        "intent": "query_data",
        "plan_steps": [{"step": "generate_report", "agent": "rag_agent"}],
        "stage": "planned",
    }


async def report_writer_node(state: AgentState) -> dict:
    await _push_node_started("report_writer")
    user_question = state.get("user_question", "")
    result = await generate_with_rag(user_question)
    return {
        "analysis_text": str(result.get("content", result)),
        "stage": "report_done",
    }


@register_mode("report")
def get_report_workflow() -> StateGraph:
    builder = StateGraph(AgentState)
    builder.add_node("report_planner", report_planner_node)
    builder.add_node("report_writer", report_writer_node)
    builder.add_node("finish", finish_node)
    builder.set_entry_point("report_planner")
    builder.add_edge("report_planner", "report_writer")
    builder.add_edge("report_writer", "finish")
    builder.add_edge("finish", END)
    return builder
```

---

### Task 5: Backend — 文档智读模式（doc workflow）

**Files:**
- Create: `backend/app/graph/doc_workflow.py`

```python
# backend/app/graph/doc_workflow.py
"""文档智读模式：文档向量化 → RAG 问答"""
from langgraph.graph import StateGraph, START, END
from app.graph.state import AgentState
from app.graph.mode_router import register_mode
from app.graph.workflow import _push_node_started, finish_node

@register_mode("doc")
def get_doc_workflow() -> StateGraph:
    builder = StateGraph(AgentState)
    builder.add_node("doc_planner", doc_planner_node)
    builder.add_node("doc_qa", doc_qa_node)
    builder.add_node("finish", finish_node)
    builder.set_entry_point("doc_planner")
    builder.add_edge("doc_planner", "doc_qa")
    builder.add_edge("doc_qa", "finish")
    builder.add_edge("finish", END)
    return builder
```

---

### Task 6: Backend — API 入口集成 ModeRouter

**Files:**
- Modify: `backend/app/api/v1/chat.py`

**Step 1: 修改 `_stream_chat` 使用 ModeRouter**

找到 `graph = get_graph()` 调用的位置，改为：

```python
# 根据 mode 参数动态加载工作流
mode = body.get("mode", "data")
web_search = body.get("web_search", False)

from app.graph.mode_router import get_graph as get_graph_by_mode
graph = get_graph_by_mode(mode)
```

**Step 2: 将 web_search 注入 state**

```python
initial_state = {
    "user_question": user_question,
    "messages": messages,
    "enable_web_search": web_search,  # ← 注入到 state，Agent 可据此决定是否调用搜索工具
}
```

---

### Task 7: Frontend — 模式切换栏 (ModeBar)

**Files:**
- Create: `frontend/src/components/ModeBar.vue`

```vue
<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  modelValue: string        // 当前模式: data | report | doc | task
  webSearch: boolean         // 联网搜索开关
}>()
const emit = defineEmits<{
  'update:modelValue': [value: string]
  'update:webSearch': [value: boolean]
}>()

const modes = [
  { key: 'data', label: '数据分析', icon: '📊' },
  { key: 'report', label: '研究报告', icon: '📝' },
  { key: 'doc', label: '文档智读', icon: '📖' },
  { key: 'task', label: '通用任务', icon: '🤖', disabled: true },
]
</script>

<template>
  <div class="mode-bar">
    <div class="mode-tabs">
      <button
        v-for="m in modes" :key="m.key"
        class="mode-tab" :class="{ active: modelValue === m.key, disabled: m.disabled }"
        :disabled="m.disabled"
        @click="emit('update:modelValue', m.key)"
      >
        <span class="mode-icon">{{ m.icon }}</span>
        <span>{{ m.label }}</span>
      </button>
    </div>
    <div class="mode-actions">
      <button class="web-search-toggle" :class="{ active: webSearch }" @click="emit('update:webSearch', !webSearch)">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
        </svg>
        <span>联网搜索</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.mode-bar {
  display: flex; align-items: center; justify-content: space-between;
  padding: var(--space-2) var(--space-4);
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border); flex-shrink: 0;
}
.mode-tabs { display: flex; gap: 2px; }
.mode-tab {
  display: flex; align-items: center; gap: 4px;
  padding: 4px 10px; border-radius: var(--radius-full);
  font-size: 12px; color: var(--color-text-muted);
  background: transparent; border: none; cursor: pointer;
  transition: all .2s ease;
}
.mode-tab:hover { background: var(--color-surface-elevated); }
.mode-tab.active { background: rgba(99,102,241,.12); color: #818cf8; font-weight: 600; }
.mode-tab.disabled { opacity: .4; cursor: not-allowed; }
.mode-icon { font-size: 14px; line-height: 1; }

.web-search-toggle {
  display: flex; align-items: center; gap: 4px;
  padding: 4px 10px; border-radius: var(--radius-full);
  font-size: 12px; color: var(--color-text-muted);
  background: transparent; border: 1px solid var(--color-border);
  cursor: pointer; transition: all .2s ease;
}
.web-search-toggle.active {
  border-color: #22c55e; color: #22c55e;
  background: rgba(34,197,94,.08);
}
</style>
```

**Step 1: 集成到 Chat.vue**

在 `chat-main` 顶部、`chat-toolbar` 下方插入:

```vue
<ModeBar v-model="currentMode" v-model:webSearch="webSearchEnabled" />
```

**Step 2: Chat.vue script 新增状态**

```ts
const currentMode = ref('data')
const webSearchEnabled = ref(false)
```

**Step 3: 发送消息时传递 mode + webSearch**

在 `sendMessage` 的 SSE 请求体中添加:
```ts
mode: currentMode.value,
web_search: webSearchEnabled.value,
```

---

### Task 8: Frontend — ChatInput 添加文件上传区域（doc 模式）

**Files:**
- Modify: `frontend/src/components/ChatInput.vue`
- Modify: `frontend/src/views/Chat.vue`

**Step 1: ChatInput 新增 props**

```ts
// ChatInput.vue
const props = defineProps<{
  loading: boolean
  showUpload: boolean  // ← 新增：doc 模式显示上传区域
}>()
```

**Step 2: 上传区域模板**（仅 `showUpload=true` 时渲染）

```vue
<div v-if="showUpload" class="upload-area">
  <input type="file" accept=".pdf,.docx,.md,.txt" @change="onFileSelect" />
  <span>支持 PDF / Word / Markdown / 纯文本</span>
</div>
```

**Step 3: 在 Chat.vue 中根据 currentMode 传递 showUpload**

```vue
<ChatInput :loading="store.isLoading" :showUpload="currentMode === 'doc'" @send="handleSend" @cancel="handleCancel" />
```

---

### Task 9: Backend — task 模式占位（stub）

**Files:**
- Create: `backend/app/graph/task_workflow.py`

```python
# backend/app/graph/task_workflow.py
"""通用任务模式：阶段 10 deepagents 实现，当前为占位"""
from langgraph.graph import StateGraph, START, END
from app.graph.state import AgentState
from app.graph.mode_router import register_mode
from app.graph.workflow import _push_node_started, finish_node


async def task_placeholder_node(state: AgentState) -> dict:
    await _push_node_started("task_placeholder")
    return {
        "analysis_text": "通用任务模式将在 V2.0 阶段 10（deepagents）中实现，敬请期待。",
        "stage": "task_done",
    }


@register_mode("task")
def get_task_workflow() -> StateGraph:
    builder = StateGraph(AgentState)
    builder.add_node("task_placeholder", task_placeholder_node)
    builder.add_node("finish", finish_node)
    builder.set_entry_point("task_placeholder")
    builder.add_edge("task_placeholder", "finish")
    builder.add_edge("finish", END)
    return builder
```

---

### Task 10: Integration — 端到端验证

**Step 1: 启动后端，发送 data 模式请求（向后兼容）**

```bash
curl -X POST http://localhost:8000/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"查询a_sheet1记录数"}], "mode":"data", "stream":true}'
```

**Step 2: 发送 report 模式请求**

```bash
curl -X POST http://localhost:8000/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"写一份数据安全分析报告"}], "mode":"report", "stream":true, "web_search":true}'
```

**Step 3: 发送 doc 模式请求**

```bash
curl -X POST http://localhost:8000/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"总结这份文档"}], "mode":"doc", "stream":true}'
```

**Step 4: 前端 Chrome DevTools 验证**

- 确认 4 模式切换栏渲染正确
- 确认联网搜索 toggle 开关正常
- 确认 data 模式向后兼容
- 确认 web_search=true 时 SSE 请求携带正确字段

---

### File Change Summary

| Action | File |
|--------|------|
| Modify | `backend/app/api/v1/chat.py` — ChatRequest + mode/web_search + ModeRouter 集成 |
| Modify | `backend/app/graph/workflow.py` — 提取 _build_graph + register_mode("data") |
| Create | `backend/app/graph/mode_router.py` — 模式注册表 + get_graph() |
| Create | `backend/app/graph/report_workflow.py` — 研究报告模式 |
| Create | `backend/app/graph/doc_workflow.py` — 文档智读模式 |
| Create | `backend/app/graph/task_workflow.py` — 通用任务占位 |
| Create | `frontend/src/components/ModeBar.vue` — 模式切换栏 |
| Modify | `frontend/src/views/Chat.vue` — 集成 ModeBar + mode/webSearch 状态 |
| Modify | `frontend/src/components/ChatInput.vue` — 文件上传区域 |
| Modify | `frontend/src/stores/chat.ts` — SSE 请求携带 mode + web_search |

**Total: 7 new files, 4 modified files**
