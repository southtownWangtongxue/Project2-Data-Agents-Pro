"""
Security Agent - 安全审计专家
对生成的 SQL 进行分类分级：只读语句 → 放行；其余 → 高危

安全模型（deny-by-default）：
    采用「只读白名单」而非「危险黑名单」——黑名单必然存在覆盖盲区，
    任何未显式列入白名单的语句一律判定为高危并触发人工审批。

判定流程：
    1. 按分号拆分多语句（忽略字符串字面量与注释内的分号）
    2. 逐条匹配只读白名单首关键词；任一条不命中 → dangerous
    3. 命中白名单的语句再检查写操作特征（SELECT INTO / OUTFILE / FOR UPDATE…）
    4. 全部通过且无风险信号 → safe；含风险信号时调用 LLM 二次确认（只可升级不可降级）
"""
import json
import re

from app.core.config import settings
from app.core.llm import get_model_name
from app.core.llm import get_llm

# ── 只读白名单：仅这些关键词开头的语句允许放行 ──────────────
# 说明：这是「白名单」而非黑名单。GRANT / EXEC / SET / CALL / MERGE /
#       LOAD_FILE / COPY 等未列入的语句一律判定为高危。
_SAFE_STMT_PATTERN = re.compile(
    r"^\s*"
    r"(SELECT|WITH|SHOW|DESCRIBE|DESC(?!\b\w)|EXPLAIN|VALUES|TABLE)\b",
    re.IGNORECASE,
)

# ── 只读语句内部的写操作特征 ────────────────────────────────
# SELECT ... INTO newtable（SQL Server/PG 建表写操作）
# SELECT ... INTO OUTFILE / DUMPFILE（MySQL 写文件）
# SELECT ... FOR UPDATE / LOCK IN SHARE MODE（加锁，影响并发与一致性）
_WRITE_HINT_PATTERN = re.compile(
    r"\b("
    r"INTO\s+(?:OUTFILE|DUMPFILE)"      # MySQL 导出文件
    r"|\bOUTFILE\b"
    r"|\bDUMPFILE\b"
    r"|\bINTO\b"                        # SELECT INTO 建表/写变量
    r"|\bLOAD_FILE\b"
    r"|\bFOR\s+UPDATE\b"
    r"|\bLOCK\s+IN\s+SHARE\s+MODE\b"
    r")",
    re.IGNORECASE,
)

# ── 风险信号：命中时触发 LLM 二次确认（只可升级为 dangerous）──
_RISK_SIGNAL_PATTERN = re.compile(
    r"\b("
    r"SLEEP|BENCHMARK|PG_SLEEP|DBMS_PIPE|WAITFOR\s+DELAY"
    r"|XP_CMDSHELL|SP_EXECUTESQL|UTL_HTTP|UTL_FILE"
    r"|INFORMATION_SCHEMA\.USER_PRIVILEGES|MYSQL\.USER"
    r")\b",
    re.IGNORECASE,
)

# ── 危险关键词：仅用于生成人类可读的拒绝原因，不参与放行判定 ──
_DANGEROUS_KEYWORDS = (
    "INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER", "CREATE",
    "REPLACE", "GRANT", "REVOKE", "SET", "CALL", "EXEC", "EXECUTE",
    "MERGE", "COPY", "RENAME", "COMMENT", "ANALYZE", "VACUUM", "LOCK",
)

# ── R11 审批档位：风险等级细分（dml 可被 workspace_write 档放行）──
_DML_KEYWORDS = {"INSERT", "UPDATE", "DELETE", "REPLACE", "MERGE"}
_DDL_KEYWORDS = {"DROP", "ALTER", "TRUNCATE", "CREATE", "RENAME", "COMMENT"}


def _risk_level_of_keyword(keyword: str, method: str = "whitelist") -> str:
    """将首关键词映射为风险等级: dml（数据写）/ ddl（结构变更）/ admin（权限/系统）。"""
    kw = keyword.upper()
    if kw in _DML_KEYWORDS:
        return "dml"
    if kw in _DDL_KEYWORDS:
        return "ddl"
    if method == "write-hint":
        return "ddl"
    return "admin"


def split_statements(sql: str) -> list[str]:
    """
    将 SQL 文本按分号拆分为多条语句，忽略字符串字面量与注释内的分号。

    支持的分隔场景：
        - 单引号 / 双引号 / 反引号字符串（含 '' 与 \\ 转义）
        - `--` 与 `#` 行注释、`/* */` 块注释

    参数:
        sql: 原始 SQL 文本

    返回:
        去空白后的语句列表（至少包含一个元素）
    """
    statements: list[str] = []
    buf: list[str] = []
    i, n = 0, len(sql)
    in_single = in_double = in_backtick = False
    in_line_comment = in_block_comment = False

    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""

        # ── 行注释内部 ──
        if in_line_comment:
            buf.append(ch)
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        # ── 块注释内部 ──
        if in_block_comment:
            if ch == "*" and nxt == "/":
                buf.append(ch)
                buf.append(nxt)
                in_block_comment = False
                i += 2
                continue
            buf.append(ch)
            i += 1
            continue

        # ── 字符串字面量内部 ──
        if in_single:
            if ch == "\\" and nxt:                 # 反斜杠转义
                buf.append(ch)
                buf.append(nxt)
                i += 2
                continue
            if ch == "'" and nxt == "'":           # SQL 双写单引号转义
                buf.append(ch)
                buf.append(nxt)
                i += 2
                continue
            if ch == "'":
                in_single = False
            buf.append(ch)
            i += 1
            continue

        if in_double:
            if ch == "\\" and nxt:
                buf.append(ch)
                buf.append(nxt)
                i += 2
                continue
            if ch == '"' and nxt == '"':
                buf.append(ch)
                buf.append(nxt)
                i += 2
                continue
            if ch == '"':
                in_double = False
            buf.append(ch)
            i += 1
            continue

        if in_backtick:
            if ch == "`":
                in_backtick = False
            buf.append(ch)
            i += 1
            continue

        # ── 正常态：识别定界符与注释起始 ──
        if ch == "-" and nxt == "-":
            in_line_comment = True
            buf.append(ch)
            buf.append(nxt)
            i += 2
            continue
        if ch == "#":                              # MySQL 行注释
            in_line_comment = True
            buf.append(ch)
            i += 1
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            buf.append(ch)
            buf.append(nxt)
            i += 2
            continue
        if ch == "'":
            in_single = True
            buf.append(ch)
            i += 1
            continue
        if ch == '"':
            in_double = True
            buf.append(ch)
            i += 1
            continue
        if ch == "`":
            in_backtick = True
            buf.append(ch)
            i += 1
            continue
        if ch == ";":
            statements.append("".join(buf))
            buf = []
            i += 1
            continue

        buf.append(ch)
        i += 1

    statements.append("".join(buf))
    return [s.strip() for s in statements if s.strip()]


def _strip_leading_comments(stmt: str) -> str:
    """去除语句开头的行注释与块注释，便于匹配首关键词。"""
    prev = None
    while prev != stmt:
        prev = stmt
        stmt = re.sub(r"^\s*(--[^\n]*(\n|$))", "", stmt)
        stmt = re.sub(r"^\s*(#[^\n]*(\n|$))", "", stmt)
        stmt = re.sub(r"^\s*/\*.*?\*/", "", stmt, flags=re.DOTALL)
    return stmt.strip()


def _describe_keyword(stmt: str) -> str:
    """提取语句首关键词，用于生成人类可读的拒绝原因。"""
    match = re.match(r"^\s*([A-Za-z_]+)", _strip_leading_comments(stmt))
    return match.group(1).upper() if match else "UNKNOWN"


async def classify_sql(sql: str) -> dict:
    """
    对 SQL 语句进行安全分类，区分只读与写入/修改操作。

    采用 **只读白名单 + deny-by-default** 策略：
        第一步：按分号拆分多语句，逐条匹配只读白名单；任一条不命中即判高危；
        第二步：命中白名单的语句检查写操作特征（INTO / OUTFILE / FOR UPDATE…）；
        第三步：无写特征但含风险信号（SLEEP / XP_CMDSHELL …）时调用 LLM 二次确认，
                LLM 结论**只能升级为高危，不能降级为安全**；
        第四步：全部通过才放行。

    参数:
        sql: 待分类的 SQL 语句字符串

    返回:
        {
            "category": "safe" | "dangerous",
            "method": "whitelist" | "write-hint" | "whitelist+llm",
            "reason": "分类原因描述"
        }
    """
    if not sql or not sql.strip():
        return {
            "category": "dangerous",
            "method": "whitelist",
            "reason": "空语句，按 deny-by-default 判定为高危",
        }

    statements = split_statements(sql)
    risk_level = "admin"   # 默认最高风险档（deny-by-default）

    # ── 第一步：逐条匹配只读白名单（deny-by-default）──────────
    for stmt in statements:
        if not _SAFE_STMT_PATTERN.match(_strip_leading_comments(stmt)):
            keyword = _describe_keyword(stmt)
            risk_level = _risk_level_of_keyword(keyword)
            hint = (
                f"{keyword} 命中已知高危关键词"
                if keyword in _DANGEROUS_KEYWORDS
                else f"语句首关键词 {keyword} 不在只读白名单"
                f"(SELECT/WITH/SHOW/DESCRIBE/DESC/EXPLAIN/VALUES/TABLE) 内"
            )
            return {
                "category": "dangerous",
                "risk_level": risk_level,
                "method": "whitelist",
                "reason": (
                    f"{hint}，按 deny-by-default 判定为高危，"
                    "触发 Human-in-the-loop 审批流程"
                ),
            }

    # ── 第二步：检查只读语句内的写操作特征 ────────────────────
    for stmt in statements:
        hint = _WRITE_HINT_PATTERN.search(stmt)
        if hint:
            return {
                "category": "dangerous",
                "risk_level": "ddl",
                "method": "write-hint",
                "reason": (
                    f"只读语句中检测到写操作特征 '{hint.group(1).strip()}'"
                    f"（SELECT INTO / OUTFILE / 加锁等），判定为高危，"
                    "触发 Human-in-the-loop 审批流程"
                ),
            }

    # ── 第三步：风险信号 → LLM 二次确认（只可升级不可降级）────
    if _RISK_SIGNAL_PATTERN.search(sql):
        llm_result = await _llm_confirm_sql(sql)
        if llm_result.get("category") != "safe":
            return {
                "category": "dangerous",
                "method": "whitelist+llm",
                "reason": (
                    f"检测到风险信号（耗时/命令执行/权限表访问），"
                    f"LLM 二次确认: {llm_result.get('reason', '无补充说明')}，"
                    "触发 Human-in-the-loop 审批流程"
                ),
            }
        return {
            "category": "safe",
            "risk_level": "read",
            "method": "whitelist+llm",
            "reason": f"命中只读白名单且 LLM 二次确认安全: {llm_result.get('reason', '')}",
        }

    # ── 第四步：全部通过 → 放行 ──────────────────────────────
    keywords = sorted({_describe_keyword(s) for s in statements})
    return {
        "category": "safe",
        "risk_level": "read",
        "method": "whitelist",
        "reason": f"全部 {len(statements)} 条语句命中只读白名单: {', '.join(keywords)}",
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
