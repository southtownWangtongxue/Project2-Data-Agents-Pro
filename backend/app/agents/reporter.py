"""
Reporter Agent - 报表生成专家
根据数据特征推荐图表类型，生成 ECharts JSON 配置
"""
import json

from app.core.config import settings
from app.core.llm import get_llm
from app.core.stream import get_stream_context
from app.utils.json_encoder import CustomEncoder


def _recommend_chart_type(columns: list[str], data: list[dict]) -> str:
    """
    纯规则的基础图表推荐（不调 LLM），作为 LLM 推荐前的默认值。

    规则：
    - 有日期列 + 数值列 → "line"（折线图）
    - 仅分类列 + 数值列 → "bar"（柱状图）
    - 一维分类 + 一维数值 → "pie"（饼图）
    - 双数值列 → "scatter"（散点图）
    - 无法判断时默认返回 "bar"

    参数:
        columns: 列名列表
        data: 查询结果行列表

    返回:
        图表类型字符串，取值为 "line" | "bar" | "pie" | "scatter"
    """
    if not columns or not data:
        return "bar"

    # 识别列类型
    numeric_cols: list[str] = []
    date_cols: list[str] = []
    text_cols: list[str] = []

    # 日期相关的列名关键词
    date_keywords = ["date", "time", "日期", "时间", "year", "month", "day",
                     "年", "月", "日", "created", "updated", "create_time",
                     "update_time", "datetime", "timestamp"]

    for col in columns:
        col_lower = col.lower()
        # 判断是否为日期列（按列名关键词匹配）
        is_date = any(kw in col_lower for kw in date_keywords)
        if is_date:
            date_cols.append(col)
            continue

        # 判断是否为数值列（取第一行非空值判断）
        sample_values = [row.get(col) for row in data if row.get(col) is not None]
        if sample_values and isinstance(sample_values[0], (int, float)):
            numeric_cols.append(col)
        else:
            text_cols.append(col)

    # 按规则推荐图表类型
    if len(date_cols) >= 1 and len(numeric_cols) >= 1:
        # 时间序列 + 数值 → 折线图
        return "line"
    elif len(text_cols) >= 1 and len(numeric_cols) >= 2:
        # 双数值列 → 散点图
        return "scatter"
    elif len(text_cols) >= 1 and len(numeric_cols) == 1:
        # 一维分类 + 一维数值 → 饼图（数据量少时）或柱状图
        if len(data) <= 10:
            return "pie"
        else:
            return "bar"
    elif len(text_cols) >= 1 and len(numeric_cols) >= 1:
        # 分类对比 → 柱状图
        return "bar"
    elif len(numeric_cols) >= 2:
        # 双数值列（无文本列）→ 散点图
        return "scatter"

    # 默认为柱状图
    return "bar"


async def generate_chart_config(
    question: str, data: list[dict], columns: list[str]
) -> dict:
    """
    调用 LLM 分析数据特征，推荐图表类型并生成 ECharts 配置。

    参数:
        question: 用户原始问题
        data: 查询结果行列表
        columns: 列名列表

    返回:
        {
            "chart_type": str,          # "line" | "bar" | "pie" | "scatter"
            "chart_title": str,         # 图表标题
            "echarts_config": dict,     # 完整的 ECharts option JSON 配置
        }
    """
    # ── 步骤 1：规则兜底推荐 ─────────────────────────────
    fallback_type = _recommend_chart_type(columns, data)

    # ── 步骤 2：LLM 生成图表配置 ─────────────────────────
    # 取前 20 行数据供 LLM 分析
    sample_data = data[:20]

    client = get_llm()

    system_prompt = (
        "你是一个专业的 ECharts 报表配置专家。"
        "根据提供给您的查询结果数据，分析数据特征并选择合适的图表类型，"
        "然后生成完整的 ECharts option JSON 配置。\n\n"
        "图表选择规则：\n"
        "- 时间序列 + 数值 → 折线图 (line)\n"
        "- 分类对比 → 柱状图 (bar)\n"
        "- 占比分布 → 饼图 (pie)\n"
        "- 双数值列 → 散点图 (scatter)\n\n"
        "ECharts 配置要求：\n"
        "- 必须包含 title、xAxis、yAxis、series 等基本元素\n"
        "- 饼图无需 xAxis/yAxis\n"
        "- tooltip 和 legend 默认开启\n"
        "- 颜色使用现代简洁风格\n"
        "- 数据点数量超过 15 个的折线图/柱状图建议添加 dataZoom\n\n"
        "严格要求：\n"
        "1. 只返回 JSON 格式，不要包含任何其他文字或 markdown 标记\n"
        "2. 返回的 JSON 必须包含三个字段：chart_type、chart_title、echarts_config\n"
        "3. echarts_config 必须是合法且完整的 ECharts option 对象\n"
        "4. 所有字段使用双引号"
    )

    sample_text = json.dumps(sample_data, ensure_ascii=False, indent=2,cls=CustomEncoder)
    columns_text = json.dumps(columns, ensure_ascii=False)

    user_message = (
        f"## 用户问题\n\n{question}\n\n"
        f"## 数据列名\n\n{columns_text}\n\n"
        f"## 查询结果（前 {len(sample_data)} 行）\n\n```json\n{sample_text}\n```\n\n"
        f"## 规则推荐兜底\n\n{fallback_type}\n\n"
        "请分析数据特征，推荐图表类型并生成 ECharts 配置："
    )

    response = await client.chat.completions.create(
        model=settings.LLM_MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0.2,
        stream=True,
    )

    # 流式收集 LLM 返回内容（不推送到 stream_queue：Reporter 输出 JSON，图表配置由工作流格式化后推送）
    ctx = get_stream_context()
    content_chunks = []
    async for chunk in response:
        if chunk.choices and chunk.choices[0].delta.content:
            token = chunk.choices[0].delta.content
            content_chunks.append(token)
    raw_content = "".join(content_chunks).strip()
    try:
        # 去除可能的 markdown 代码块标记
        if raw_content.startswith("```"):
            lines = raw_content.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw_content = "\n".join(lines).strip()

        llm_result = json.loads(raw_content)
    except json.JSONDecodeError:
        # LLM 返回格式异常时使用规则兜底 + 空配置
        return {
            "chart_type": fallback_type,
            "chart_title": "数据可视化",
            "echarts_config": {},
        }

    return {
        "chart_type": llm_result.get("chart_type", fallback_type),
        "chart_title": llm_result.get("chart_title", "数据可视化"),
        "echarts_config": llm_result.get("echarts_config", {}),
    }


async def generate_excel(
    data: list[dict], columns: list[str], filename: str
) -> bytes:
    """
    生成 Excel (.xlsx) 文件的字节内容。

    参数:
        data: 查询结果行列表
        columns: 列名列表
        filename: 文件名（用于 sheet 标题）

    返回:
        .xlsx 文件的二进制内容
    """
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from datetime import datetime

    wb = Workbook()
    ws = wb.active
    ws.title = filename[:31] or "Sheet1"

    if not columns:
        return b""

    # ── 样式定义 ──────────────────────────────────
    header_fill = PatternFill(start_color="6366F1", end_color="6366F1", fill_type="solid")
    header_font = Font(name="Microsoft YaHei", bold=True, color="FFFFFF", size=11)
    header_align = Alignment(horizontal="center", vertical="center")
    thin_border = Border(
        left=Side(style="thin", color="D1D5DB"),
        right=Side(style="thin", color="D1D5DB"),
        top=Side(style="thin", color="D1D5DB"),
        bottom=Side(style="thin", color="D1D5DB"),
    )
    even_fill = PatternFill(start_color="F3F4F6", end_color="F3F4F6", fill_type="solid")
    data_font = Font(name="Microsoft YaHei", size=10)
    data_align_left = Alignment(horizontal="left", vertical="center")
    data_align_right = Alignment(horizontal="right", vertical="center")

    # ── 写表头 ──────────────────────────────────
    for col_idx, col_name in enumerate(columns, 1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align
        cell.border = thin_border

    # ── 判定数字列 ──────────────────────────────
    numeric_cols: set[int] = set()
    for row_data in data[:100]:
        for col_idx, col_name in enumerate(columns, 1):
            val = row_data.get(col_name)
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                numeric_cols.add(col_idx)

    # ── 写数据行 ─────────────────────────────────
    for row_idx, row_data in enumerate(data, 2):
        is_even = row_idx % 2 == 0
        for col_idx, col_name in enumerate(columns, 1):
            val = row_data.get(col_name)
            if isinstance(val, datetime):
                val = val.strftime("%Y-%m-%d %H:%M:%S")
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.font = data_font
            cell.border = thin_border
            cell.alignment = data_align_right if col_idx in numeric_cols else data_align_left
            if is_even:
                cell.fill = even_fill

    # ── 底部汇总行 ───────────────────────────────
    summary_row = len(data) + 2
    summary_fill = PatternFill(start_color="EEF2FF", end_color="EEF2FF", fill_type="solid")
    summary_cell = ws.cell(row=summary_row, column=1, value=f"共 {len(data)} 条记录")
    summary_cell.font = Font(name="Microsoft YaHei", bold=True, size=10, color="6366F1")
    summary_cell.fill = summary_fill
    summary_cell.border = thin_border

    # ── 自动列宽 ────────────────────────────────
    for col_idx, col_name in enumerate(columns, 1):
        header_width = sum(2 if ord(c) > 127 else 1 for c in str(col_name))
        max_width = header_width
        for row_data in data[:50]:
            val = str(row_data.get(col_name, ""))[:80]
            val_width = sum(2 if ord(c) > 127 else 1 for c in val)
            max_width = max(max_width, val_width)
        ws.column_dimensions[get_column_letter(col_idx)].width = max(10, min(max_width + 4, 40))

    ws.freeze_panes = "A2"

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()
