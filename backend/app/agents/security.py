"""
Security Agent - 安全审计专家
对生成的 SQL 进行分类分级：SELECT → 放行；INSERT/UPDATE/DELETE/DROP/ALTER → 高危
使用正则表达式 + LLM 双重校验，确保数据安全
"""
import json
import re

from app.core.config import settings
from app.core.llm import get_model_name
from app.core.llm import get_llm

# ── 正则分类模式 ────────────────────────────────────
# 匹配 SQL 语句开头关键词，忽略前导空白与注释
_SAFE_PATTERN = re.compile(
    r"^\s*"
    r"(?!--\s|/\*)"  # 忽略以注释开头的行
    r"(SELECT|SHOW|DESCRIBE|DESC(?!\b\w)|EXPLAIN)\b",
    re.IGNORECASE,
)

_DANGEROUS_PATTERN = re.compile(
    r"^\s*"
    r"(?!--\s|/\*)"  # 忽略以注释开头的行
    r"(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|REPLACE)\b",
    re.IGNORECASE,
)


async def classify_sql(sql: str) -> dict:
    """
    对 SQL 语句进行安全分类，区分只读与写入/修改操作。

    采用双检策略：
    第一步：正则快速检测，根据 SQL 前缀关键词做初步分类；
    第二步：若正则判定为危险，调用 LLM 进行语义级二次确认；
    第三步：综合双检结果，采用保守策略（宁可误拦，不可漏放）。

    参数:
        sql: 待分类的 SQL 语句字符串

    返回:
        {
            "category": "safe" | "dangerous",
            "method": "regex" | "regex+llm",
            "reason": "分类原因描述"
        }
    """
    # ── 第一步：正则快速分类 ─────────────────────────
    safe_match = _SAFE_PATTERN.match(sql)
    dangerous_match = _DANGEROUS_PATTERN.match(sql)

    if safe_match and not dangerous_match:
        # 明确的安全操作
        keyword = safe_match.group(1).upper()
        return {
            "category": "safe",
            "method": "regex",
            "reason": f"正则匹配到安全关键词: {keyword}，判定为只读查询",
        }

    if dangerous_match:
        keyword = dangerous_match.group(1).upper()
        regex_category = "dangerous"
        # ── 第二步：LLM 语义级二次确认 ────────────────
        llm_result = await _llm_confirm_sql(sql)

        # ── 第三步：综合裁决 ──────────────────────────
        # 保守策略：正则判定为危险时，若 LLM 也认为是危险，则采纳；
        # 若 LLM 认为是安全，仍以正则结果为准（宁可误拦不可漏放）；
        # 实际应用中可在此触发 Human-in-the-loop 审批流程。
        if llm_result.get("category") == "dangerous":
            return {
                "category": "dangerous",
                "method": "regex+llm",
                "reason": (
                    f"正则匹配到危险关键词: {keyword}（{regex_category}），"
                    f"LLM 二次确认: {llm_result.get('reason', '无补充说明')}，"
                    "触发 Human-in-the-loop 审批流程"
                ),
            }
        else:
            # LLM 虽认为是安全操作，但正则已拦截，维持保守裁决
            return {
                "category": "dangerous",
                "method": "regex+llm",
                "reason": (
                    f"正则匹配到危险关键词: {keyword}（{regex_category}），"
                    f"LLM 判定为安全但采用保守策略，维持危险标记。"
                    f"LLM 理由: {llm_result.get('reason', '无补充说明')}，"
                    "触发 Human-in-the-loop 审批流程"
                ),
            }

    # 未匹配到任何已知关键词，默认放行（偏保守的安全侧）
    return {
        "category": "safe",
        "method": "regex",
        "reason": "未匹配到已知危险关键词，默认放行",
    }


async def _llm_confirm_sql(sql: str) -> dict:
    """
    调用 LLM 对 SQL 语句进行语义级安全判断。

    要求 LLM 只返回 JSON 对象，包含 category 与 reason 两个字段。

    参数:
        sql: 待确认的 SQL 语句

    返回:
        解析后的字典，含 "category" 和 "reason"；
        解析失败时返回保守的危险判定。
    """
    client = get_llm()

    system_prompt = (
        "你是一个数据库安全审计专家。"
        "请判断以下 SQL 语句是否会修改数据库中的数据（包括写入、更新、删除、表结构变更等）。\n\n"
        "严格要求：\n"
        "1. 只返回一个 JSON 对象，不要包含任何其他文字\n"
        "2. JSON 格式为: {\"category\": \"safe\" 或 \"dangerous\", \"reason\": \"简要判断理由\"}\n"
        "3. safe 表示该 SQL 只读数据，不会造成任何数据变更\n"
        "4. dangerous 表示该 SQL 会写入、修改、删除数据或变更表结构\n"
        "5. 注意区分：SHOW、DESCRIBE、EXPLAIN 等命令属于 safe"
    )

    try:
        response = await client.chat.completions.create(
            model=get_model_name(),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请审计以下 SQL：\n\n{sql}"},
            ],
            temperature=0.0,
        )

        content = response.choices[0].message.content.strip()
        # 尝试从 markdown 代码块中提取 JSON
        if content.startswith("```"):
            content = _extract_json_from_markdown(content)
        return json.loads(content)

    except (json.JSONDecodeError, Exception):
        # LLM 返回解析失败，返回保守的危险判定
        return {
            "category": "dangerous",
            "reason": "LLM 响应解析失败，默认标记为危险",
        }


def _extract_json_from_markdown(text: str) -> str:
    """
    从 markdown 代码块中提取 JSON 内容。

    参数:
        text: 可能包含 markdown 标记的文本

    返回:
        提取后的纯 JSON 字符串
    """
    lines = text.split("\n")
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def mask_sensitive_data(data: list[dict]) -> list[dict]:
    """
    对查询结果中的敏感字段进行脱敏处理。

    支持的脱敏规则：
    - 手机号 (11 位, 1 开头)：保留前 3 后 4，如 138****1234
    - 身份证号 (18 位或 15 位)：保留前 3 后 4，如 320***********1234
    - 邮箱：保留首字母与域名，如 u***@domain.com

    参数:
        data: 查询结果行列表，每行为一个字典

    返回:
        脱敏后的数据列表（原位修改，同时返回）
    """
    if not data:
        return data

    # 正则模式：手机号、身份证号、邮箱
    patterns = [
        (re.compile(r"\b1[3-9]\d{9}\b"), _mask_phone),           # 手机号
        (re.compile(r"\b\d{15}(?:\d{2}[\dXx])?\b"), _mask_id_card),  # 身份证
        (re.compile(r"\b[\w.\-]+@[\w\-]+\.\w{2,}\b"), _mask_email),  # 邮箱
    ]

    # 遍历所有行
    for row in data:
        for key, value in row.items():
            if not isinstance(value, str):
                continue
            for pattern, mask_func in patterns:
                if pattern.search(value):
                    row[key] = pattern.sub(mask_func, value)

    return data


def _mask_phone(match: re.Match) -> str:
    """
    手机号脱敏：138****1234（保留前 3 后 4）。

    参数:
        match: 正则匹配对象

    返回:
        脱敏后的字符串
    """
    phone = match.group()
    if len(phone) == 11:
        return f"{phone[:3]}****{phone[-4:]}"
    return phone


def _mask_id_card(match: re.Match) -> str:
    """
    身份证号脱敏：320***********1234（保留前 3 后 4）。

    参数:
        match: 正则匹配对象

    返回:
        脱敏后的字符串
    """
    id_num = match.group()
    length = len(id_num)
    if length in (15, 18):
        masked_length = length - 7  # 减去前 3 和后 4
        return f"{id_num[:3]}{'*' * masked_length}{id_num[-4:]}"
    return id_num


def _mask_email(match: re.Match) -> str:
    """
    邮箱脱敏：u***@domain.com（保留用户名首字母，隐藏其余部分）。

    参数:
        match: 正则匹配对象

    返回:
        脱敏后的字符串
    """
    email = match.group()
    local_part, domain = email.split("@", 1)
    if len(local_part) <= 1:
        return f"{local_part}***@{domain}"
    return f"{local_part[0]}***@{domain}"
