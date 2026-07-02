# Phase E: 全面重构设计方案 (✅ 已完成)

> 日期: 2026-06-24  
> 状态: ✅ 已全部实施 (E.1~E.6)，2026-06-24 ~ 2026-06-30  
> 涵盖: 认证隔离 / 会话持久化 / 工作流重设计 / 标题生成 / 历史恢复 / UI 重设计
>
> **这是历史设计文档。当前实际架构请参考 [工作流详解](./guide/workflow.md) 和 [架构设计](./guide/architecture.md)。**

---

## 一、问题总览

| # | 问题 | 根因 | 优先级 |
|---|------|------|--------|
| 1 | 点击历史记录无法回到历史消息 | 缺少 `GET /sessions/{id}` API + 前端未实现消息恢复逻辑 | P0 |
| 2 | 历史会话无标题 | 无标题生成机制，侧边栏仅显示 thread_id 前缀 | P0 |
| 3 | 会话未做用户隔离 | 无登录体系，thread_id 是随机 UUID，所有用户共享 | P0 |
| 4 | 历史会话无法删除 | PlainRedisSaver 不支持 adelete，返回伪成功 | P1 |
| 5 | 工作流异常（意图识别错误 + 无效节点级联） | Orchestrator 直接分类执行，无确认 + 无短路机制 + Analyst 不控制图表生成入口 | P0 |
| 6 | 前端 UI 布局与交互不合理 | 侧边栏为浮层、非持久；无节点导航；空状态缺少引导 | P1 |

---

## 二、技术架构总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Frontend (Vue 3 + TS)                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────────────┐  │
│  │ Login    │  │ Chat     │  │ Approval │  │ Stores: auth, chat │  │
│  │ (JWT)    │  │ (SSE)    │  │          │  │ Router: guards     │  │
│  └──────────┘  └──────────┘  └──────────┘  └────────────────────┘  │
├─────────────────────────────────────────────────────────────────────┤
│                         Backend (FastAPI + LangGraph)                │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────────────────┐  │
│  │ Auth API │  │ Chat API │  │ Agents (Planner → Schema → SQL   │  │
│  │ JWT      │  │ SSE      │  │   → Security → Execute → Analyst │  │
│  │ middleware│  │ Sessions │  │   → Reporter)                   │  │
│  └──────────┘  └──────────┘  └──────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────┤
│                         Storage Layer                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────────────────┐  │
│  │ MySQL    │  │ Redis    │  │ Milvus                           │  │
│  │ sys_user │  │ LangGraph│  │ RAG vectors                      │  │
│  │ chat_    │  │ checkpts │  │                                  │  │
│  │ sessions │  │          │  │                                  │  │
│  │ chat_nodes│ │          │  │                                  │  │
│  └──────────┘  └──────────┘  └──────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 三、模块 1：认证与用户隔离

### 3.1 当前问题

- 前端无登录页，任何人可直接访问对话页
- `thread_id = str(uuid.uuid4())` — 随机生成，无用户维度
- 所有用户共享同一会话空间，无法区分归属

### 3.2 设计

#### 用户表（复用现有 `sys_user`）

```sql
-- 现有表结构，无需修改
-- 关键字段: user_name (登录账号), password (密码), user_type (角色), nick_name (昵称), status (状态)
```

#### 认证流程

```
用户输入 user_name + password
  │
  ▼
POST /api/v1/auth/login
  │
  ├─ 查 sys_user WHERE user_name = ? AND status = '0' AND del_flag = '0'
  ├─ 验证 password (bcrypt/plaintext 比对)
  ├─ 更新 login_ip + login_date
  ├─ 生成 JWT: {user_name, user_type, nick_name, exp}
  └─ 返回: {access_token, user_name, nick_name, user_type}
```

#### thread_id 格式

```
{user_name}:{uuid}

示例:
  zhangsan:a1b2c3d4-e5f6-7890-abcd-ef1234567890
  lisi:     f9e8d7c6-b5a4-3210-fedc-ba0987654321
```

SSE 流中的 config 构造：
```python
thread_id = f"{user_name}:{str(uuid.uuid4())}"
config = {"configurable": {"thread_id": thread_id}}
```

#### 权限控制矩阵

| 操作 | 普通用户 (user_type≠'00') | Admin (user_type='00') |
|------|--------------------------|------------------------|
| 查看自己的会话列表 | ✅ | ✅ |
| 查看所有用户的会话 | ❌ | ✅ (`?all=true`) |
| 加载自己的历史消息 | ✅ | ✅ |
| 加载他人的历史消息 | ❌ | ✅ |
| 删除自己的会话 | ✅ | ✅ |
| 删除他人的会话 | ❌ | ✅ |

#### JWT 中间件

```python
# backend/app/api/deps.py 新增
from fastapi import Request, HTTPException, Depends
import jwt

async def get_current_user(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录")
    token = auth.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        return {"user_name": payload["user_name"], "user_type": payload.get("user_type", ""),
                "nick_name": payload.get("nick_name", "")}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="令牌已过期")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效令牌")
```

#### 前端改造

| 文件 | 改动 |
|------|------|
| `src/views/Login.vue` | **新建**：用户名/密码登录表单 |
| `src/stores/auth.ts` | **新建**：token 管理 + login/logout/getUser |
| `src/router/index.ts` | 新增 `/login` 路由 + 全局前置守卫 |
| `src/api/client.ts` | Axios 拦截器：自动附加 Authorization header，401→跳转登录 |
| `src/views/Chat.vue` | Header 显示用户信息 + 退出按钮 |

---

## 四、模块 2：数据库会话存储

### 4.1 当前问题

- `PlainRedisSaver` 不支持 `adelete()`，删除返回伪成功
- 会话元数据（标题、创建时间、归属用户）无结构化存储
- 无法按用户过滤会话列表

### 4.2 设计：双写策略

```
┌─────────────────┐     ┌──────────────────────────┐
│ Redis           │     │ MySQL                    │
│                 │     │                          │
│ LangGraph       │     │ chat_sessions            │
│ checkpoints     │     │  - thread_id (PK/UNIQUE) │
│ (工作流状态恢复)  │     │  - user_name             │
│                 │     │  - title (LLM生成)        │
│                 │     │  - created_at / updated_at│
│                 │     │                          │
│                 │     │ chat_nodes               │
│                 │     │  - thread_id + node_index │
│                 │     │  - title (节点标题)        │
│                 │     │  - question (前200字)     │
└─────────────────┘     └──────────────────────────┘
```

#### 新增表 DDL

```sql
-- 会话元数据表
CREATE TABLE chat_sessions (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    thread_id   VARCHAR(128) NOT NULL UNIQUE COMMENT '{user_name}:{uuid}',
    user_name   VARCHAR(30) NOT NULL COMMENT '归属用户',
    title       VARCHAR(200) DEFAULT '' COMMENT 'LLM生成的会话标题',
    created_at  DATETIME DEFAULT NOW(),
    updated_at  DATETIME DEFAULT NOW() ON UPDATE NOW(),
    INDEX idx_user_name (user_name),
    INDEX idx_created (created_at)
) COMMENT 'Agent对话会话元数据';

-- 节点标题表（每轮问答一条）
CREATE TABLE chat_nodes (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    thread_id   VARCHAR(128) NOT NULL,
    node_index  INT NOT NULL COMMENT '第几轮问答(从0开始)',
    title       VARCHAR(200) NOT NULL COMMENT 'LLM生成的节点标题',
    question    TEXT COMMENT '用户提问原文(前200字)',
    created_at  DATETIME DEFAULT NOW(),
    INDEX idx_thread (thread_id),
    UNIQUE KEY uk_thread_node (thread_id, node_index)
) COMMENT 'Agent对话节点标题';
```

#### 运营动作——清理 Redis

Redis 已累积约 29 个历史会话 checkpoints（无用户标识的随机 UUID）。迁移方案：

1. 迁移脚本扫描 Redis keys `checkpoints:*`，将已有 thread_id 插入 `chat_sessions`（user_name 标记为 `legacy`）
2. 对于 `legacy` 会话，Admin 可见并可删除
3. 不能恢复归属的会话标记 `legacy` 可见不可恢复

### 4.3 API 变更

| 方法 | 路径 | 变更说明 |
|------|------|---------|
| `POST` | `/api/v1/auth/login` | **新增**：JWT 登录 |
| `GET` | `/api/v1/auth/me` | **新增**：获取当前用户信息 |
| `POST` | `/api/v1/chat/completions` | 修改：注入 user_name → thread_id 格式化；流结束后异步保存会话 + 节点标题 |
| `GET` | `/api/v1/chat/sessions` | 修改：从 MySQL 查询，按 user_name 过滤（admin 可 `?all=true`） |
| `GET` | `/api/v1/chat/sessions/{thread_id}` | **新增**：从 Redis checkpoints 恢复消息历史 + 返回节点标题列表 |
| `DELETE` | `/api/v1/chat/sessions/{thread_id}` | 修改：校验 user_name 权限 → MySQL 删除 + Redis checkpoints 清理 |
| `PATCH` | `/api/v1/chat/sessions/{thread_id}` | **新增**：更新会话标题（手动编辑） |

---

## 五、模块 3：工作流重设计（Plan-and-Execute）

### 5.1 当前问题

"我当前有哪些数据" → orchestrator 分类 `query_data` → schema → sql_coder → 无法生成有效 SQL → 最终 "无法回答此问题" → **但仍继续走到 analyst → reporter → chart**

核心缺陷：
- 意图分类过于武断，不追问用户模糊意图
- 缺少节点间有效性门控（失败不短路）
- Analyst 不控制是否进入 Reporter（结果为空也进图表）

### 5.2 新架构：Plan → Validate → Execute

参考 [Superpowers](https://github.com/obra/superpowers) 工作范式：**用结构化提问消除需求歧义，分块设计确认后再执行**。

```
用户提问
   │
   ▼
┌──────────────────────────────────────────────┐
│  Step 1: Clarifier (意图澄清)                  │
│  LLM 分析模糊度，若模糊 → 追问                  │
│  输出: {is_clear, intent, plan, clarification} │
└──────────────┬───────────────────────────────┘
               │
        ┌──────┼──────┐
        ▼             ▼
      清晰          模糊/歧义
        │             │
        │             ▼
        │      ┌──────────────┐
        │      │ 追问用户      │  SSE: clarication 事件
        │      │ "您想查看表    │  前端显示追问卡片
        │      │  列表还是表    │  用户点击选项 → 重新进入 Clarifier
        │      │  数据统计？"   │
        │      └──────┬───────┘
        │             │ 用户回答后
        │             ▼
        │      回到 Clarifier (带新上下文)
        │
        ▼
┌──────────────────────────────────────────────┐
│  Step 2: Planner (生成执行计划)                │
│  输出: {intent, plan_steps[], chart_suitable}  │
└──────────────┬───────────────────────────────┘
               │
    ┌──────────┼──────────┬──────────────┐
    ▼          ▼          ▼              ▼
 query      chart      ask_help      other_q
 _data      _int                     → misc_agent → finish ✅
    │          │         → rag_agent
    │          │         → finish ✅
    ▼          │
schema_node    │
    │          │
    ├─失败─────→ finish (含友好提示) ❌
    │          │
    ▼          │
sql_coder     │
    │          │
    ├─失败─────→ rag_agent (知识库兜底) → finish ❌
    │          │
    ▼          │
security      │
    │          │
    ├─驳回─────→ finish ❌
    ├─审批─────→ Human-in-loop
    │          │
    ▼          │
execute_sql   │
    │          │
    ├─空结果───→ misc_agent → finish ❌ (不进入 analyst)
    │          │
    ▼          │
analyst       │
    │          │
    ├─ {chart_suitable: false} → answer (纯文本) → finish ✅
    ├─ {chart_suitable: true}  → reporter+chart → finish ✅
```

### 5.3 关键节点设计

#### Clarifier 判断规则

| 用户输入 | 模糊度 | 行为 |
|---------|--------|------|
| "我当前有哪些数据" | ⚠️ 高 | 追问 "您想查看数据库中有哪些**表**，还是查看某个具体表的**数据内容**？" |
| "帮我分析销售趋势" | ⚠️ 中 | 追问 "请指定时间范围（本月/本季度）和关注的指标（销售额/订单量）" |
| "查询a_sheet1表上个月销售额TOP10" | ✅ 低 | 直接生成计划: `[load_schema, gen_sql, execute, analyze, report+chart]` |
| "你好" / "你能做什么" | ✅ 低 | 直接路由到 misc_agent |

#### Clarifier 追问 SSE 事件

```json
{
  "type": "clarification",
  "content": "您想查看数据库中有哪些表，还是查看某个具体表的数据内容？",
  "options": ["查看表列表", "查看具体表数据", "查看数据统计概览"],
  "clarify_id": "clar_001"
}
```

#### Planner 输出结构

```json
{
  "intent": "query_data",
  "confidence": 0.92,
  "reasoning": "用户明确要求查询a_sheet1表的数据",
  "plan_steps": [
    {"step": "load_schema", "agent": "schema", "priority": 1},
    {"step": "generate_sql", "agent": "sql_coder", "priority": 2},
    {"step": "security_check", "agent": "security", "priority": 3},
    {"step": "execute_query", "agent": "execute", "priority": 4},
    {"step": "analyze_data", "agent": "analyst", "priority": 5}
  ],
  "chart_suitable": true,
  "expected_output": "带图表的销售数据分析报告"
}
```

#### 条件边短路规则（修改 workflow.py）

| 节点 | 条件 | 失败路由 |
|------|------|---------|
| schema_agent | `error_message` 非空 | → finish（含友好提示） |
| sql_coder | `error_message` 非空 | → rag_agent（知识库兜底） |
| security | `sql_category != "safe"` | → finish |
| execute_sql | `query_result` 为空 | → misc_agent（降级提示），**不走 analyst** |
| analyst | `chart_suitable == false` | → answer 节点（纯文本）→ finish |

### 5.4 文件改动

| 文件 | 改动说明 |
|------|---------|
| `backend/app/agents/orchestrator.py` | 改造为 Planner + Clarifier 双阶段，新增 `clarify_intent()` 函数 |
| `backend/app/agents/reporter.py` | analyst → reporter 间新增 `chart_suitable` 判断 |
| `backend/app/graph/workflow.py` | 新增 `planner_node` / `clarifier_node` / `answer_node`，重写条件边路由规则 |
| `backend/app/graph/state.py` | AgentState 新增 `chart_suitable`, `clarification_needed`, `plan_steps` 字段 |
| `backend/app/api/v1/chat.py` | SSE 事件新增 `clarification` 类型处理 |
| `frontend/src/composables/useSSE.ts` | 新增 `onClarification` 回调 |
| `frontend/src/views/Chat.vue` | 追问卡片组件 + 点击选项回传 |
| `frontend/src/stores/chat.ts` | 新增 `clarification` 消息类型 |

---

## 六、模块 4：节点标题生成

### 6.1 设计

每轮对话完成后（SSE `done` 事件之后），后端异步调用 LLM 生成节点标题：

```
SSE done 事件触发
   │
   ▼
┌──────────────────────────────────────────┐
│ TitleGenerator (异步 LLM 调用，不阻塞流)   │
│                                          │
│ Prompt:                                  │
│ "根据以下对话，生成一个15字以内的标题:       │
│  用户: 查询a_sheet1表上个月销售额           │
│  AI: [最终回答的前200字摘要]                │
│  标题:"                                  │
│                                          │
│ 输出: "上月销售数据查询"                    │
│                                          │
│ 降级: 生成失败 → "第N轮: {question[:20]}"  │
└──────────────────┬───────────────────────┘
                   ▼
   INSERT INTO chat_nodes (thread_id, node_index, title, question)
```

**标题编辑**：用户双击侧边栏标题 → inline 编辑 → `PATCH /sessions/{thread_id}`

### 6.2 文件改动

| 文件 | 改动说明 |
|------|---------|
| `backend/app/agents/title_generator.py` | **新建**：标题生成 Agent，包含 `generate_title()` 和 `generate_session_title()` |
| `backend/app/api/v1/chat.py` | SSE done 后异步调用 `generate_title()` 保存标题 |
| `backend/app/graph/workflow.py` | `finish_node` 中设置 `node_index` 计数器 |

---

## 七、模块 5：历史消息恢复

### 7.1 流程

```
用户点击侧边栏 "上月销售数据查询" (thread_id: zhangsan:abc123)
   │
   ▼
GET /api/v1/chat/sessions/zhangsan:abc123
   │
   ▼
后端:
  1. 查 chat_nodes WHERE thread_id = ? → 节点标题列表（侧边栏锚点）
  2. 通过 Redis checkpointer.get(config, thread_id) → LangGraph state
  3. 从 checkpoint state.messages 中提取 HumanMessage + AIMessage 等
  4. 每条消息标记 node_index（通过分隔标记推断属于第几轮）
  5. 组装 ChatMessage[] 返回
```

### 7.2 响应格式

```json
{
  "thread_id": "zhangsan:abc123",
  "title": "上月销售数据查询",
  "nodes": [
    {"index": 0, "title": "上月销售数据查询", "question": "查询a_sheet1表上个月销售额"},
    {"index": 1, "title": "本月订单统计", "question": "统计本月订单总数"}
  ],
  "messages": [
    {"role": "user", "content": "查询a_sheet1表上个月销售额", "nodeIndex": 0},
    {"role": "assistant", "type": "thinking", "agent": "planner", "nodeIndex": 0},
    {"role": "assistant", "type": "sql", "content": "SELECT ...", "nodeIndex": 0},
    {"role": "assistant", "type": "result", "columns": [...], "rows": [...], "nodeIndex": 0},
    {"role": "assistant", "type": "chart", "config": {...}, "nodeIndex": 0},
    {"role": "assistant", "type": "text", "content": "上个月销售额为...", "nodeIndex": 0},
    {"role": "user", "content": "统计本月订单总数", "nodeIndex": 1},
    ...
  ]
}
```

### 7.3 前端跳转

`nodeIndex` 标记每条消息归属哪一轮。前端渲染时：
- 在 `nodeIndex` 变化处插入节点分隔线 + 标题
- 侧边栏点击节点标题 → `scrollIntoView({ behavior: "smooth" })` 跳转到对应分隔线

### 7.4 文件改动

| 文件 | 改动说明 |
|------|---------|
| `backend/app/api/v1/chat.py` | 新增 `GET /sessions/{thread_id}` 端点 + `PATCH /sessions/{thread_id}` |
| `frontend/src/stores/chat.ts` | `loadSession()` action，从 API 加载完整消息历史 |
| `frontend/src/views/Chat.vue` | 侧边栏点击事件 → `loadSession()` → 渲染完整消息 + 节点分隔线 |

---

## 八、模块 6：前端 UI 重设计

### 8.1 设计参考

参考 [ChatGLM All Tools](https://chatglm.cn/) 的界面模式，结合当前深色科技风设计系统（`design-system.css`）。

### 8.2 设计系统（沿用并增强）

| 类别 | 值 |
|------|---|
| Primary | `#6366f1` (靛蓝) |
| Background | `#09090b` (深黑) |
| Surface | `#18181b` / `#27272a` |
| Text | `#fafafa` / `#a1a1aa` / `#71717a` |
| Font | Inter (正文) + JetBrains Mono (代码) |
| 圆角 | 8px 卡片 / 12px 按钮 / 24px 输入框 |

### 8.3 整体布局（三区式）

```
┌───────────┬────────────────────────────────────────────┐
│           │  Header Bar                                │
│  Sidebar  │  [nick_name ▼] [退出]                       │
│  280px    ├────────────────────────────────────────────┤
│           │                                            │
│ ┌───────┐ │  Messages Panel (flex: 1, overflow-y:auto) │
│ │+新建  │ │                                            │
│ │ 会话  │ │  ┌─ Node Separator ────────────────────┐   │
│ ├───────┤ │  │ 📌 "上月销售数据查询"                 │   │
│ │📝标题1│ │  └──────────────────────────────────────┘   │
│ │📝标题2│ │  [user bubble]                              │
│ │📝标题3│ │  [SQL card]                                 │
│ │       │ │  [result table]                             │
│ │ hover  │ │  [chart block]                             │
│ │ 显示   │ │  [assistant text]                          │
│ │编辑/   │ │  ┌─ Follow-up ──────────────────────────┐  │
│ │删除   │ │  │ [导出数据] [换个图表] [深入分析]       │  │
│ └───────┘ │  └──────────────────────────────────────┘  │
│           ├────────────────────────────────────────────┤
│ 可折叠    │  Input Area (sticky bottom)                 │
│           │  ┌────────────────────────────────── [发送]┐│
│           │  │ 用自然语言描述您的数据需求...            ││
│           │  └─────────────────────────────────────────┘│
└───────────┴────────────────────────────────────────────┘
```

### 8.4 各区块设计

#### 侧边栏

```
┌────────────────────┐
│ [+ 新建会话]        │  ← prominent, full-width 按钮
├────────────────────┤
│ 📝 上月销售数据查询  │  hover → 显示 [编辑] [删除] 按钮
│    3小时前          │  双击标题 → inline 编辑模式
│                    │
│ 📝 用户增长趋势分析  │  当前激活 → 高亮背景 + 左侧色条
│    昨天             │
│                    │
│ 📝 本月订单统计汇总  │
│    2天前            │
│                    │
└────────────────────┘
```

#### 空状态

```
┌─────────────────────────────────────────────┐
│                                             │
│         [大型插图/DataAgent Logo]            │
│                                             │
│        开始您的数据分析之旅                   │
│     用自然语言描述您的数据需求                 │
│                                             │
│  ┌ 快捷分析 ───────────────────────────────┐│
│  │ [查询销售额] [用户增长趋势] [库存分析]    ││
│  │ [区域对比]   [销售排行]     [更多...]    ││
│  └─────────────────────────────────────────┘│
│                                             │
└─────────────────────────────────────────────┘
```

#### 思考/执行卡片（行内展开）

```
┌─ Agent 执行中 ───────────────────────────┐
│ 💭 Planner    → 分析意图完成       ✓    │
│ 🔧 Schema     → 加载表结构完成     ✓    │
│ 🔧 SQL Coder  → 生成查询语句...    ◌    │  ← loading spinner
│ ⏳ Security   → 待执行                  │
│ ⏳ Execute    → 待执行                  │
│ ⏳ Reporter   → 待执行                  │
└─────────────────────────────────────────┘
```

#### Clarifier 追问卡片

```
┌─────────────────────────────────────────┐
│ 🤔 需要确认一下                          │
│                                         │
│ 您想查看数据库中有哪些表，还是              │
│ 查看某个具体表的数据内容？                 │
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │ [查看表列表]  [查看具体表数据]        │ │
│ │ [查看数据统计概览]                    │ │
│ └─────────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

点击选项 → 作为用户消息发送 → Planner 带上下文重新分析

#### 消息类型对应的 UI 组件

| SSE 类型 | 前端渲染 |
|---------|---------|
| `thinking` | Agent 行内执行卡片 (不占独立消息) |
| `clarification` | 追问选择卡片 |
| `sql` | 代码块 + 复制按钮 (暗色背景) |
| `result` | 数据表格 + CSV/Excel 导出按钮 |
| `chart` | ECharts 渲染图表 (360px 高度) |
| `token` / `text` | 流式打字机效果文本 |
| `error` | 错误横幅 + 重试按钮 |
| `approval_required` | 审批提示 (仅 admin) |
| `done` | 完成标记 + 触发异步标题生成 |

### 8.5 路由改造

| 路由 | 组件 | 鉴权 |
|------|------|------|
| `/login` | Login.vue | 公开 |
| `/chat` | Chat.vue | 需登录 |
| `/approval` | Approval.vue | Admin only |

### 8.6 前端文件总览

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/views/Login.vue` | **新建** | 登录页 |
| `src/views/Chat.vue` | **重写** | 三区式布局 + SSE 流式 + 节点导航 |
| `src/views/Home.vue` | 保留 | 首页（已重构） |
| `src/views/Approval.vue` | 保留 | 审批页（已重构） |
| `src/stores/auth.ts` | **新建** | 认证状态管理 |
| `src/stores/chat.ts` | **重写** | 会话 + 消息 + 标题管理 |
| `src/composables/useSSE.ts` | 修改 | 新增 `clarification` 事件处理 |
| `src/api/client.ts` | 修改 | JWT 拦截器 |
| `src/router/index.ts` | 修改 | 路由守卫 + Login 路由 |
| `src/components/ChatSidebar.vue` | **新建** | 侧边栏组件 |
| `src/components/ChatMessage.vue` | **新建** | 消息卡片组件（提取自 Chat.vue） |
| `src/components/ChatInput.vue` | **新建** | 输入区组件 |
| `src/components/ClarifierCard.vue` | **新建** | 追问卡片组件 |
| `src/components/ExecutionCard.vue` | **新建** | Agent 行内执行卡片 |
| `src/components/NodeSeparator.vue` | **新建** | 节点分隔线 + 跳转锚点 |
| `src/styles/design-system.css` | 保留 | 设计系统变量 |

---

## 九、执行顺序（共 6 个阶段）

```
Phase E.1: 认证与用户隔离（基础依赖）
├── 后端: auth API + JWT 中间件 + deps.py
├── 前端: Login.vue + auth.ts + 路由守卫 + Axios 拦截器
└── 验收: 登录 → token → 访问 /chat → 退出

Phase E.2: 数据库会话存储
├── 后端: chat_sessions / chat_nodes 表创建 + ORM 模型
├── 后端: Sessions API 改造（CRUD + 权限过滤）
└── 验收: 新建会话 → MySQL 写入 → 列表查询 → 删除

Phase E.3: 工作流重设计
├── 后端: Clarifier + Planner 双阶段
├── 后端: workflow.py 条件边重写 + answer_node 新增
├── 后端: SSE clarification 事件
├── 前端: ClarifierCard + ExecutionCard 组件
└── 验收: "我当前有哪些数据" → 追问 → 选择 → 正确链路

Phase E.4: 节点标题生成
├── 后端: TitleGenerator Agent + 异步调用
├── 后端: done 事件后触发
└── 验收: 完成对话 → 侧边栏显示标题

Phase E.5: 历史消息恢复
├── 后端: GET /sessions/{id} + Redis checkpoint → messages 转换
├── 前端: 侧边栏点击 → 消息渲染 + 节点分隔线
└── 验收: 点击历史会话 → 完整恢复所有消息

Phase E.6: UI 重设计
├── 前端: 三区式布局 + 所有新组件
├── 前端: 交互优化（hover、动画、空状态）
└── 验收: 视觉效果 + 交互流程完整性
```

---

## 十、关键约束与注意事项

1. **向后兼容**：保留 Redis checkpointer 用于工作流状态恢复，MySQL 仅存元数据
2. **认证粒度**：JWT 过期时间默认 24h，可配置
3. **异步标题生成**：不阻塞 SSE 流，标题生成失败不影响对话体验
4. **Clarifier 次数限制**：最多追问 2 次，防止死循环
5. **DeepAgent 模式**：本方案仅改造传统 Agent 模式（USE_DEEP_AGENT=false），DeepAgent 模式暂不涉及
6. **现有测试兼容**：14 个已有测试需要适配新的 workflow 结构

---

## 十一、验收标准

| # | 验收项 | 标准 |
|---|--------|------|
| 1 | 登录 | 未登录访问 /chat → 重定向 /login；正确密码登录成功；错误密码提示 |
| 2 | 用户隔离 | userA 看不到 userB 的会话列表；admin 可看全部 |
| 3 | 会话列表 | 侧边栏显示 LLM 生成的标题（非 thread_id 前缀） |
| 4 | 会话创建 | 发送消息 → MySQL 写入 chat_sessions + chat_nodes |
| 5 | 标题生成 | 对话完成 → 侧边栏自动出现标题（3s 内） |
| 6 | 标题编辑 | 双击标题 → inline 编辑 → Enter 保存 → API 更新 |
| 7 | 历史恢复 | 点击会话 → 完整加载所有消息（含 SQL/图表/表格/文本） |
| 8 | 会话删除 | 侧边栏删除 → MySQL + Redis 双删 → 列表刷新 |
| 9 | 意图确认 | "我当前有哪些数据" → Planner 追问 → 用户选择 → 正确执行 |
| 10 | SQL 失败短路 | 无法生成 SQL → 降级到 RAG/misc → finish（不继续无用步骤） |
| 11 | 空结果短路 | SQL 执行无数据 → misc 提示 → finish（不进入 analyst/chart） |
| 12 | Analyst 控制 | 数据不适合图表 → answer 纯文本 → finish（不生成图表） |
| 13 | 追问卡片 | 前端显示选项按钮 → 点击 → 作为消息发送 → Planner 重新分析 |
| 14 | 执行卡片 | Planner/Schema/SQL/... 各步骤行内展开，完成打勾 |
