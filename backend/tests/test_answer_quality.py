"""答案质量检测器(两臂共用纯函数,TDD)。

两个指标:
1. 数据接地(grounding):答案里出现的数字必须能在本轮 tool_result 数据中找到;
   直接量必须逐字命中,派生量(百分比/合计/差值/倍数)允许由数据算出,
   并在明细里列出派生路径供人工复核。
2. 分析维度(dimensions):判定"命中 = 出现了该维度的分析行为",不是出现关键词。
   例如「sessions 是 events 的 12 倍」算对比,「还有 sessions 和 events 两个表」
   只是并列列举,不算。

定位:预筛 + 人工复核,不作为全自动门禁(准确率有限);宁可漏判不可误判。
"""
import pytest

from app.core.answer_quality import (
    check_dimensions,
    check_grounding,
    extract_numbers,
    parse_tool_results,
)


# ── 指标 1:数据接地 ──────────────────────────────────────────

def test_direct_value_grounded():
    rows = parse_tool_results(['{"row_count": 883, "table": "session_events"}'])
    rep = check_grounding("session_events 有 883 条记录", rows)
    assert rep["grounded"] is True
    assert rep["ungrounded"] == []


def test_hallucinated_value_flagged():
    rows = parse_tool_results(['{"row_count": 883}'])
    rep = check_grounding("session_events 有 9999 条记录", rows)
    assert rep["grounded"] is False
    assert 9999 in rep["ungrounded"]


def test_suffix_and_unit_forms_match():
    """同一数值带单位后缀/括注时都要能对上(不因装饰失配)。

    百分比属派生量,由 test_percentage_is_derived_and_path_listed 单独覆盖。
    """
    rows = parse_tool_results(['{"row_count": 883}'])
    for text in ("共 883 条", "共 883 条（单位：条）", "883"):
        assert check_grounding(text, rows)["grounded"] is True, text


def test_percentage_is_derived_and_path_listed():
    """百分比是派生量:允许由数据算出,且派生路径要列出供复核。"""
    rows = parse_tool_results(['{"a": 883, "b": 1107}'])
    rep = check_grounding("a 占 b 的 80%", rows)
    assert rep["grounded"] is True
    assert any(d["kind"] == "derived" for d in rep["details"]), rep["details"]


def test_sum_is_derived():
    rows = parse_tool_results(['{"a": 100, "b": 50}'])
    rep = check_grounding("合计 150 条", rows)
    assert rep["grounded"] is True
    assert any(d["kind"] == "derived" and d["op"] == "sum" for d in rep["details"])


def test_no_tool_results_means_cannot_judge():
    """没采集到工具结果时不得判为通过(避免无据放行)。"""
    rep = check_grounding("答案里有 42", [])
    assert rep["grounded"] is False
    assert rep["reason"] == "no_tool_results"


def test_ignore_years_and_small_integers():
    """年份、序号等小整数不算数据声明,否则噪声淹没真幻觉。"""
    rows = parse_tool_results(['{"row_count": 883}'])
    rep = check_grounding("2026 年的数据,步骤 1 和 2", rows)
    assert rep["ungrounded"] == []


# ── 指标 2:分析维度(命中=分析行为)──────────────────────────

def test_comparison_requires_relation_not_listing():
    rows = parse_tool_results(['{"sessions": 110, "events": 883}'])
    hit = check_dimensions("sessions 是 events 的 8 倍", rows)
    assert "对比" in hit["hit"]
    # 并列列举不算对比
    no_hit = check_dimensions("还有 sessions 和 events 两个表", rows)
    assert "对比" not in no_hit["hit"]


def test_proportion_dimension():
    rows = parse_tool_results(['{"small": 20, "total": 100}'])
    hit = check_dimensions("small 占 total 的 20%", rows)
    assert "构成" in hit["hit"]


def test_trend_dimension():
    rows = parse_tool_results(['{"day": "2026-10-13", "n": 3}, {"day": "2026-10-14", "n": 9}'])
    hit = check_dimensions("从 3 增长到 9,呈上升趋势", rows)
    assert "趋势" in hit["hit"]


def test_ranking_dimension():
    rows = parse_tool_results(['{"t": "a", "n": 3}, {"t": "b", "n": 9}'])
    hit = check_dimensions("b 以 9 条居首,a 只有 3 条", rows)
    assert "排名" in hit["hit"]


def test_no_dimension_when_only_listing():
    rows = parse_tool_results(['{"t": "a", "n": 3}, {"t": "b", "n": 9}'])
    assert check_dimensions("共 2 张表:a 有 3 条,b 有 9 条", rows)["hit"] == []


def test_count_of_hit_dimensions():
    rows = parse_tool_results([
        '{"sessions": 110, "events": 883}', '{"day": "d1", "n": 3}', '{"day": "d2", "n": 9}',
    ])
    rep = check_dimensions("events 是 sessions 的 8 倍;从 3 涨到 9,呈上升趋势", rows)
    assert rep["count"] >= 2
