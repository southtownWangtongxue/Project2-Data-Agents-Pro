"""
Quality Evaluator — ReAct 范式的质量评估节点 (Phase E.9)

在关键决策点引入 LLM 质量评估，替代简单的规则判断：
1. execute_sql 之后: 评估查询结果是否满足用户期望（如「Top10」只返回1行则质量不足）
2. analyst 之后: 动态评估数据是否适合图表展示

ReAct 范式 (Reason + Act):
    Observe (获取结果) → Reason (LLM评估质量) → Act (路由决策)
"""

import json
import logging

from app.core.config import settings
from app.core.llm import get_llm
from app.utils.json_encoder import CustomEncoder

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


async def evaluate_query_quality(
    question: str,
    sql: str,
    data: list[dict],
    columns: list[str],
) -> dict:
    """
    执行 SQL 后评估结果质量的 ReAct 节点。

    用 LLM 判断查询结果是否：
    - 充分回答了用户问题
    - 数据量合理（如 "Top10" 应有 ~10 行）
    - 数据有意义（不只是 1 行或全零）

    参数:
        question: 用户原始自然语言问题
        sql: 最终执行的 SQL 语句
        data: 查询结果行列表
        columns: 列名列表

    返回:
        {
            "quality": "good" | "insufficient" | "empty",
            "reason": str,       # 技术性原因说明（日志用）
            "feedback": str,    # 用户友好反馈（前端展示用）
        }
    """
    row_count = len(data)
    col_count = len(columns)

    # 空结果直接返回，不需要调 LLM
    if row_count == 0 or not columns:
        return {
            "quality": "empty",
            "reason": "查询返回 0 条记录",
            "feedback": (
                "查询未返回任何数据。可能原因：当前时间段暂无记录、"
                "数据尚未同步、或查询条件过于严格。建议尝试放宽时间范围或检查数据源。"
            ),
        }

    # 构建数据摘要（不发送完整数据，降低 token 消耗）
    sample_size = min(5, row_count)
    sample_data = data[:sample_size]
    sample_text = json.dumps(sample_data, ensure_ascii=False, indent=2, cls=CustomEncoder)

    # 数值列简要统计
    numeric_summary = {}
    for col in columns[:5]:  # 最多分析前 5 列
        values = []
        for row in data:
            v = row.get(col)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                values.append(v)
        if values:
            numeric_summary[col] = {
                "count": len(values),
                "min": round(min(values), 2),
                "max": round(max(values), 2),
                "unique": len(set(values)),
            }

    summary_text = json.dumps(numeric_summary, ensure_ascii=False, indent=2) if numeric_summary else "无数值列"

    client = get_llm()

    system_prompt = (
        "你是一个数据查询结果质量评估专家。用户提出数据分析问题后，系统执行了 SQL 查询。"
        "现在你需要评估查询结果的质量，判断是否值得继续进行数据分析和图表生成。\n\n"
        "质量等级定义：\n"
        '- "good": 结果充分、数据量合理，可以进行有意义的分析\n'
        '- "insufficient": 结果存在但过于稀疏/单薄，无法支撑有价值的分析\n'
        '- "empty": 查询无结果或列信息为空\n\n'
        "评估关键标准：\n"
        "1. 结果是否真正回答了用户问题？\n"
        '   - 如「Top10」应返回约 10 行，只返回 1 行说明数据不足或查询有问题\n'
        '   - 如「趋势分析」应返回多个时间点的数据\n'
        '2. 数据量是否合理？单条记录的「排名」无意义\n'
        "3. 数值是否有意义？全是 0/NULL 则无分析价值\n"
        "4. 结果是否与问题预期匹配？\n\n"
        "严格要求：\n"
        "1. 只返回 JSON 格式，不包含任何其他文字\n"
        "2. quality 取值：good / insufficient / empty\n"
        "3. reason: 简短的技术原因（中英文皆可）\n"
        "4. feedback: 对用户友好的中文说明，解释结果质量情况\n"
        '5. 反馈中可包含建议（如「建议扩大时间范围」、「当前月份暂无数据」等）\n'
        "6. 使用双引号"
    )

    user_message = (
        f"## 用户问题\n\n{question}\n\n"
        f"## 执行的 SQL\n\n```sql\n{sql}\n```\n\n"
        f"## 结果概览\n\n"
        f"- 行数: {row_count}\n"
        f"- 列数: {col_count}\n"
        f"- 列名: {columns[:10]}\n"
        f"- 数值列统计:\n{summary_text}\n\n"
        f"## 前 {sample_size} 行数据\n\n```json\n{sample_text}\n```\n\n"
        "请评估查询结果质量："
    )

    try:
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.2,
        )

        raw_content = response.choices[0].message.content.strip()

        # 去除可能的 markdown 代码块标记
        if raw_content.startswith("```"):
            lines = raw_content.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw_content = "\n".join(lines).strip()

        result = json.loads(raw_content)

        quality = result.get("quality", "good")
        # 规范化 quality 值
        if quality not in ("good", "insufficient", "empty"):
            quality = "good"

        logger.info(
            "[QualityEval] 查询质量评估: quality=%s, rows=%d, reason=%s",
            quality,
            row_count,
            result.get("reason", "")[:80],
        )

        return {
            "quality": quality,
            "reason": result.get("reason", ""),
            "feedback": result.get("feedback", ""),
        }

    except (json.JSONDecodeError, Exception) as exc:
        logger.warning(f"[QualityEval] LLM 调用或解析失败，使用规则兜底: {exc}")

        # 规则兜底：数据量判断
        if row_count == 1:
            # 单行数据很可能没有分析价值
            quality = "insufficient"
            reason = f"仅返回 {row_count} 条数据（规则兜底）"
        elif row_count < 3:
            quality = "insufficient"
            reason = f"数据量过少: {row_count} 行（规则兜底）"
        else:
            quality = "good"
            reason = f"返回 {row_count} 条数据（规则兜底）"

        return {
            "quality": quality,
            "reason": reason,
            "feedback": (
                f"查询返回了 {row_count} 条记录。"
                + ("数据量较少，分析结果可能不够全面。" if quality == "insufficient" else "")
            ),
        }


async def evaluate_chart_suitability(
    question: str,
    data: list[dict],
    columns: list[str],
    analysis_summary: str,
) -> dict:
    """
    分析完成后，动态评估数据是否适合图表展示。

    替代 Planner 阶段静态的 chart_suitable 判断，
    基于实际数据和用户意图做出更准确的决定。

    参数:
        question: 用户原始问题
        data: 查询结果
        columns: 列名
        analysis_summary: 分析摘要文本

    返回:
        {"suitable": bool, "reason": str}
    """
    row_count = len(data)

    # 快速规则判断，避免不必要的 LLM 调用
    if row_count == 0 or not columns:
        return {"suitable": False, "reason": "无数据或列信息为空"}

    # 单行单列表格：没有图表意义
    if row_count == 1 and len(columns) == 1:
        return {"suitable": False, "reason": "仅有单行单列数据，不适合图表展示"}

    # 判断是否有数值列
    has_numeric = False
    for col in columns:
        for row in data[:5]:
            v = row.get(col)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                has_numeric = True
                break
        if has_numeric:
            break

    if not has_numeric:
        return {"suitable": False, "reason": "查询结果无数值列，无法生成图表"}

    # 数据量充足且有数值列，调用 LLM 做精确判断
    client = get_llm()

    sample_data = data[:10]
    sample_text = json.dumps(sample_data, ensure_ascii=False, indent=2, cls=CustomEncoder)

    system_prompt = (
        "你是一个数据可视化专家。根据用户问题和实际查询结果，"
        "判断数据是否适合用图表展示。\n\n"
        "不适合图表展示的情况：\n"
        "- 数据是纯文本/描述性内容\n"
        "- 仅有单条记录（无法形成对比/趋势）\n"
        "- 数据量过少缺乏统计意义\n"
        "- 用户问题的本意是咨询/帮助而非数据查询\n\n"
        '严格要求：只返回 JSON: {"suitable": true/false, "reason": "原因"}\n'
        "使用双引号"
    )

    user_message = (
        f"## 用户问题\n\n{question}\n\n"
        f"## 查询结果\n\n"
        f"- 行数: {row_count}\n"
        f"- 列名: {columns}\n"
        f"- 分析摘要: {analysis_summary[:200]}\n\n"
        f"## 数据样本\n\n```json\n{sample_text}\n```\n\n"
        "请判断是否适合生成图表："
    )

    try:
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.1,
        )

        raw_content = response.choices[0].message.content.strip()
        if raw_content.startswith("```"):
            lines = raw_content.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw_content = "\n".join(lines).strip()

        result = json.loads(raw_content)
        suitable = bool(result.get("suitable", True))

        logger.info(
            "[QualityEval] 图表适配性评估: suitable=%s, reason=%s",
            suitable,
            result.get("reason", "")[:80],
        )

        return {
            "suitable": suitable,
            "reason": result.get("reason", ""),
        }

    except Exception as exc:
        logger.warning(f"[QualityEval] 图表评估 LLM 调用失败，使用规则兜底: {exc}")

        # 规则兜底
        if row_count >= 2 and has_numeric:
            return {"suitable": True, "reason": "规则兜底: 有多行数值数据"}
        return {"suitable": False, "reason": "规则兜底: 数据不足"}
