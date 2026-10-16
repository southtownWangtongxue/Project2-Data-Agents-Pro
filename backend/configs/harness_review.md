# Harness 两臂对照(人工判定用)

- 样本数:18(含已排除占位,与采集批次一一对应)
- 判定说明:指标 3(子问题覆盖)对照原始提问逐项核对;指标 4(结论正确性)对照下方「工具行数据」核对答案中的数字。
- 判定标记:`[ ]` 未判 / `[x] 过` / `[x] 不过`

## 1. 统计各表的数据量

- 模型:`qwen-flash`
- HARNESS:接地 `None` / 维度 `None` ()
- LEGACY:接地 `None` / 维度 `None`

> ⚠️ **已排除**:legacy 侧未采到答案(流超时/取消),该样本不计入对比,保留占位以对齐采集批次。

### 工具行数据(run_sql result)

(本轮未采集到工具行数据)

### 两臂答案

**HARNESS:**

## 各表数据量统计

| 表名 | 说明 | 数据量 |
|------|------|--------|
| `approval_records` | 审批记录表 | **0** |
| `chat_nodes` | 对话节点表（每轮问答） | **111** |
| `chat_sessions` | 会话表 | **114** |
| `da_sys_user` | 系统用户表 | **1** |
| `session_events` | 会话事件表 | **924** |

### 简要分析
- **会话活跃情况**：共 114 个会话，产生 111 个对话节点，平均每会话约 1轮问答。
- **事件记录丰富**：924 条事件记录，说明每个节点平均关联约 8 条事件（SQL执行、结果返回、分析等）。
- **无审批数据**：审批记录表为空，当前可能未启用审批流程或暂无审批操作。
- **系统用户**：仅 1 个用户账号。

### 人工判定

- 指标 3 子问题覆盖:`[ ]`
- 指标 4 结论正确性:`[ ]`

## 2. 统计各表的数据量

- 模型:`qwen-flash`
- HARNESS:接地 `None` / 维度 `None` ()
- LEGACY:接地 `None` / 维度 `None`

> ⚠️ **已排除**:legacy 侧未采到答案(流超时/取消),该样本不计入对比,保留占位以对齐采集批次。

### 工具行数据(run_sql result)

(本轮未采集到工具行数据)

### 两臂答案

**HARNESS:**

各表数据量统计如下：

| 表名 | 数据量 |
|---|---|| approval_records（审批记录） | 0 |
| chat_nodes（对话节点） | 112 |
| chat_sessions（会话） | 115 |
| da_sys_user（系统用户） | 1 |
| session_events（会话事件） |934 |

**简要分析：**
- **session_events** 数据量最大（934条），说明每次会话交互产生了较多事件日志。
- **chat_sessions** 有 115个会话，**chat_nodes** 有 112 个节点，平均每个会话约 1 轮问答。
- **approval_records** 为空，当前暂无审批记录。
- **da_sys_user** 仅有 1 条用户数据（可能是管理员账号）。

### 人工判定

- 指标 3 子问题覆盖:`[ ]`
- 指标 4 结论正确性:`[ ]`

## 3. 查询所有产品清单

- 模型:`qwen-flash`
- HARNESS:接地 `None` / 维度 `None` ()
- LEGACY:接地 `None` / 维度 `None`

> ⚠️ **已排除**:legacy 侧未采到答案(流超时/取消),该样本不计入对比,保留占位以对齐采集批次。

### 工具行数据(run_sql result)

(本轮未采集到工具行数据)

### 两臂答案

**HARNESS:**

当前数据库中没有产品相关的表。现有表结构如下：| 表名 | 说明 ||---|---|
| `approval_records` | 审批记录 |
| `chat_nodes` | 聊天问答节点 |
| `chat_sessions` | 聊天会话 |
| `da_sys_user` | 系统用户 |
| `session_events` | 会话事件 |

该数据库是 **DataAgent Pro** 系统的运行库，存储的是会话、审批和用户数据，不包含产品信息。

如果您想查询产品清单，请确认：
1. 是否有其他业务数据库包含产品数据？
2. 或者您想查询的是**系统用户列表**（`da_sys_user` 表）？

### 人工判定

- 指标 3 子问题覆盖:`[ ]`
- 指标 4 结论正确性:`[ ]`

## 4. 帮我分析数据库整体概况

- 模型:`qwen-flash`
- HARNESS:接地 `None` / 维度 `None` ()
- LEGACY:接地 `None` / 维度 `None`

> ⚠️ **已排除**:legacy 侧未采到答案(流超时/取消),该样本不计入对比,保留占位以对齐采集批次。

### 工具行数据(run_sql result)

(本轮未采集到工具行数据)

### 两臂答案

**HARNESS:**

## 数据库整体概况分析

### 一、表结构与数据量

| 表名 | 记录数 | 说明 |
|------|--------|------|
| `chat_sessions` | **117** | 会话主表 |
| `chat_nodes` | **114** | 会话中的问答轮次节点 |
| `session_events` | **953** | 会话事件流水（消息/SQL/分析等） |
| `da_sys_user` | **1** | 系统用户表 |
| `approval_records` | **0** | 审批记录表 |

> 共 **5 张表**，总计 **1,185 条记录**。

---

### 二、用户情况

- 当前仅有 **1 个活跃用户**：`admin`（管理员），状态正常。
- 所有 117个会话均由该用户创建。
- 最后登录 IP 和时间均为空，说明可能尚未正式登录或为测试账号。

---

### 三、会话活跃度（近 5 天）

| 日期 | 新建会话数 |
|------|-----------|
| 2026-10-15 | **45** |
| 2026-10-14 | **50** |
| 2026-10-13 | 5 |
| 2026-10-12 | 16 |
|2026-10-11 | 1 |

- 数据时间跨度：**2026-10-11 ~ 2026-10-15**（5 天）。
- 最近两天（10/14、10/15）是活跃高峰，合计 **95 个会话**，占总量的 **81%**。
- 平均每天约 **23 个会话**。

---

### 四、会话事件分布（953 条事件）

| 事件类型 | 数量 | 占比 |
|----------|------|------|
| `user_message` / `turn_start` | 各 228 | 交互入口 |
| `turn_end` | 217 | 轮次结束（约 11 轮未完成） |
| `analysis` | 119 | LLM 分析输出 |
| `plan` | 53 | 计划步骤 |
| `clarification` | 48 | 澄清请求 |
| `tool_chain` | 31 | 工具链调用 |
| `sql` | 12 | SQL 查询执行 |
| `result` | 12 | 查询结果返回 |
| `chart` | 5 | 图表生成 |
| `error` | 0 | 无错误事件 |

**关键洞察：**
- 用户消息与 turn_start 一致（228），说明大部分轮次有完整交互。
- `turn_end` 仅 217 条，比 `turn_start` 少 11 条，可能存在 **11 轮会话未正常结束**。
- SQL 查询仅 12 次，说明实际触发数据库查询的比例较低（约5% 的轮次）。
- 无 `error` 事件，运行状态健康。

---

### 五、审批模块

- `approval_records` 表为空，**无任何审批记录**。
- 审批功能可能尚未启用或未配置审批流程。

---

### 六、总结

| 维度 | 评估 |
|------|------|
| **数据规模** | 小体量，适合测试/小规模使用 |
| **活跃度** | 近期增长明显，10/14-15 为高峰 |
| **用户覆盖** | 仅 1 个用户，需推广多用户场景 |
| **功能使用** | 会话和消息功能正常，SQL 查询使用率低 |
| **系统健康** | 无错误事件，运行稳定 |
| **审批功能** | 未启用，待配置 |

### 人工判定

- 指标 3 子问题覆盖:`[ ]`
- 指标 4 结论正确性:`[ ]`

## 5. 每个表有多少条记录？

- 模型:`qwen-flash`
- HARNESS:接地 `None` / 维度 `None` ()
- LEGACY:接地 `None` / 维度 `None`

> ⚠️ **已排除**:legacy 侧未采到答案(流超时/取消),该样本不计入对比,保留占位以对齐采集批次。

### 工具行数据(run_sql result)

(本轮未采集到工具行数据)

### 两臂答案

**HARNESS:**

各表记录数如下：

| 表名 | 记录数 |
|---|---|| approval_records（审批记录） | 0 |
| chat_nodes（对话节点） | 115 |
| chat_sessions（会话） | 118 |
| da_sys_user（系统用户） | 1 |
| session_events（会话事件） |957 |

共 **5** 张表，累计 **1,191** 条记录。其中 `approval_records` 为空表，`session_events` 数据量最大（957 条）。

### 人工判定

- 指标 3 子问题覆盖:`[ ]`
- 指标 4 结论正确性:`[ ]`

## 6. 最近7天的会话数量趋势如何

- 模型:`qwen-flash`
- HARNESS:接地 `None` / 维度 `None` ()
- LEGACY:接地 `None` / 维度 `None`

> ⚠️ **已排除**:legacy 侧未采到答案(流超时/取消),该样本不计入对比,保留占位以对齐采集批次。

### 工具行数据(run_sql result)

(本轮未采集到工具行数据)

### 两臂答案

**HARNESS:**

## 最近7天会话数量趋势

**结论：** 会话量在10月14日出现显著峰值，整体呈快速上升趋势。

### 关键数据

| 日期 | 会话数 |
|------|--------|
| 2026-10-11 | 1 |
| 2026-10-12 | 16 |
|2026-10-13 | 5 |
| **2026-10-14** | **50**（峰值） |
| 2026-10-15 | 47 |

- 近5天共 **119** 个会话，日均约 **24**个
- 10月14日较前一日增长 **900%**，是10月13日的10倍
- 10月15日略有回落但仍维持在高位### 数据口径
- 数据来源：`chat_sessions` 表，按 `created_at` 统计每日新建会话数
- 时间范围：2026-10-11 至 2026-10-15（共5天有数据）

### 人工判定

- 指标 3 子问题覆盖:`[ ]`
- 指标 4 结论正确性:`[ ]`

## 7. 什么是GMV？

- 模型:`qwen-flash`
- HARNESS:接地 `None` / 维度 `None` ()
- LEGACY:接地 `None` / 维度 `None`

> ⚠️ **已排除**:legacy 侧未采到答案(流超时/取消),该样本不计入对比,保留占位以对齐采集批次。

### 工具行数据(run_sql result)

(本轮未采集到工具行数据)

### 两臂答案

**HARNESS:**

**GMV（Gross Merchandise Volume，商品交易总额）**是电商、本地生活及平台型业务中最核心的规模指标。

### 核心定义
GMV 指在**特定统计周期内**，通过平台完成下单的商品或服务**总价值**。它反映的是"交易流水规模"，而非实际到账金额或利润。### 常见计算方式
- `GMV = 订单数量 × 平均客单价`
- 或 `GMV = 所有成交订单金额之和`

### 关键包含与不包含项

| 项目 | 是否计入 GMV | 说明 |
|------|-------------|------|
| 已支付订单 | ✅ 是 | 无论是否发货/确认收货 |
| 未支付订单 | ❌ 否 | 主流口径以支付成功为准 |
| 退款/退货 | ❌ 否（理想） | 但很多平台不实时扣减，导致虚高 |
| 平台实际营收 | ❌ 否 | GMV ≠ 收入，平台赚的是佣金/服务费 |

### ⚠️ 使用注意
1. **口径差异大**：不同公司对 GMV 的定义可能不同，对比时需确认规则。
2. **非盈利指标**：GMV 高不代表赚钱，需结合毛利率、净利率等综合评估。
3. **防"注水"**：建议搭配"有效 GMV"（扣除退款/异常订单）一起看。

### 人工判定

- 指标 3 子问题覆盖:`[ ]`
- 指标 4 结论正确性:`[ ]`

## 8. 你好

- 模型:`qwen-flash`
- HARNESS:接地 `None` / 维度 `None` ()
- LEGACY:接地 `None` / 维度 `None`

> ⚠️ **已排除**:legacy 侧未采到答案(流超时/取消),该样本不计入对比,保留占位以对齐采集批次。

### 工具行数据(run_sql result)

(本轮未采集到工具行数据)

### 两臂答案

**HARNESS:**

你好！我是 DataAgent Pro 的数据智能体，可以帮你查询业务数据、生成报表和分析指标。有什么需要帮忙的吗？

### 人工判定

- 指标 3 子问题覆盖:`[ ]`
- 指标 4 结论正确性:`[ ]`

## 9. 统计各表的数据量

- 模型:`qwen-flash`
- HARNESS:接地 `None` / 维度 `None` ()
- LEGACY:接地 `None` / 维度 `None`

> ⚠️ **已排除**:legacy 侧未采到答案(流超时/取消),该样本不计入对比,保留占位以对齐采集批次。

### 工具行数据(run_sql result)

(本轮未采集到工具行数据)

### 两臂答案

**HARNESS:**

各表数据量统计如下：

| 表名 | 数据量 |
|------|--------|| approval_records（审批记录） | 0 条 |
| chat_nodes（对话节点） | 123 条 |
| chat_sessions（会话） | 126 条 || da_sys_user（系统用户） | 1 条 |
| session_events（会话事件） | 1,059 条 |

**合计：1,309 条**

**简要分析：**
- **session_events** 是数据量最大的表，平均每个会话约 8.4 个事件（1059 ÷ 126），说明每次对话交互产生了多条事件记录。
- **chat_nodes** 与 **chat_sessions**数量接近（123 vs 126），表明大部分会话只有 1 轮问答。
- **approval_records** 为空，当前尚无审批操作记录。
- **da_sys_user** 仅 1 条，为当前管理员账号。

### 人工判定

- 指标 3 子问题覆盖:`[ ]`
- 指标 4 结论正确性:`[ ]`

## 10. 每个表有多少条记录？

- 模型:`qwen-flash`
- HARNESS:接地 `None` / 维度 `None` ()
- LEGACY:接地 `None` / 维度 `None`

> ⚠️ **已排除**:legacy 侧未采到答案(流超时/取消),该样本不计入对比,保留占位以对齐采集批次。

### 工具行数据(run_sql result)

(本轮未采集到工具行数据)

### 两臂答案

**HARNESS:**

各表记录数如下：

| 表名 | 记录数 |
|---|---|| `approval_records`（审批记录） | 0 |
| `chat_nodes`（对话节点） | 124 |
| `chat_sessions`（会话） | 127 |
| `da_sys_user`（系统用户） | 1 |
| `session_events`（会话事件） | 1,069 |

**数据口径：** 均为全表 `COUNT(*)`，未加任何过滤条件。

### 人工判定

- 指标 3 子问题覆盖:`[ ]`
- 指标 4 结论正确性:`[ ]`

## 11. 帮我分析数据库整体概况

- 模型:`qwen-flash`
- HARNESS:接地 `None` / 维度 `None` ()
- LEGACY:接地 `None` / 维度 `None`

> ⚠️ **已排除**:legacy 侧未采到答案(流超时/取消),该样本不计入对比,保留占位以对齐采集批次。

### 工具行数据(run_sql result)

(本轮未采集到工具行数据)

### 两臂答案

**HARNESS:**

## 数据库整体概况分析

### 一、表结构与数据量

| 表名 | 记录数 | 时间跨度 | 说明 |
|---|---|---|---|
| `chat_sessions` | **128** | 2026-10-11 ~2026-10-15 | 会话主表 |
| `chat_nodes` | **125** | 同上 | 每轮问答节点 |
| `session_events` | **1,079** | 同上 | 会话事件流水 |
| `da_sys_user` | **1** | — | 系统用户（仅 admin） |
| `approval_records` | **0** | — | 审批记录（暂无数据） |

> 数据覆盖 **5 天**，系统于 10 月 11 日上线。

---

### 二、用户情况

目前仅有 **1 个活跃用户**：`admin`（管理员），所有 128 个会话均由该用户创建。无其他普通用户接入。

---

### 三、活跃度趋势

| 日期 | 新建会话数 |
|---|---|
| 10-11 (周六) | 1 |
| 10-12 (周日) | 16 |
| 10-13 (周一) | 5 |
| 10-14 (周二) | 50 |
| 10-15 (周三) | 56 |

**关键发现：**
- 活跃度呈 **快速上升趋势**，10-14 和 10-15 两天占总量近 **78%**（106/128）。
- 日均会话从 1 增长到 56，系统正在被高频使用。

---

### 四、交互深度（事件类型分布）

| 事件类型 | 数量 | 占比 |
|---|---|---|
| user_message | 253 | 23.4% |
| turn_start | 253 | 23.4% |
| turn_end | 242 | 22.4% |
| analysis | 134 | 12.4% |
| plan | 60 | 5.6% |
| clarification | 52 | 4.8% |
| tool_chain | 42 | 3.9% |
| sql | 17 | 1.6% |
| result | 17 | 1.6% |
| chart | 9 | 0.8% |

**关键洞察：**
- 共约 **253 轮对话**（turn_start ≈ user_message），平均每会话 **~2 轮**。
- 系统完成了 **134 次分析**、**60 次计划**、**52 次澄清**，说明交互质量较高，不只是简单问答。
- SQL 查询仅 17 次、图表 9 次，**数据查询类功能使用率偏低**，大部分交互可能集中在规划/澄清环节。

---

### 五、审批模块

`approval_records` 表为空，说明：
- 审批流程尚未启用，或当前测试阶段未触发审批场景。

---

### 六、总结与建议

| 维度 | 状态 | 建议 |
|---|---|---|
| 用户规模 | 仅 1 人 | 推广更多用户接入，验证多用户并发 |
| 活跃度 | 快速增长中 | 关注 10-15 峰值后的稳定性 |
| 交互深度 | 平均 2 轮/会话 | 可优化首轮回答准确率，减少澄清轮次 |
| 数据查询 | 使用率低 | 加强 SQL 生成与可视化能力的引导 |
| 审批模块 | 未启用 | 评估是否需要在业务流程中引入审批机制 |

### 人工判定

- 指标 3 子问题覆盖:`[ ]`
- 指标 4 结论正确性:`[ ]`

## 12. 统计各表的数据量

- 模型:`nemotron-3-ultra`
- HARNESS:接地 `None` / 维度 `None` ()
- LEGACY:接地 `None` / 维度 `None`

> ⚠️ **已排除**:legacy 侧未采到答案(流超时/取消),该样本不计入对比,保留占位以对齐采集批次。

### 工具行数据(run_sql result)

(本轮未采集到工具行数据)

### 两臂答案

**HARNESS:**

**各表数据量统计**

| 表名 | 行数 |
|------|------|
| approval_records | 0 |
| chat_nodes | 129 |
| chat_sessions | 132 |
| da_sys_user | 1 |
| session_events | 1,127 |

**数据说明**
- 共 5 张业务表，总计 1,389 行数据
- `approval_records` 目前为空（暂无审批记录）
- `da_sys_user` 仅 1 条用户记录（可能为初始化管理员账号）
- `session_events` 数据量最大（1,127 行），存储会话过程中的各类事件日志

*SQL：单条 UNION ALL 聚合查询，耗时 16ms，返回 5 行*

**LEGACY:**

SELECT 'approval_records' AS table_name, COUNT(*) AS row_count FROM approval_records
UNION ALL
SELECT 'chat_nodes', COUNT(*) FROM chat_nodes
UNION ALL
SELECT 'chat_sessions', COUNT(*) FROM chat_sessions
UNION ALL
SELECT 'da_sys_user', COUNT(*) FROM da_sys_user
UNION ALL
SELECT 'session_events', COUNT(*) FROM session_events;共查询到 5 条记录；row_count 合计 1377.0，均值 275.4，最小值 0.0，最大值 1117.0
### 数据概览
系统共包含 **5 张表**，总数据量 **1,377 条**。数据分布极不均衡：**session_events** 单表占比 **81.1%**，而 **approval_records** 为空表，**da_sys_user** 仅 1 条记录。

### 数据洞察
- **session_events 占主导**：**1,117 条**（占总量 **81.1%**），为核心事件日志表，数据量是其他业务表总和的 **4.3 倍**。
- **会话相关表规模接近**：**chat_sessions (131)** 与 **chat_nodes (128)** 相差仅 **3 条**，符合会话-节点 1:N 的业务预期。
- **用户表极小**：**da_sys_user 仅 1 条**，疑似为系统配置/初始化账号表，非业务用户表。
- **空表预警**：**approval_records 0 条**，审批功能可能未上线或数据未回流。
- **长尾分布显著**：Top 1 表占比超 80%，平均值 **275.4** 失去代表性，中位数仅 **128**。

| 表名 | 行数 | 占比 |
|------|------|------|
| session_events | **1,117** | **81.1%** |
| chat_sessions | **131** | **9.5%** |
| chat_nodes | **128** | **9.3%** |
| da_sys_user | **1** | **0.1%** |
| approval_records | **0** | **0%** |

### 异常关注
> **⚠️ approval_records 为空表**  
> 审批记录表无任何数据，需确认：  
> 1. 审批功能是否已发布？  
> 2. 是否存在数据写入路径缺失（如前端未埋点、后端未落库）？  
> 3. 是否为新建表待迁移历史数据？

> **ℹ️ da_sys_user 单行数据**  
> 仅 1 条用户记录，建议核对：  
> - 是否为超级管理员初始化账号？  
> - 业务用户是否存储于其他表（如外部认证系统）？

> **📈 session_events 数据量突变风险**  
> 单表超 1 千行，若为高频事件日志，需关注：  
> - 分区/归档策略是否就绪？  
> - 查询性能是否已评估索引覆盖？

### 人工判定

- 指标 3 子问题覆盖:`[ ]`
- 指标 4 结论正确性:`[ ]`

## 13. 每个表有多少条记录？

- 模型:`nemotron-3-ultra`
- HARNESS:接地 `None` / 维度 `None` ()
- LEGACY:接地 `None` / 维度 `None`

> ⚠️ **已排除**:legacy 侧未采到答案(流超时/取消),该样本不计入对比,保留占位以对齐采集批次。

### 工具行数据(run_sql result)

(本轮未采集到工具行数据)

### 两臂答案

**HARNESS:**

各表记录数统计：

| 表名 | 记录数 |
|------|--------|
| approval_records | 0 |
| chat_nodes | 130 |
| chat_sessions | 133 |
| da_sys_user | 1 |
| session_events | 1,138 |

**数据口径**：单条 SQL（UNION ALL）一次性查完 5 张表，耗时 16ms。

**LEGACY:**

SELECT 'approval_records' AS table_name, COUNT(*) AS record_count FROM approval_records
UNION ALL
SELECT 'chat_nodes', COUNT(*) FROM chat_nodes
UNION ALL
SELECT 'chat_sessions', COUNT(*) FROM chat_sessions
UNION ALL
SELECT 'da_sys_user', COUNT(*) FROM da_sys_user
UNION ALL
SELECT 'session_events', COUNT(*) FROM session_events;共查询到 5 条记录；record_count 合计 1389.0，均值 277.8，最小值 0.0，最大值 1127.0
### 数据概览
系统共包含 **5 张表**，总记录数 **1,389 条**，但分布极不均匀：**session_events** 独占 **1,127 条（81.1%）**，其余四表合计仅 262 条。

### 数据洞察
- **session_events 占比高达 81.1%**（1,127/1,389），是核心业务事件表  
- **chat_sessions 与 chat_nodes 数量接近**（132 vs 129），会话与节点近似 1:1 对应  
- **approval_records 为空表**（0 条），可能尚未启用或已归档  
- **da_sys_user 仅 1 条记录**，疑似仅保留超级管理员或初始化账号  
- 平均每表 **277.8 条**，但标准差 **479.1**，分布严重右偏  

| 表名 | 记录数 | 占比 |
|------|--------|------|
| session_events | **1,127** | **81.1%** |
| chat_sessions | **132** | 9.5% |
| chat_nodes | **129** | 9.3% |
| da_sys_user | **1** | 0.1% |
| approval_records | **0** | 0% |

### 异常关注
> ⚠️ **approval_records 无任何数据** — 确认审批功能是否上线或数据是否迁移至其他表  
> ⚠️ **da_sys_user 仅 1 条** — 核对用户导入/同步流程，防止权限管理缺失  
> ⚠️ **session_events 量级远超其它表** — 评估存储增长与查询性能，考虑分区或归档策略

### 人工判定

- 指标 3 子问题覆盖:`[ ]`
- 指标 4 结论正确性:`[ ]`

## 14. 统计各表的数据量

- 模型:`qwen-flash`
- HARNESS:接地 `False` / 维度 `3` (对比, 构成, 异常)
- LEGACY:接地 `False` / 维度 `5`

### 工具行数据(run_sql result)

(本轮未采集到工具行数据)

### 两臂答案

**HARNESS:**

## 各表数据量统计

**结论**:库内共 5 张表,合计 **1,537 行**。数据高度集中于 `session_events`(事件流水),占总量约 81.3%;`approval_records` 为空表。

| 表名 | 行数 | 占比 |
|---|---:|---:|
| session_events | 1,250 | 81.3% |
| chat_sessions | 146 | 9.5% |
| chat_nodes | 140 | 9.1% |
| da_sys_user | 1 | 0.1% |
| approval_records | 0 | 0% |

**分析维度**

- **构成**:事件流水表 `session_events`(1,250 行)是绝对主体,存储每轮问答的 user_message/sql/result/chart 等事件;会话表 `chat_sessions`(146)与问答节点表 `chat_nodes`(140)量级相当,平均每会话约 0.96 个节点(140/146),说明多数会话仅 1 轮问答,存在较多短会话。
- **异常/空表**:`approval_records` 为 0 行,即尚无审批记录(与当前 read_only 审批档位一致,未发生需人工审批的写操作);`da_sys_user` 仅 1 行,当前只有1 个登录账号。
- **关联一致性**:chat_nodes(140) < chat_sessions(146),无节点数超过会话数的异常,数据关系正常。

**依据**:以上均来自单次 UNION ALL 统计各表 COUNT(*) 的查询(执行耗时 15ms,结果未截断)。

**LEGACY:**

SELECT 'approval_records' AS table_name, COUNT(*) AS row_count FROM approval_records UNION ALL SELECT 'chat_nodes' AS table_name, COUNT(*) AS row_count FROM chat_nodes UNION ALL SELECT 'chat_sessions' AS table_name, COUNT(*) AS row_count FROM chat_sessions UNION ALL SELECT 'da_sys_user' AS table_name, COUNT(*) AS row_count FROM da_sys_user UNION ALL SELECT 'session_events' AS table_name, COUNT(*) AS row_count FROM session_events;共查询到 5 条记录；row_count 合计 1526.0，均值 305.2，最小值 0.0，最大值 1241.0
### 数据概览
当前统计的 **5** 张表总数据量为 **1526** 行，其中 `session_events` 表数据量最高，占整体数据的 **81.32%**，数据分布明显不均衡。

### 数据洞察
- **数据量排名**：`session_events` 以 **1241** 行位居第一，`chat_sessions` 为 **145** 行，`chat_nodes` 为 **139** 行，`da_sys_user` 仅 **1** 行，`approval_records` 为 **0** 行。
- **占比结构**：`session_events` 占总数据量的 **81.32%**，`chat_sessions` 和 `chat_nodes` 合计占 **18.61%**，其余表占比极低。

| 表名 | 数据量 | 占比 |
|---|---:|---:|
| `session_events` | **1241** | **81.32%** |
| `chat_sessions` | **145** | **9.50%** |
| `chat_nodes` | **139** | **9.11%** |
| `da_sys_user` | **1** | **0.07%** |
| `approval_records` | **0** | **0.00%** |

- **离散程度较高**：数据量平均值为 **305.2**，最大值为 **1241**，最小值为 **0**，标准差为 **527.90**，说明表间数据量差异较大。
- **头部集中明显**：`session_events` 的数据量是平均值的 **4.07** 倍，是当前数据量增长的主要来源。

### 异常关注
- `approval_records` 表数据量为 **0**，可能存在审批功能未启用、数据未写入或同步缺失的问题。
- `da_sys_user` 表仅有 **1** 行数据，若为生产环境，用户主数据量明显偏低，需确认是否为测试环境或初始化数据不完整。
- `session_events` 表数据量达到 **1241** 行，远高于其他表，需关注事件日志是否持续增长，并评估是否需要归档或清理策略。

> 当前整体数据量主要由 `session_events` 驱动，其他业务表数据稀疏，建议优先核查审批记录与用户数据是否正常生成。

### 人工判定

- 指标 3 子问题覆盖:`[ ]`
- 指标 4 结论正确性:`[ ]`

## 15. 每个表有多少条记录？

- 模型:`qwen-flash`
- HARNESS:接地 `True` / 维度 `4` (对比, 构成, 趋势, 异常)
- LEGACY:接地 `False` / 维度 `4`

### 工具行数据(run_sql result)

(本轮未采集到工具行数据)

### 两臂答案

**HARNESS:**

各表记录数如下（依据：单条 UNION ALL 统计各表行数查询，共 5 张表）：

| 表名 | 记录数 |
|---|---|
| session_events | 1,260 |
| chat_sessions | 147 |
| chat_nodes | 141 |
| da_sys_user | 1 |
| approval_records | 0 |

**分析维度：**

- **构成**：数据量高度集中在 `session_events`（1,260 条，占全库 88.5%），它是会话过程事件流水表，天然随问答轮次增长。
- **对比/一致性**：`chat_sessions`（147 个会话）略多于 `chat_nodes`（141 个节点），说明有约 6 个会话尚未产生任何问答节点（可能刚创建或空会话）；平均每会话约 0.96 个节点，而平均每会话约 8.6 条事件，事件粒度远细于节点粒度。
- **异常/空表**：`approval_records` 为 0 条，即当前无任何审批记录（与当前 read_only 审批档位一致，尚未触发过审批）；`da_sys_user` 仅 1 个账号（即当前 admin）。

图表配置已生成（柱状图，见上方 make_chart 结果）。

**LEGACY:**

SELECT 'approval_records' AS table_name, COUNT(*) AS record_count FROM approval_records
UNION ALL
SELECT 'chat_nodes' AS table_name, COUNT(*) AS record_count FROM chat_nodes
UNION ALL
SELECT 'chat_sessions' AS table_name, COUNT(*) AS record_count FROM chat_sessions
UNION ALL
SELECT 'da_sys_user' AS table_name, COUNT(*) AS record_count FROM da_sys_user
UNION ALL
SELECT 'session_events' AS table_name, COUNT(*) AS record_count FROM session_events;共查询到 5 条记录；record_count 合计 1538.0，均值 307.6，最小值 0.0，最大值 1251.0
### 数据概览
当前 **5** 张表总记录数为 **1538** 条，数据分布高度集中，**session_events** 是主要数据承载表。

### 数据洞察
- **session_events** 记录数最多，为 **1251** 条，占总记录数的 **81.34%**，是整体数据量的核心来源。
- **chat_sessions** 记录数为 **146** 条，略高于 **chat_nodes** 的 **140** 条，两者合计 **286** 条，占总记录数的 **18.59%**。
- **da_sys_user** 仅有 **1** 条记录，占比 **0.07%**，数据量极低，可能处于初始化或测试状态。
- **approval_records** 记录数为 **0**，说明该表当前无业务数据沉淀。
- 整体平均值仅为 **307.6**，但标准差达到 **532.17**，说明表间记录数差异较大，数据分布明显偏斜。

| 表名 | 记录数 | 占比 |
|---|---:|---:|
| approval_records | **0** | **0.00%** |
| chat_nodes | **140** | **9.10%** |
| chat_sessions | **146** | **9.49%** |
| da_sys_user | **1** | **0.07%** |
| session_events | **1251** | **81.34%** |

> **核心结论：** 数据量主要由 **session_events** 贡献，其余表合计仅 **287** 条，占比 **18.66%**。

### 异常关注
- **approval_records** 为空表，若该表用于审批流程，需确认是否存在数据未写入、功能未启用或统计范围遗漏。
- **da_sys_user** 仅 **1** 条记录，用户基础数据过少，可能影响依赖用户信息的业务分析。
- **session_events** 记录数远高于其他表，若业务上事件量正常则属合理，但需进一步排查是否存在重复事件、批量导入或日志膨胀问题。
- 基础统计未标记数值型离群点，但 **0** 和 **1** 这类极低值在业务上仍具有明显异常提示意义。

### 人工判定

- 指标 3 子问题覆盖:`[ ]`
- 指标 4 结论正确性:`[ ]`

## 16. 统计各表的数据量

- 模型:`qwen-flash`
- HARNESS:接地 `True` / 维度 `4` (对比, 构成, 排名, 异常)
- LEGACY:接地 `False` / 维度 `5` — 注意:`legacy_grounding_reliability=degraded_nested_derivation`(嵌套派生判不出来,未接地数字 [1604.0, 320.8, 81.55, 18.4, 0.06, 556.74, 9.41, 8.98] 不构成幻觉证据)

### 工具行数据(run_sql result)

(本轮未采集到工具行数据)

### 两臂答案

**HARNESS:**

## 结论

全库共 5 张表、**1,615 行**数据,其中 `session_events`(会话事件流)以 1,317 行占绝对大头(约 81.5%),其余表数据量都很小。

## 各表数据量明细

| 表名 | 行数 | 占比 | 说明 |
|---|---|---|---|
| session_events | 1,317 | 81.5% | 会话事件流(提问/SQL/结果/图表等) |
| chat_sessions | 152 | 9.4% | 会话主表 |
| chat_nodes | 145 | 9.0% | 会话节点(每轮问答) |
| da_sys_user | 1 | 0.06% | 系统用户(仅 admin 1 人) |
| approval_records | 0 | 0% | 审批记录(空表) |

## 分析维度

**1. 构成与排名**(依据:统计各表行数的那次 UNION ALL 查询)
- 数据高度集中于 `session_events`,单表占全库 81.5%,是典型的"事件日志型"大表;
- `chat_sessions` 与 `chat_nodes` 体量接近(152 vs 145),符合"一个会话包含若干轮问答节点"的 1:N 结构,平均每会话约 0.95 个节点,说明多数会话只进行了一轮问答;
- `session_events` 平均每会话约 8.7 条事件,即每轮问答产生多条事件(用户消息、SQL、结果、分析等)。

**2. 异常/关注点**
- `approval_records` 为 0 行:审批功能尚未产生任何记录(当前审批档位为 read_only,只读查询不触发审批,属正常现象);
- `da_sys_user` 仅 1 人:系统目前只有 admin 一个账号,无普通用户。

**3. 可视化**

图表已生成(柱状图,见上方 make_chart 输出),直观呈现各表数据量级差异。

**LEGACY:**

SELECT 'approval_records' AS table_name, COUNT(*) AS row_count FROM approval_records
UNION ALL
SELECT 'chat_nodes' AS table_name, COUNT(*) AS row_count FROM chat_nodes
UNION ALL
SELECT 'chat_sessions' AS table_name, COUNT(*) AS row_count FROM chat_sessions
UNION ALL
SELECT 'da_sys_user' AS table_name, COUNT(*) AS row_count FROM da_sys_user
UNION ALL
SELECT 'session_events' AS table_name, COUNT(*) AS row_count FROM session_events
ORDER BY table_name;共查询到 5 条记录；row_count 合计 1604.0，均值 320.8，最小值 0.0，最大值 1308.0
### 数据概览
本次统计覆盖 **5** 张表，总数据量为 **1604** 行，平均每张表 **320.8** 行；其中 **session_events** 数据量最高，**approval_records** 数据量为 **0**。

### 数据洞察
- **session_events** 是数据量最大的表，共 **1308** 行，占总数据量的 **81.55%**，是主要事件流水表。
- **chat_sessions** 与 **chat_nodes** 数据量接近，分别为 **151** 行和 **144** 行，合计 **295** 行，占总数据量的 **18.40%**。
- **da_sys_user** 仅 **1** 行，占比 **0.06%**，用户基础数据量极低。
- 数据分布不均衡：最大表数据量为 **1308**，最小表数据量为 **0**，标准差为 **556.74**，说明数据高度集中在少数表中。

| 表名 | 数据量 | 占比 |
|---|---:|---:|
| **session_events** | **1308** | **81.55%** |
| **chat_sessions** | **151** | **9.41%** |
| **chat_nodes** | **144** | **8.98%** |
| **da_sys_user** | **1** | **0.06%** |
| **approval_records** | **0** | **0.00%** |

### 异常关注
- **approval_records** 为 **0** 行，需要确认审批功能是否未启用、数据未写入或统计范围遗漏。
- **da_sys_user** 仅 **1** 行，若系统依赖用户体系，该数据量明显偏低，可能存在初始化不足或数据同步异常。
- **chat_nodes** 少于 **chat_sessions**，节点数为 **144**，会话数为 **151**；若预期每个会话至少包含 **1** 个节点，则可能存在节点缺失或关联数据不完整。
- **session_events** 占比达 **81.55%**，后续需关注其存储增长、索引性能和历史数据清理策略。

> 最显著异常是 **approval_records** 空表与 **da_sys_user** 单行表，建议优先核对业务链路和数据写入状态。

### 人工判定

- 指标 3 子问题覆盖:`[ ]`
- 指标 4 结论正确性:`[ ]`

## 17. 统计各表的数据量

- 模型:`qwen-flash`
- HARNESS:接地 `True` / 维度 `4` (对比, 构成, 排名, 异常)
- LEGACY:接地 `False` / 维度 `0`

> ⚠️ **已排除**:legacy 侧未采到答案(流超时/取消),该样本不计入对比,保留占位以对齐采集批次。

### 工具行数据(run_sql result)

(本轮未采集到工具行数据)

### 两臂答案

**HARNESS:**

## 结论

数据库共 **5 张表,合计 1,698 行**。数据高度集中在 `session_events`(事件流水表,占 81%),业务主体表(会话/节点)约 150 余条,用户表仅 1 人,审批表为空。

## 各维度分析

**1. 数据量排名**(依据:统计各表行数的那次 UNION ALL 查询)

| 排名 | 表名 | 行数 | 占比 |
|---|---|---|---|
| 1 | session_events(会话事件流水) | 1,378 | 81.2% |
| 2 | chat_sessions(会话) | 158 | 9.3% |
| 3 | chat_nodes(问答节点) | 151 | 8.9% |
| 4 | da_sys_user(系统用户) | 1 | 0.06% |
| 5 | approval_records(审批记录) | 0 | 0% |

**2. 构成与关联关系**(依据:同一次查询的行数对比)
- `session_events` 是 `chat_nodes` 的约 9.1 倍(1,378 / 151),符合"每个问答节点产生多条事件(用户消息/SQL/结果/图表等)"的模型,平均每轮问答约 9 条事件,属正常水平。
- `chat_sessions`(158)与 `chat_nodes`(151)数量接近,说明平均每会话约 0.95 轮问答,即大部分会话只有一轮交互,多轮深度会话较少。

**3. 异常/关注点**(依据:同一次查询)
- `approval_records` 为 **0 行**:当前审批档位为 read_only,尚无写入类操作触发审批,属预期内,非异常。
- `da_sys_user` 仅 **1 行**:库中只有 1 个登录账号(即当前 admin),普通用户尚未入驻。

图表配置已生成(柱状图),可直接渲染展示。

### 人工判定

- 指标 3 子问题覆盖:`[ ]`
- 指标 4 结论正确性:`[ ]`

## 18. 每个表有多少条记录？

- 模型:`qwen-flash`
- HARNESS:接地 `True` / 维度 `3` (对比, 构成, 异常)
- LEGACY:接地 `False` / 维度 `5` — 注意:`legacy_grounding_reliability=degraded_nested_derivation`(嵌套派生判不出来,未接地数字 [1689.0, 337.8, 81.65, 18.3, 0.06, 9.35, 8.94, 587.12] 不构成幻觉证据)

### 工具行数据(run_sql result)

(本轮未采集到工具行数据)

### 两臂答案

**HARNESS:**

## 结论

数据库共 5 张表,总计 **1,700 条记录**,其中 `session_events`(会话事件)占绝对大头(1,388 条,约 81.6%)。

## 各表记录数

| 表名 | 记录数 | 占比 |
|---|---:|---:|
| session_events | 1,388 | 81.6% |
| chat_sessions | 159 | 9.4% |
| chat_nodes | 152 | 8.9% |
| da_sys_user | 1 | 0.06% |
| approval_records | 0 | 0% |

## 分析

- **构成**:事件流水表 `session_events` 是数据主体,平均每轮问答产生约 9 条事件(1,388 ÷ 152),符合"一轮问答包含多条 user_message/sql/result 等事件"的设计。
- **对比**:`chat_sessions`(159)略多于 `chat_nodes`(152),差7 个,说明约 7 个会话尚未产生任何问答节点(可能是刚创建或只停留在澄清阶段)。
- **异常**:`approval_records` 为空表——当前没有任何审批记录,与当前 read_only 审批档位下无写操作相符;`da_sys_user` 仅 1 个用户(即当前 admin)。

**依据**:以上均基于「统计各表记录数」那次查询(单条 UNION ALL 汇总 5 张表的 COUNT(*))。

**LEGACY:**

SELECT 'approval_records' AS table_name, COUNT(*) AS record_count FROM approval_records
UNION ALL
SELECT 'chat_nodes', COUNT(*) FROM chat_nodes
UNION ALL
SELECT 'chat_sessions', COUNT(*) FROM chat_sessions
UNION ALL
SELECT 'da_sys_user', COUNT(*) FROM da_sys_user
UNION ALL
SELECT 'session_events', COUNT(*) FROM session_events;共查询到 5 条记录；record_count 合计 1689.0，均值 337.8，最小值 0.0，最大值 1379.0
### 数据概览
当前 5 张表共有 **1689** 条记录，数据高度集中在 **session_events** 表，其余表记录量较少。

### 数据洞察
- **session_events** 记录最多，为 **1379** 条，占总记录数的 **81.65%**，是主要数据载体。
- **chat_sessions** 和 **chat_nodes** 记录量接近，分别为 **158** 条和 **151** 条，合计占比 **18.30%**，说明会话与节点数据规模相当。
- **da_sys_user** 仅有 **1** 条记录，占比 **0.06%**，用户数据量极低。
- **approval_records** 为 **0** 条，未产生任何审批记录。

| 表名 | 记录数 | 占比 |
|---|---:|---:|
| session_events | **1379** | **81.65%** |
| chat_sessions | **158** | **9.35%** |
| chat_nodes | **151** | **8.94%** |
| da_sys_user | **1** | **0.06%** |
| approval_records | **0** | **0.00%** |

> **session_events** 的记录数是 **chat_sessions** 的约 **8.7 倍**，也是 **chat_nodes** 的约 **9.1 倍**。

### 异常关注
- **approval_records 为 0**：可能审批功能未启用、业务未发生审批，或数据同步/写入异常，需要优先确认。
- **da_sys_user 仅 1 条**：用户基础数据过少，可能影响权限、会话归属和审批链路，建议检查用户同步或初始化数据。
- **session_events 占比过高**：事件表可能快速增长，建议关注存储、查询性能和归档/清理策略。
- 记录分布不均衡，最大 **1379** 与最小 **0** 差距明显，标准差 **587.12**，说明数据量差异较大。

### 人工判定

- 指标 3 子问题覆盖:`[ ]`
- 指标 4 结论正确性:`[ ]`
