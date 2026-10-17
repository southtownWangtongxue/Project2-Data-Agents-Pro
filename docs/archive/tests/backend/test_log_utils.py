"""log_utils 双风格日志门面测试。

背景:全库 120 处调用按 stdlib logging 习惯写 printf 风格
(log.warning("x %s", val)),而 log 是 loguru(只做 str.format)——值被
静默丢弃,只打印字面 %s。[SqlGate] 安全审计日志与 [Shadow] 失败原因
均中招(排查 nemotron 补采失败时实测:异常详情完全不可见)。
门面方案:log_utils 一处修复全部调用点,printf/{} 两种风格都正确。
"""
import pytest

from app.utils.log_utils import log


@pytest.fixture
def captured():
    messages: list[str] = []
    sink_id = log.add(messages.append)
    yield messages
    log.remove(sink_id)


def test_printf_style_args_formatted(captured):
    """printf 占位符的参数必须被格式化进消息,不得打印字面 %s"""
    log.warning("[SqlGate] run_sql 决策=%s category=%s risk=%s", "ask", "write", "high")
    assert "[SqlGate] run_sql 决策=ask category=write risk=high" in captured[0]
    assert "%s" not in captured[0]


def test_printf_float_and_escape_percent(captured):
    """浮点占位符与 %% 转义按 printf 语义格式化"""
    log.info("占比 %.1f%% 阈值 %s", 81.55, "80%")
    assert "占比 81.5% 阈值 80%" in captured[0]


def test_loguru_brace_style_still_works(captured):
    """loguru 原生 {} 风格不受门面影响"""
    log.info("用户: {} 模式: {}", "shadow", "data")
    assert "用户: shadow 模式: data" in captured[0]


def test_plain_message_passthrough(captured):
    """无参数消息原样通过(含字面百分号,不做格式化)"""
    log.warning("接地率 81.55% 观察期已过")
    assert "接地率 81.55% 观察期已过" in captured[0]


def test_exception_instance_as_arg(captured):
    """异常对象作为参数时,其文本进入消息([Shadow] 失败原因场景)"""
    log.warning("[Shadow] 比对执行失败(已忽略): %s", ValueError("上游 DEGRADED"))
    assert "[Shadow] 比对执行失败(已忽略): 上游 DEGRADED" in captured[0]


def test_arg_count_mismatch_does_not_raise(captured):
    """占位符与参数数不匹配时退回原样输出,绝不在日志层抛错"""
    log.info("只有 %s 个占位", 1, "多余参数")  # noqa: LOG001
    assert "只有 %s 个占位" in captured[0]


def test_levels_route_to_loguru(captured):
    """门面方法路由到 loguru 对应级别(抽查 error/exception)"""
    log.error("错误 %s", "E1")
    assert "错误 E1" in captured[-1]
    assert any("级别" not in m for m in captured)  # 无泄漏的原始对象
