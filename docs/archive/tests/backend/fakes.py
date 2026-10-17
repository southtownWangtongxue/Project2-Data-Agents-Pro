"""测试替身:最小 async Engine/Conn/CursorResult,契约经真库探针校准。

2026-10-16 于 business_db(asyncmy)实测:
- SELECT 非空: returns_rows=True, fetchall() 返回行, keys() 返回列名
- SELECT 零行: returns_rows=True, fetchall()=[], rowcount=0
- DML:        returns_rows=False, rowcount=影响行数, fetchall() 抛 ResourceClosedError
"""
from sqlalchemy.exc import ResourceClosedError


class FakeCursorResult:
    """模仿 asyncmy 驱动的 CursorResult(仅 execute_sql 用到的成员)。"""

    def __init__(self, *, returns_rows: bool, rows: list | None = None,
                 columns: list | None = None, rowcount: int = 0):
        self.returns_rows = returns_rows
        self._rows = rows or []
        self._columns = columns or []
        self.rowcount = rowcount

    def fetchall(self):
        if not self.returns_rows:
            raise ResourceClosedError("This result object is closed.")
        return self._rows

    def keys(self):
        return self._columns


class FakeConnection:
    """模仿 AsyncConnection:execute 恒返回预置结果,commit 空操作。"""

    def __init__(self, result: FakeCursorResult):
        self._result = result

    async def execute(self, stmt):
        return self._result

    async def commit(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class FakeEngine:
    """模仿 AsyncEngine:connect() 返回可用作 async 上下文的假连接。"""

    def __init__(self, result: FakeCursorResult):
        self._conn = FakeConnection(result)

    def connect(self):
        return self._conn
