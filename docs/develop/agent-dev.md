# Agent 开发指南

本文档面向需要新增或修改 Agent（智能体）的后端开发者，涵盖 Agent 注册、Graph 节点集成、SSE 事件发送等核心内容。

---

## Agent 体系回顾

DataAgent Pro 采用 Plan-and-Execute + ReAct 架构，包含 8 个 Agent，通过 13 个 LangGraph 节点协作：

```
clarify_plan → schema_agent → sql_coder → security → execute_sql → quality_gate → analyst → reporter/answer → finish
(+ rag_agent, misc_agent, chart_direct 按 intent 条件路由)
```

每个 Agent 在 LangGraph 中对应一个**节点函数**，通过全局 `AgentState` 共享上下文。节点开始时通过 `_push_node_started` 实时推送进度到前端。

---

## Agent 节点函数规范

所有 Agent 节点函数遵循统一签名：

```python
# backend/app/agents/_base.py

from typing import Any
from app.graph.state import AgentState

class BaseAgent:
    """Agent 基类"""

    def __init__(self, llm, config):
        self.llm = llm        # LLM 客户端
        self.config = config  # 应用配置

    async def run(self, state: AgentState) -> dict:
        """
        核心执行方法。

        参数:
            state: 全局工作流状态

        返回:
            dict: 需要更新的状态字段（LangGraph 会自动合并到全局 State）
        """
        raise NotImplementedError("子类必须实现 run 方法")
```

### 节点包装函数

LangGraph 的 `add_node` 期望一个接收 `state` 并返回部分状态更新的函数：

```python
# backend/app/graph/workflow.py

async def orchestrator_node(state: AgentState) -> dict:
    """编排节点 — LangGraph 节点包装函数"""
    agent = OrchestratorAgent(llm=get_llm_client(), config=get_app_config())
    return await agent.run(state)
```

---

## 新增一个 Worker Agent

以下以新增一个 **Data Quality Agent（数据质量检查 Agent）** 为例，演示完整的 Agent 开发流程。

### 第一步：创建 Agent 文件

```python
# backend/app/agents/data_quality.py

from app.graph.state import AgentState
from app.agents._base import BaseAgent

class DataQualityAgent(BaseAgent):
    """数据质量检查 Agent

    职责：
    1. 检查查询结果的数据完整性
    2. 检测缺失值、异常值、重复行
    3. 生成数据质量报告
    """

    async def run(self, state: AgentState) -> dict:
        query_result = state.get("query_result")

        if not query_result:
            return {
                "quality_report": "无查询结果，跳过数据质量检查"
            }

        # 检查数据质量
        report = await self._analyze_quality(query_result)

        return {
            "quality_report": report
        }

    async def _analyze_quality(self, rows: list) -> str:
        """分析数据质量"""
        total_rows = len(rows)

        if total_rows == 0:
            return "查询结果为空"

        # 统计缺失值
        null_counts = {}
        for row in rows:
            for col, val in row.items():
                if val is None or val == "":
                    null_counts[col] = null_counts.get(col, 0) + 1

        # 生成质量报告
        report_parts = [f"总行数: {total_rows}"]

        if null_counts:
            report_parts.append("\n缺失值统计:")
            for col, count in null_counts.items():
                pct = count / total_rows * 100
                report_parts.append(f"  {col}: {count} 行缺失 ({pct:.1f}%)")
        else:
            report_parts.append("无缺失值，数据完整性良好")

        return "\n".join(report_parts)
```

### 第二步：注册到 Graph

在 `backend/app/graph/workflow.py` 中注册新节点：

```python
from app.agents.data_quality import DataQualityAgent

# 定义节点函数
async def data_quality_node(state: AgentState) -> dict:
    agent = DataQualityAgent(llm=get_llm_client(), config=get_app_config())
    return await agent.run(state)

# 构建 Graph 时添加节点
builder = StateGraph(AgentState)

# ... 注册其他节点 ...

# 新增数据质量检查节点
builder.add_node("data_quality", data_quality_node)

# 调整边：analyst_node 之后 → data_quality → reporter_node
builder.add_edge("analyst_node", "data_quality")
builder.add_edge("data_quality", "reporter_node")
```

### 第三步：更新 AgentState

如果新 Agent 需要存储新的字段，需要在 `backend/app/graph/state.py` 中添加：

```python
class AgentState(MessagesState):
    # ... 已有字段 ...

    # 新增字段
    quality_report: Optional[str]  # 数据质量检查报告
```

### 第四步：添加 SSE 事件

如果新 Agent 的处理结果需要实时推送到前端，要在路由层发送新的 SSE 事件：

```python
# backend/app/api/v1/chat.py

# 在 SSE 事件处理器中新增事件类型
if state.get("quality_report"):
    yield {
        "event": "quality_report",
        "data": {
            "report": state["quality_report"]
        }
    }
```

前端 `useSSE.ts` 中也需要注册对应的事件监听：

```typescript
// frontend/src/composables/useSSE.ts

on('quality_report', (data) => {
  assistantMsg.qualityReport = data.report
})
```

---

## Agent 开发最佳实践

### 1. 单一职责

每个 Agent 只负责一项明确的业务任务。如果一个 Agent 的逻辑越来越复杂，应考虑拆分为多个子 Agent。

### 2. 错误处理

Agent 的异常不应导致整个工作流崩溃。使用状态字段传递错误信息，由 Orchestrator 决定如何处理：

```python
async def run(self, state: AgentState) -> dict:
    try:
        result = await self._do_work(state)
        return {"result": result, "error_message": None}
    except Exception as e:
        logger.error(f"[{self.__class__.__name__}] 执行失败: {e}")
        return {"error_message": str(e)}
```

### 3. 可观测性

关键步骤输出日志，便于调试和监控：

```python
import logging
logger = logging.getLogger(__name__)

async def run(self, state: AgentState) -> dict:
    logger.info(f"[{self.__class__.__name__}] 开始执行, query={state['user_query'][:50]}")
    # ... 执行逻辑 ...
    logger.info(f"[{self.__class__.__name__}] 执行完成, 耗时={elapsed:.2f}s")
```

### 4. 避免副作用

Agent 函数应该是 **纯数据转换**：输入 State，输出 State 的部分更新。避免直接操作数据库、文件系统等外部资源（由专门的工具/服务层处理）。

### 5. LLM 调用优化

- **复用 LLM 客户端**：通过依赖注入共享同一个 LLM 客户端实例
- **控制 Token 消耗**：传给 LLM 的 Schema 信息应精简，只包含相关表和字段
- **设置超时**：LLM 调用设置合理的超时（建议 30s），避免长时间阻塞

---

## AgentState 字段速查

| 字段 | 类型 | 读写节点 | 说明 |
|------|------|---------|------|
| `user_query` | str | 全部（只读） | 用户原始问题 |
| `intent` | str | Orchestrator | 意图分类 |
| `rag_context` | str | RAG Agent | 检索到的知识 |
| `table_schemas` | str | Schema Agent | 表结构 DDL |
| `generated_sql` | str | SQL Coder | 生成的 SQL |
| `sql_risk_level` | str | Security Agent | 风险等级 |
| `query_result` | list | Execute Node | 查询结果 |
| `analysis_insights` | str | Analyst Agent | 分析洞察 |
| `chart_config` | dict | Reporter Agent | ECharts 配置 |
| `approval_required` | bool | Security Agent | 是否需要审批 |
| `error_message` | str | 任意节点 | 错误信息 |

---

## 测试 Agent

```python
# backend/tests/test_agents/test_data_quality.py

import pytest
from app.agents.data_quality import DataQualityAgent
from app.graph.state import AgentState

@pytest.mark.asyncio
async def test_data_quality_with_null_values():
    agent = DataQualityAgent(llm=None, config={})

    state = AgentState(
        user_query="测试查询",
        query_result=[
            {"name": "张三", "phone": "13800138000"},
            {"name": "李四", "phone": None},       # 缺失值
            {"name": "", "phone": "13900139000"},  # 空名称
        ]
    )

    result = await agent.run(state)

    assert "quality_report" in result
    assert "缺失值" in result["quality_report"]
    assert "phone: 1 行缺失" in result["quality_report"]
```

```bash
# 运行测试
cd backend
uv run pytest tests/test_agents/test_data_quality.py -v
```

---

## 开发检查清单

新增 Agent 时，请确认以下事项：

- [ ] 创建 `backend/app/agents/<agent_name>.py`，实现 `BaseAgent` 子类
- [ ] 在 `backend/app/graph/workflow.py` 中添加节点函数和 Graph 节点
- [ ] 调整 Graph 的条件边/普通边，将新节点放入合理的执行位置
- [ ] 如需新增状态字段，更新 `backend/app/graph/state.py` 的 `AgentState`
- [ ] 如需向前端发送事件，在 `backend/app/api/v1/chat.py` 中添加 SSE 事件
- [ ] 在前端 `useSSE.ts` 中注册事件监听
- [ ] 编写单元测试，验证 Agent 的正常流程和异常流程
- [ ] 关键步骤添加日志，便于调试
