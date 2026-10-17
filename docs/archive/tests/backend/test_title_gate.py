"""
标题生成器语言门禁测试
弱模型常输出英文标题("The user is ask"),必须被判为不合格并降级。
"""
from app.agents.title_generator import _is_chinese_title


class TestChineseTitleGate:
    def test_chinese_title_valid(self):
        assert _is_chinese_title("上月销售额Top10查询") is True
        assert _is_chinese_title("用户增长与留存分析") is True
        assert _is_chinese_title("助手自我介绍") is True

    def test_english_title_rejected(self):
        assert _is_chinese_title("The user is ask") is False
        assert _is_chinese_title("The user wants") is False
        assert _is_chinese_title("The user said") is False

    def test_empty_rejected(self):
        assert _is_chinese_title("") is False

    def test_mixed_title_accepted(self):
        # 含数字/英文词的正常中文标题应通过
        assert _is_chinese_title("Top10订单统计") is True