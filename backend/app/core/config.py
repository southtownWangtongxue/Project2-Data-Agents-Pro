"""
应用配置模块 —— 使用 pydantic-settings 从 .env 文件读取所有配置项
"""
import pathlib
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
PROJECT_PATH = pathlib.Path(__file__).parent.parent.parent.parent

class Settings(BaseSettings):
    """全局配置，自动从项目根目录的 .env 文件加载。"""

    # ── LLM 大模型配置 ──────────────────────────────
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL_NAME: str = "gpt-4o"

    # ── Redis ───────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── Milvus 向量数据库 ───────────────────────────
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530
    MILVUS_COLLECTION_NAME: str = "knowledge_base"

    # ── Embedding 模型（远程 OpenAI 兼容接口）───────────
    # 使用任意 OpenAI 兼容的 embeddings 服务（如智谱 embedding-3、DashScope text-embedding-v3 等）。
    # 通过 EMBEDDING_BASE_URL + EMBEDDING_API_KEY 认证，模型维度由服务端决定。
    EMBEDDING_MODEL: str = "embedding-3"
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_BASE_URL: str = ""

    # ── 数据库类型选择 ─────────────────────────────
    DB_TYPE: str = "mysql"  # mysql 或 postgresql

    # ── MySQL ───────────────────────────────────────
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = ""
    MYSQL_DATABASE: str = "dataagent"

    # ── PostgreSQL ──────────────────────────────────
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DATABASE: str = "dataagent"

    # ── JWT 认证 ───────────────────────────────────
    JWT_SECRET: str = "dataagent-default-secret-change-in-production"
    JWT_EXPIRE_HOURS: int = 24

    # ── 应用服务 ────────────────────────────────────
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    DEBUG: bool = True

    # ── 事件溯源（Phase 1：会话事件日志 + surface 投影）────
    # 开启后，SSE 流式产出时双写业务事件到 session_events 表，
    # get_session_messages 优先从事件日志投影恢复，回退 Redis checkpoint。
    EVENT_SOURCING_ENABLED: bool = False

    # ── 系统提示词分层组装（Phase 2：PromptSection）────
    # 开启后，build_system_prompt 走 PromptAssembler 分层组装（内容与旧字符串等价），
    # 关闭则返回旧版单一字符串。便于 A/B 对比与提示词可插拔/审计。
    PROMPT_SECTION_ENABLED: bool = False

    # ── 能力接缝（Phase 3：ServiceDefinition/Provider/Consumer）────
    # 开启后，search/llm_client/storage 等可替换点走 SeamRegistry 解析后端，
    # 关闭则走原硬编码实现。便于多后端可替换/可注入测试后端。
    SEAM_ENABLED: bool = False

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_PATH / ".env"),           # 自动读取项目根目录的 .env
        env_file_encoding="utf-8",
        extra="ignore",            # 忽略 .env 中未定义的字段
    )


# 全局单例配置实例
settings = Settings()


def get_settings() -> Settings:
    """返回全局配置单例实例"""
    # print("PROJECT_PATH", PROJECT_PATH )
    # print(".env exists?:", (PROJECT_PATH / ".env").exists())
    # print(settings)
    return settings
