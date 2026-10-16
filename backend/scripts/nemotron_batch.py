"""nemotron 跨模型稳健性补采脚本(重试工具,HANDOVER §5.1 遗留)。

对 18 样本问题集去重后的 7 个问题,逐个经 run_shadow_comparison 跑
Harness 臂(legacy 空占位,该批次定位是「跨模型稳健性附录」,不比两臂),
构造路径与 chat.py 真实请求对齐(AgentLoopRunner.build_request)。

用法:
    cd backend && uv run python scripts/nemotron_batch.py           # 全量 7 题
    cd backend && uv run python scripts/nemotron_batch.py "你好"     # 单题冒烟

2026-10-16 首次尝试被上游阻塞:OpenRouter/Nvidia 侧该免费模型先是
工具调用 DEGRADED(400 "DEGRADED function cannot be invoked"),随后
流式 120s 零 chunk——均为 provider 侧故障,非本仓库代码问题;
当日 OpenRouter 配额本身已重置(usage=0)。上游恢复后重跑本脚本即可,
产出会追加进 configs/shadow_comparison.jsonl(不覆盖既有样本)。

配额注意:免费档每日请求数有限,逐题顺序执行;单题失败
(run_shadow_comparison 吞异常返回 None)不中断后续题目。
"""
import asyncio
import sys

from app.core.agent_loop import AgentLoopRunner
from app.graph.workflow import use_deep_agent
from app.harness.shadow import run_shadow_comparison

MODEL = "nemotron-3-ultra"

QUESTIONS = [
    "统计各表的数据量",
    "查询所有产品清单",
    "帮我分析数据库整体概况",
    "最近7天的会话数量趋势如何",
    "什么是GMV？",
    "你好",
    "每个表有多少条记录？",
]


async def run_one(question: str) -> dict | None:
    req = AgentLoopRunner.build_request(
        question=question, user_name="shadow", history=[], thread_id=None,
        mode="data", model=MODEL, web_search=False,
        deepagent_on=use_deep_agent(),
    )
    return await run_shadow_comparison(
        question, legacy_answer="", legacy_metrics={},
        user_name="shadow", model=MODEL,
        runtime_context=req.runtime_context, history=req.history,
    )


async def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    questions = [only] if only else QUESTIONS
    ok = fail = 0
    for q in questions:
        rec = await run_one(q)
        if rec is None:
            fail += 1
            print(f"FAIL  {q}")
            continue
        h = rec["harness"]
        ok += 1
        print(f"OK    {q} | rounds={h['llm_rounds']} sql={h['sql_count']} "
              f"tools={h['tool_calls']} 接地={h['grounded']} 未接地={h['ungrounded']} "
              f"维度={h['dim_count']} {h['duration_ms']}ms ctx_ok={h['ctx_ok']}")
    print(f"\n完成:成功 {ok} / 失败 {fail}")


if __name__ == "__main__":
    asyncio.run(main())
