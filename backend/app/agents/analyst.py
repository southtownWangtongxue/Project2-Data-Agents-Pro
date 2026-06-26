"""
Analyst Agent - 数据分析师
接收 SQL 执行结果集，进行统计分析并生成自然语言洞察
"""
import asyncio
import json
import statistics
import math

from app.core.config import settings
from app.core.llm import get_llm
from app.core.stream import get_stream_context
from app.utils.json_encoder import CustomEncoder


def _basic_stats(data: list[dict], columns: list[str]) -> dict:
    """
    纯 Python 计算基本统计量（不调 LLM）。

    对数值列计算 sum/avg/min/max，对文本列计算唯一值数量，
    并检测极端值（超过均值 ± 2 倍标准差的视为异常）。

    参数:
        data: 查询结果行列表，每行为一个字典
        columns: 列名列表

    返回:
        {
            "row_count": int,
            "numeric_stats": {列名: {"sum": float, "avg": float, "min": float, "max": float}},
            "text_stats": {列名: {"unique_count": int}},
            "outliers": {列名: [异常值列表]},
        }
    """
    numeric_stats: dict = {}
    text_stats: dict = {}
    outliers: dict = {}

    # 识别数值列和文本列
    numeric_cols: list[str] = []
    text_cols: list[str] = []

    for col in columns:
        # 取第一行有效数据判断列类型
        values = [row.get(col) for row in data if row.get(col) is not None]
        if not values:
            # 整列全为空，归为文本列
            text_cols.append(col)
            continue

        sample = values[0]
        if isinstance(sample, (int, float)) and not isinstance(sample, bool):
            numeric_cols.append(col)
        else:
            text_cols.append(col)

    # 对数值列计算统计量
    for col in numeric_cols:
        values = []
        for row in data:
            v = row.get(col)
            if v is not None:
                try:
                    values.append(float(v))
                except (ValueError, TypeError):
                    continue

        if not values:
            continue

        stat = {
            "sum": round(sum(values), 4),
            "avg": round(statistics.mean(values), 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
        }

        # 只有多于 1 个数据点时才计算标准差
        if len(values) > 1:
            stat["std"] = round(statistics.stdev(values), 4)
        else:
            stat["std"] = 0

        numeric_stats[col] = stat

        # 检测极端值（超过均值 ± 2 倍标准差的视为异常）
        if stat["std"] > 0:
            mean = stat["avg"]
            std = stat["std"]
            lower = mean - 2 * std
            upper = mean + 2 * std
            col_outliers = []
            for row in data:
                v = row.get(col)
                if v is not None:
                    try:
                        fv = float(v)
                    except (ValueError, TypeError):
                        continue
                    if fv < lower or fv > upper:
                        col_outliers.append({col: v, "value": fv})
            if col_outliers:
                outliers[col] = col_outliers

    # 对文本列计算唯一值数量
    for col in text_cols:
        unique_values = set()
        for row in data:
            v = row.get(col)
            if v is not None:
                unique_values.add(str(v))
        text_stats[col] = {"unique_count": len(unique_values)}

    return {
        "row_count": len(data),
        "numeric_stats": numeric_stats,
        "text_stats": text_stats,
        "outliers": outliers,
    }


async def analyze_results(
    question: str, sql: str, data: list[dict], columns: list[str]
) -> dict:
    """
    对查询结果做数值统计分析，生成自然语言洞察。

    流程：
    1. 调用 _basic_stats 进行纯 Python 基础统计
    2. 将基础统计结果 + 前 10 行数据 + 用户原始问题发给 LLM
    3. LLM 以数据分析师身份生成洞察、异常，并判断是否适合图表展示

    参数:
        question: 用户原始问题
        sql: 最终执行的 SQL 语句
        data: 查询结果行列表
        columns: 列名列表

    返回:
        {
            "summary": str,           # 数据概览
            "stats": dict,            # 基本统计量
            "insights": list[str],    # 洞察列表
            "anomalies": list[str],   # 异常点
            "chart_suitable": bool,   # 是否适合生成图表（基于实际数据判断）
        }
    """
    # ── 第一步：基础统计（不调 LLM） ──────────────────────
    stats = _basic_stats(data, columns)

    # 构建数据概览摘要
    row_count = stats["row_count"]
    overview_parts = [f"共查询到 {row_count} 条记录"]

    for col_name, col_stat in stats["numeric_stats"].items():
        overview_parts.append(
            f"{col_name} 合计 {col_stat['sum']}，"
            f"均值 {col_stat['avg']}，"
            f"最小值 {col_stat['min']}，"
            f"最大值 {col_stat['max']}"
        )

    summary = "；".join(overview_parts)

    # 如果没有数据，直接返回空结果
    if row_count == 0:
        return {
            "summary": "查询结果为空，未能获取到任何数据。",
            "stats": stats,
            "insights": [],
            "anomalies": [],
            "chart_suitable": False,
        }

    # ── 实时推送基础统计 summary（LLM 调用前填充等待期）──
    ctx = get_stream_context()
    if ctx.queue:
        chunk_size = 3
        for i in range(0, len(summary), chunk_size):
            chunk = summary[i:i + chunk_size]
            await ctx.push_token(chunk)
            # 让出事件循环，确保 token 能被 _forward_tokens 消费
            await asyncio.sleep(0)

    # ── 第二步：LLM 增强分析（实时流式输出 Markdown）─────────
    # 取前 10 行数据供 LLM 参考
    sample_data = data[:10]

    client = get_llm()

    system_prompt = (
        "你是一个专业的数据分析师。"
        "根据提供的查询结果和基础统计信息，生成有价值的数据洞察和异常检测。\n\n"
        "输出格式要求（严格按顺序）：\n"
        "1. 第一行必须是 `[CHART_SUITABLE:true]` 或 `[CHART_SUITABLE:false]`，"
        "   指示数据是否适合用图表展示（≥2行数据且有数值列→true，单行/纯文本→false）\n"
        "2. 之后输出 Markdown 格式的分析文本，按以下结构组织：\n"
        "   - ### 数据概览：用一两句话概括整体情况\n"
        "   - ### 数据洞察：2-5 条具体洞察（排名、占比、趋势等）\n"
        "   - ### 异常关注：数据中的异常点或需要关注的问题\n\n"
        "Markdown 排版要求：\n"
        "- 数值用 **粗体** 强调\n"
        "- 列表用 - 开头的无序列表\n"
        "- 对比数据用 Markdown 表格（| 列1 | 列2 |）\n"
        "- 重点信息用 > 引用块\n\n"
        "严格要求：\n"
        "- 不要使用代码块（```）包裹内容\n"
        "- 直接输出内容，不要有任何前缀说明\n"
        "- chart_suitable 标签必须在第一行，不能省略"
    )

    # 将基础统计格式化为易读字符串
    stats_text = json.dumps(stats, ensure_ascii=False, indent=2)
    sample_text = json.dumps(sample_data, ensure_ascii=False, indent=2, cls=CustomEncoder)

    user_message = (
        f"## 用户问题\n\n{question}\n\n"
        f"## 执行的 SQL\n\n```sql\n{sql}\n```\n\n"
        f"## 基础统计结果\n\n```json\n{stats_text}\n```\n\n"
        f"## 前 {len(sample_data)} 行数据\n\n```json\n{sample_text}\n```\n\n"
        "请分析以上数据，生成洞察和异常检测结果："
    )

    response = await client.chat.completions.create(
        model=settings.LLM_MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0.3,
        stream=True,
    )

    # ── 实时流式收集 LLM 内容，提取 chart_suitable 前缀后立即推送 token ──
    ctx = get_stream_context()
    content_chunks = []
    chart_suitable = row_count >= 2  # 默认值
    prefix_buffer = ""  # 用于收集第一行（chart_suitable 标签）
    prefix_extracted = False  # 是否已从前缀中提取出 chart_suitable
    streaming_active = False  # 是否开始将 token 推送到前端

    async for chunk in response:
        if chunk.choices and chunk.choices[0].delta.content:
            token = chunk.choices[0].delta.content
            content_chunks.append(token)

            if not prefix_extracted:
                # 仍在积累第一行，查找 CHART_SUITABLE 标签
                prefix_buffer += token
                if "\n" in prefix_buffer:
                    # 遇到换行，检查前缀
                    first_line = prefix_buffer.split("\n")[0].strip()
                    if first_line.startswith("[CHART_SUITABLE:"):
                        chart_suitable = "true" in first_line.lower()
                    # 将前缀中换行后的部分推送出去
                    remaining = "\n".join(prefix_buffer.split("\n")[1:])
                    prefix_extracted = True
                    if remaining and ctx.queue:
                        streaming_active = True
                        await ctx.push_token(remaining)
            elif streaming_active and ctx.queue:
                # 实时推送后续所有 token
                await ctx.push_token(token)
            elif ctx.queue:
                # 第一次推送时激活流式输出
                streaming_active = True
                await ctx.push_token(token)

    # 如果整个响应都没有换行（异常情况），回退处理
    if not prefix_extracted and prefix_buffer:
        first_line = prefix_buffer.strip()
        if first_line.startswith("[CHART_SUITABLE:"):
            chart_suitable = "true" in first_line.lower()
            # 去掉标签行，推送剩余内容
            remaining = first_line[first_line.index("]") + 1:].strip()
            if remaining and ctx.queue:
                await ctx.push_token(remaining)
        else:
            # 没有标签，全部当作分析文本推送
            if ctx.queue:
                await ctx.push_token(prefix_buffer)

    raw_content = "".join(content_chunks).strip()

    # 清理可能的 markdown 代码块标记
    if raw_content.startswith("```"):
        lines = raw_content.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw_content = "\n".join(lines).strip()

    # 提取纯分析文本（去除第一行的 chart_suitable 标签）
    analysis_lines = raw_content.split("\n")
    if analysis_lines and analysis_lines[0].strip().startswith("[CHART_SUITABLE:"):
        analysis_text = "\n".join(analysis_lines[1:]).strip()
    else:
        analysis_text = raw_content

    # 如果分析文本为空，使用基础统计 summary 兜底
    if not analysis_text:
        analysis_text = summary

    return {
        "summary": analysis_text,  # 完整的 Markdown 分析文本
        "stats": stats,
        "insights": [],  # 已整合到 summary 文本中，不再单独返回
        "anomalies": [],
        "chart_suitable": chart_suitable,
    }
