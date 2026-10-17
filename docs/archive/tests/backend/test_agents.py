"""
Agent 单元测试
"""
import pytest
from app.agents.security import mask_sensitive_data, classify_sql
from app.agents.rag_agent import retrieve_knowledge
from app.agents.sql_coder import execute_sql
from tests.fakes import FakeCursorResult, FakeEngine


class TestSecurityAgent:
    """Security Agent 测试"""

    def test_mask_phone(self):
        """测试手机号脱敏"""
        data = [{"phone": "13812345678"}]
        result = mask_sensitive_data(data)
        assert result[0]["phone"] == "138****5678"

    def test_mask_id_card(self):
        """测试身份证脱敏"""
        data = [{"id_card": "320102199001011234"}]
        result = mask_sensitive_data(data)
        assert "****" in result[0]["id_card"]
        assert result[0]["id_card"].startswith("320")
        assert result[0]["id_card"].endswith("1234")

    def test_mask_email(self):
        """测试邮箱脱敏"""
        data = [{"email": "user@example.com"}]
        result = mask_sensitive_data(data)
        assert "***" in result[0]["email"]
        assert result[0]["email"].endswith("@example.com")

    def test_mask_multiple_fields(self):
        """测试多字段、多行脱敏"""
        data = [
            {"name": "张三", "phone": "13900001111", "email": "zhangsan@test.com"},
            {"name": "李四", "id_card": "110101198001015678"},
        ]
        result = mask_sensitive_data(data)
        assert result[0]["phone"] == "139****1111"
        assert result[0]["email"] == "z***@test.com"
        assert "****" in result[1]["id_card"]

    def test_empty_data(self):
        """测试空数据"""
        assert mask_sensitive_data([]) == []

    def test_no_sensitive_data(self):
        """测试无敏感字段的数据"""
        data = [{"name": "产品A", "price": 99.9}]
        result = mask_sensitive_data(data)
        assert result == data


class TestClassifySQL:
    """SQL 分类测试（正则层，不调 LLM）"""

    @pytest.mark.asyncio
    async def test_select_is_safe(self):
        """SELECT 语句应为安全"""
        result = await classify_sql("SELECT * FROM orders")
        assert result["category"] == "safe"

    @pytest.mark.asyncio
    async def test_insert_is_dangerous(self):
        """INSERT 语句应为危险

        安全红线「写必批」：正则层 deny-by-default 已足以判定危险，
        断言必须是严格等于 dangerous —— 早期版本写成
        `in ("safe", "dangerous")` 属恒真断言，无法拦截回归。
        """
        result = await classify_sql("INSERT INTO orders VALUES (1, 'test')")
        assert result["category"] == "dangerous"

    @pytest.mark.asyncio
    async def test_delete_is_dangerous(self):
        """DELETE 语句应为危险"""
        result = await classify_sql("DELETE FROM orders WHERE id = 1")
        assert result["category"] == "dangerous"

    @pytest.mark.asyncio
    async def test_show_is_safe(self):
        """SHOW 语句应为安全"""
        result = await classify_sql("SHOW TABLES")
        assert result["category"] == "safe"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT * FROM t; DROP TABLE users",          # 多语句注入
            "GRANT ALL ON *.* TO 'hacker'@'%'",           # 权限变更
            "EXEC xp_cmdshell('rm -rf /')",               # 命令执行
            "SELECT * INTO newtable FROM old",            # SELECT INTO 写表
            "UPDATE users SET role='admin'",              # 越权更新
            "DROP TABLE users",                            # 结构变更
        ],
    )
    async def test_dangerous_sql_variants(self, sql: str):
        """各类写类/危险 SQL 必须被判定为 dangerous（含历史绕过样本）"""
        result = await classify_sql(sql)
        assert result["category"] == "dangerous", f"未拦截: {sql}"


class TestRAGAgent:
    """RAG Agent 测试（不依赖 Milvus，验证降级行为）"""

    @pytest.mark.asyncio
    async def test_retrieve_empty_query(self):
        """空查询应返回空字符串"""
        result = await retrieve_knowledge("")
        assert result == ""

    @pytest.mark.asyncio
    async def test_retrieve_whitespace_query(self):
        """仅空白查询应返回空字符串"""
        result = await retrieve_knowledge("   ")
        assert result == ""

    @pytest.mark.asyncio
    async def test_retrieve_no_milvus_graceful_degradation(self):
        """Milvus 不可用时应优雅降级返回空字符串（不抛异常）"""
        result = await retrieve_knowledge("如何使用数据查询？")
        # 无 Milvus 环境，应优雅降级返回空字符串
        assert isinstance(result, str)
        # 不应包含异常信息
        assert "Traceback" not in result


class TestExecuteSql:
    """execute_sql 结果形态测试(替身契约见 tests/fakes.py,经真库校准)"""

    @pytest.mark.asyncio
    async def test_zero_row_select_returns_empty_data(self):
        """零行 SELECT 必须返回 data=[],不得伪装成 affected_rows 单行

        旧行为缺陷:零行 SELECT 落入 affected_rows 分支,下游 run_sql
        呈现 row_count=1,模型会误以为查到了一行数据(交接文档 §4.3 遗留)。
        """
        engine = FakeEngine(FakeCursorResult(returns_rows=True, rows=[], columns=["v"]))
        result = await execute_sql(engine, "SELECT v FROM t WHERE 1=0")
        assert result["success"] is True
        assert result["data"] == []

    @pytest.mark.asyncio
    async def test_nonempty_select_returns_row_dicts(self):
        """非空 SELECT 返回「每行一个 dict」形态(既有契约,回归保护)"""
        engine = FakeEngine(
            FakeCursorResult(returns_rows=True, rows=[(1,), (2,)], columns=["v"])
        )
        result = await execute_sql(engine, "SELECT v FROM t")
        assert result["success"] is True
        assert result["data"] == [{"v": 1}, {"v": 2}]

    @pytest.mark.asyncio
    async def test_dml_returns_affected_rows_row(self):
        """DML 无结果集,返回 affected_rows 元信息行(既有契约,回归保护)"""
        engine = FakeEngine(FakeCursorResult(returns_rows=False, rowcount=3))
        result = await execute_sql(engine, "UPDATE t SET a=1")
        assert result["success"] is True
        assert result["data"] == [{"affected_rows": 3}]
