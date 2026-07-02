# 接入新数据库

DataAgent Pro 的核心设计原则之一：**新增数据库方言仅需配置，无需修改 Agent 核心代码**。本文档说明如何接入新的业务数据库或新增数据库方言。

---

## 数据库方言支持

当前支持的四种数据库方言：

| 方言 | 标识 | 驱动 | 最低版本 |
|------|------|------|---------|
| MySQL | `mysql` | pymysql / mysqlclient | 5.7+ |
| PostgreSQL | `postgresql` | psycopg2 | 12+ |
| SQL Server | `sqlserver` | pyodbc | 2017+ |
| Oracle | `oracle` | cx_Oracle | 19c+ |

---

## 接入已有方言的新数据库实例

如果你的新数据库属于上述四种方言之一，只需配置 `.env` 和 Docker Compose 即可。

### 步骤一：配置 .env

```ini
# 新增一个业务数据库（例如：CRM 系统用的 MySQL）
CRM_DB_HOST=192.168.1.100
CRM_DB_PORT=3306
CRM_DB_USER=readonly_user
CRM_DB_PASSWORD=your-password
CRM_DB_NAME=crm_db
CRM_DB_DIALECT=mysql
CRM_DB_DISPLAY_NAME=CRM 系统数据库
```

### 步骤二：注册数据源

后端通过配置文件或数据库注册数据源（定义在 `backend/app/core/config.py`）：

```python
# 数据源配置（支持从 .env 动态加载）
DATASOURCES = [
    {
        "id": "crm_mysql",
        "display_name": "CRM 系统数据库",
        "dialect": "mysql",
        "host": "${CRM_DB_HOST}",
        "port": "${CRM_DB_PORT}",
        "user": "${CRM_DB_USER}",
        "password": "${CRM_DB_PASSWORD}",
        "database": "${CRM_DB_NAME}",
    }
]
```

### 步骤三：验证连接

```bash
# 调用数据源列表 API 验证
curl http://localhost:8000/api/v1/datasource/list
```

```json
// 响应
{
  "datasources": [
    { "id": "default", "display_name": "默认数据库", "dialect": "mysql" },
    { "id": "crm_mysql", "display_name": "CRM 系统数据库", "dialect": "mysql" }
  ]
}
```

---

## 新增数据库方言

如果需要接入新的数据库方言（如 ClickHouse、TiDB 等），需要在两层添加适配。

### 第一步：添加方言模板

在 `backend/app/db/dialects/` 目录下创建新文件：

```python
# backend/app/db/dialects/clickhouse.py

DIALECT_CONFIG = {
    "name": "clickhouse",
    "driver": "clickhouse-connect",
    "connection_template": "clickhouse://{user}:{password}@{host}:{port}/{database}",
    "features": {
        "supports_window_functions": True,
        "supports_cte": True,
        "supports_json": True,
        "quote_char": "`",
        "limit_syntax": "LIMIT {limit}",
    }
}

# LLM 提示词中使用的 SQL 语法特征
SQL_SYNTAX_HINTS = """
ClickHouse SQL 注意事项：
- 使用 toDate(), toDateTime() 进行类型转换
- 日期函数：toStartOfMonth(), toStartOfWeek()
- 聚合函数：uniqExact() 替代 COUNT(DISTINCT)
- 表引擎通常为 MergeTree 系列
- 不支持事务，DELETE/UPDATE 是异步操作
"""
```

### 第二步：注册到方言工厂

修改 `backend/app/db/session.py`（或方言注册中心），注册新方言：

```python
# backend/app/db/dialects/__init__.py

from .mysql import DIALECT_CONFIG as MYSQL_CONFIG
from .postgresql import DIALECT_CONFIG as PG_CONFIG
from .sqlserver import DIALECT_CONFIG as MSSQL_CONFIG
from .oracle import DIALECT_CONFIG as ORACLE_CONFIG
from .clickhouse import DIALECT_CONFIG as CLICKHOUSE_CONFIG  # 新增

DIALECT_REGISTRY = {
    "mysql": MYSQL_CONFIG,
    "postgresql": PG_CONFIG,
    "sqlserver": MSSQL_CONFIG,
    "oracle": ORACLE_CONFIG,
    "clickhouse": CLICKHOUSE_CONFIG,  # 新增
}
```

### 第三步：更新 SQL Coder Agent 提示词

确保 SQL Coder Agent 在生成 SQL 时加载对应方言的语法提示：

```python
# backend/app/agents/sql_coder.py（示意）

def get_dialect_hints(dialect: str) -> str:
    """获取方言特定的 LLM 提示词"""
    dialect_module = DIALECT_REGISTRY.get(dialect)
    if dialect_module:
        return dialect_module.SQL_SYNTAX_HINTS
    return ""
```

---

## Agent 代码不变原则

以下核心 Agent **不需要改动**即可适配新方言：

| Agent | 说明 |
|-------|------|
| **clarify_plan** | 不涉及数据库操作（仅 LLM 调用） |
| **RAG Agent** | 仅操作 Milvus 向量库 |
| **Schema Agent** | 使用 SQLAlchemy 通用接口获取元数据 |
| **Security Agent** | 基于 SQL 文本语法判断，不依赖特定方言 |
| **Analyst Agent** | 对查询结果（通用数据结构）做分析 |
| **Reporter Agent** | 对查询结果生成图表，不感知数据来源 |
| **Misc Agent** | 仅 LLM 文本生成，不涉及数据库 |

唯一需要适配的是 **SQL Coder Agent** 的 LLM 提示词，通过方言模板注入（无需改动代码逻辑）。

---

## 测试接入结果

```bash
# 1. 验证数据源已注册
curl http://localhost:8000/api/v1/datasource/list

# 2. 使用新数据源发起对话
curl -X POST http://localhost:8000/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "query": "查询用户数量",
    "datasource_id": "crm_mysql"
  }'
```

---

## 安全注意事项

1. **使用只读账号**：建议为 DataAgent 创建专用的只读数据库账号，写操作通过审批流控制
2. **网络隔离**：数据库应部署在内网，仅允许后端服务访问
3. **连接池限制**：配置合理的连接池大小，避免耗尽数据库连接
4. **敏感字段脱敏**：在 `.env` 或配置中心管理密码，不硬编码
