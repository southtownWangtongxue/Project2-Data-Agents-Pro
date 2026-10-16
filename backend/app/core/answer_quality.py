"""答案质量检测器(两臂共用纯函数)。

**为什么两臂共用**:Phase 2 门禁要求"结果可用率 ≥ legacy",前提是两臂用同一把
尺子;尺子只装在 Harness 侧等于没门禁。判定逻辑必须只有一份,否则下一步就会
面对"两把尺子悄悄漂移"——这正是本轮反复出现的环境不一致坑的又一个变体。

两个指标:
1. 数据接地(grounding):答案里的数字必须能在本轮 tool_result 数据中找到。
   - 直接量:逐字命中(容忍单位后缀/百分号/千分位)
   - 派生量:百分比、合计、差值、倍数——允许由数据算出,并在明细里给出
     派生路径(op + 参与计算的值)供人工复核
   - 判定位:预筛 + 人工复核。宁可漏判不可误判,故无法判定时判不通过
     (如没有工具结果),不无据放行。
2. 分析维度(dimensions):判定"出现了该维度的分析行为",而非出现关键词。
   对比要求两实体间存在量级关系(倍数/比/高低),并列列举不算。

report 模式的维度口径(摘要/证据链/建议)暂不定义:影子采集目前只有 data 类
样本,先定会变成拍出来的标准;等 report 开始采集时按同一套流程补。
"""
from __future__ import annotations

import json
import re
from typing import Any

# 答案中不算"数据声明"的数字:年份、步骤序号
_YEAR_RE = re.compile(r"(19|20)\d{2}")
_STEP_RE = re.compile(r"(步骤|Step|第)\s*\d+", re.I)

_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")

# 维度判定用的关系词:必须蕴含"两实体量级比较",并列列举不算。
# 刻意不含"分别是"/"两个"这类纯列举词——否则"还有 A 和 B 两个表"会被误判为对比。
_RELATION_WORDS = (
    "倍", "占比", "高于", "低于", "多于", "少于", "超过", "不到",
    "相比", "较之", "对比",
)
_TREND_WORDS = ("趋势", "上升", "下降", "增长", "减少", "环比", "同比", "逐日", "每天", "波动")
_RANK_WORDS = ("居首", "最高", "最低", "最多", "最少", "排名", "位列", "第一", "垫底")
_PROPORTION_WORDS = ("占比", "占 ", "构成", "比重")
_ANOMALY_WORDS = ("异常", "突增", "骤降", "为零", "为 0", "为空", "远低于", "远高于")


def _to_float(token: Any) -> float | None:
    try:
        return float(str(token).replace(",", ""))
    except (TypeError, ValueError):
        return None


def extract_numbers(text: str, min_int: int = 10) -> list[float]:
    """抽取答案中的数值(去重、排除年份/步骤号)。

    min_int:小于该值的整数视为序号噪声并排除——但**维度判定必须传 1**,
    因为"从 3 涨到 9"里的 3/9 恰恰是趋势与排名的证据(接地判定才需要降噪)。
    """
    if not text:
        return []
    cleaned = _STEP_RE.sub(" ", _YEAR_RE.sub(" ", text))
    out: list[float] = []
    for raw in _NUM_RE.findall(cleaned):
        val = _to_float(raw)
        if val is None:
            continue
        if val == int(val) and val < min_int:
            continue
        if val not in out:
            out.append(val)
    return out


def parse_tool_results(tool_result_contents: list[str]) -> list[float]:
    """把本轮 tool_result 载荷解析成扁平数值集合(两臂通用)。

    载荷可能是 run_sql 的 JSON 或普通文本;递归收集所有数值。
    """
    values: list[float] = []

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for v in node.values():
                _walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                _walk(v)
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            values.append(float(node))
        elif isinstance(node, str):
            for raw in _NUM_RE.findall(node):
                val = _to_float(raw)
                if val is not None:
                    values.append(val)

    for raw in tool_result_contents or []:
        if raw is None or raw == "":
            continue
        text = str(raw)
        try:
            _walk(json.loads(text))
        except (json.JSONDecodeError, TypeError):
            _walk(text)
    return values


def _derive(answer_vals: list[float], data_vals: list[float]) -> list[dict]:
    """用数据算出答案里的派生量(百分比/倍数/合计),给出可复核的派生路径。

    只认可复核的简单算术;派生不出来即视为未接地(不猜)。
    """
    derived: list[dict] = []
    uniq = sorted(set(data_vals))
    if not uniq:
        return derived

    def _close(a: float, b: float, rel: float = 0.01) -> bool:
        return abs(a - b) <= max(0.01, abs(b) * rel)

    for val in answer_vals:
        hit = None
        # 百分比:a/b*100 ≈ val
        for a in uniq:
            for b in uniq:
                if b and _close(a / b * 100, val, 0.02):
                    hit = {"value": val, "kind": "derived", "op": "pct", "part": a, "whole": b}
                    break
            if hit:
                break
        if hit:
            derived.append(hit)
            continue
        # 倍数:a/b ≈ val
        for a in uniq:
            for b in uniq:
                if b and _close(a / b, val):
                    hit = {"value": val, "kind": "derived", "op": "ratio", "part": a, "whole": b}
                    break
            if hit:
                break
        if hit:
            derived.append(hit)
            continue
        # 合计:N 个数之和(实测 5 张表行数求和,仅两数相加不够)
        if len(uniq) >= 2:
            acc = uniq[0]
            for nxt in uniq[1:]:
                if _close(acc + nxt, val):
                    hit = {"value": val, "kind": "derived", "op": "sum",
                           "part": acc, "part2": nxt}
                    break
                acc += nxt
        if hit:
            derived.append(hit)
            continue
        # 均值:总和 / 个数
        if len(uniq) >= 2:
            total = sum(uniq)
            if _close(total / len(uniq), val, 0.02):
                derived.append({"value": val, "kind": "derived", "op": "mean",
                                "part": total, "whole": float(len(uniq))})
    return derived


def check_grounding(answer: str, tool_result_contents: list[str]) -> dict:
    """指标 1:答案数值是否能在工具数据中找到(直接量或可复核的派生量)。

    返回 {"grounded", "ungrounded", "details", "reason", "checked"}。
    无工具结果时判不通过(reason=no_tool_results)——不无据放行。
    """
    data_vals = parse_tool_results(tool_result_contents)
    if not data_vals:
        return {"grounded": False, "ungrounded": [], "details": [],
                "reason": "no_tool_results", "checked": 0}

    answer_vals = extract_numbers(answer)
    derived_all = _derive(answer_vals, data_vals)
    derived_values = {d["value"] for d in derived_all}

    ungrounded: list[float] = []
    details: list[dict] = []
    for val in answer_vals:
        if any(abs(d - val) <= 0.01 for d in data_vals):
            details.append({"value": val, "kind": "direct"})
        elif val in derived_values:
            continue  # 已在 derived_all 记录派生路径
        else:
            ungrounded.append(val)

    return {
        "grounded": not ungrounded,
        "ungrounded": ungrounded,
        "details": details + derived_all,
        "reason": "" if not ungrounded else "ungrounded_values",
        "checked": len(answer_vals),
    }


def check_dimensions(answer: str, tool_result_contents: list[str]) -> dict:
    """指标 2:答案出现了哪些分析维度(命中=分析行为,非关键词罗列)。

    data 模式口径:对比 / 趋势 / 构成 / 异常 / 排名。定位为预筛,最终由人工复核。
    """
    text = answer or ""
    # 维度判定用宽松取数:小整数(3、9)恰恰是趋势/排名的证据,不能当噪声滤掉
    nums = extract_numbers(text, min_int=1)
    hit: list[str] = []

    if _has_relation(text) and nums:
        hit.append("对比")
    if any(w in text for w in _PROPORTION_WORDS) and nums:
        hit.append("构成")
    if any(w in text for w in _TREND_WORDS) and len(nums) >= 2:
        hit.append("趋势")
    if any(w in text for w in _RANK_WORDS) and nums:
        hit.append("排名")
    if any(w in text for w in _ANOMALY_WORDS) and nums:
        hit.append("异常")

    return {
        "hit": hit,
        "count": len(hit),
        "data_refs": len(parse_tool_results(tool_result_contents)),
    }


def _has_relation(text: str) -> bool:
    return any(w in text for w in _RELATION_WORDS)