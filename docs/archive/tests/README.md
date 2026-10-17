# 归档测试套件（2026-10-17）

> 本目录是**停止日常维护**的纯逻辑测试套件快照。保留它们是作为历史记录与
> 最终回归参照；git 历史中同样完整保留（本目录提交前的 `backend/tests/`
> 与 `frontend-react/src/sdk/*.test.ts`）。

## 为什么归档

用户决策变更：**验证方式由「pytest / vitest 纯逻辑测试」改为「MCP 端到端验证」**。
理由：项目多次出现「单测全绿但真实链路炸」（温度硬编码、事件字段名不匹配、
provider key 解析、checkpointer 缺失等），单测给的是虚假信心；而真实链路问题
只能靠真实流量暴露。因此不再把单测作为主要门禁，改为每次交付用浏览器
(chrome-devtools MCP) 走真实链路。

注意：**归档不等于废弃**。这些用例仍是「已知契约」的清单，回归判定时可按需
参照；若要恢复日常执行，把文件移回原位置即可（见下）。

## 目录结构

```
docs/archive/tests/
├── backend/     ← 原 backend/tests/（25 个文件，含 __init__.py / fakes.py / mcp_echo_server.py）
└── frontend/    ← 原 frontend-react/src/sdk/*.test.ts（4 个）
```

## 归档时的规模（作为历史基线）

- 后端 225 passed（其中 `test_approve_edit.py` 为归档前最后一批新增）
- 前端 44 passed

## 恢复日常执行（如需）

```bash
# 后端
git mv docs/archive/tests/backend/* backend/tests/
cd backend && uv run pytest -q

# 前端
git mv docs/archive/tests/frontend/*.test.ts frontend-react/src/sdk/
cd frontend-react && npx vitest run
```

注意恢复后需同步去掉 `pyproject.toml` 中为归档添加的 `norecursedirs` 提示
（若已添加），并确认 `uv run pytest` 重新开始收集。

## 替代验证方式（当前门禁）

| 层 | 手段 |
|---|---|
| 后端 | MCP 端到端：真实 HTTP/SSE 请求 + 真实 DB + 真实前端走查 |
| 前端 | chrome-devtools MCP 走查真实页面（对话/步骤链/审批卡/表格/图表） |
| 构建 | `npm run build` / `tsc -b`（类型与打包，非逻辑断言） |
