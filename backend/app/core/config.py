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
    EVENT_SOURCING_ENABLED: bool = True

    # ── 系统提示词分层组装（Phase 2：PromptSection）────
    # 开启后，build_system_prompt 走 PromptAssembler 分层组装（内容与旧字符串等价），
    # 关闭则返回旧版单一字符串。便于 A/B 对比与提示词可插拔/审计。
    PROMPT_SECTION_ENABLED: bool = False

    # ── DEF-009：analyst 与 reporter 并行执行 ────
    # reporter（图表生成）仅依赖 query_result/columns/question，不依赖分析文本，
    # 可与 analyst 流式分析并行。开启后 quality_gate/chart_direct 同时扇出两节点，
    # 实测可节省 5~10s 串行等待。关闭则回退原串行行为（analyst → 路由 → reporter/answer）。
    PARALLEL_ANALYST_REPORTER: bool = True

    # ── R8：Skill 渐进式披露（对齐 Harness 技能子系统）────
    # 开启后 system prompt 仅注入 name+description 目录（大幅减少 token），
    # 完整 SKILL.md 正文由模型按需调用 load_skill 工具加载；
    # 关闭则回退旧版全量注入行为。
    SKILL_PROGRESSIVE_DISCLOSURE: bool = True

    # ── R9：工具执行流水线（对齐 Harness tools pre/guards/execute/post）────
    # 为 DeepAgent 所有工具统一提供：参数审计日志、超时保护、耗时埋点、
    # 结果截断、异常兜底（异常转错误字符串，不中断 Agent 循环）。
    TOOL_PIPELINE_ENABLED: bool = True
    TOOL_EXEC_TIMEOUT: int = 90        # 单次工具执行超时（秒）
    TOOL_RESULT_MAX_LEN: int = 4000    # 工具结果注入 LLM 上下文前的最大字符数

    # ── R21：上下文压缩（对齐 Harness compaction 插件）────
    # 多轮对话历史超过阈值时做确定性压缩（非 LLM 摘要，零延迟）：
    # 保留最近 KEEP_RECENT 条完整消息，更早的替换为一条 "[历史压缩]" 摘要。
    CONTEXT_COMPACTION_ENABLED: bool = True
    CONTEXT_MAX_MESSAGES: int = 40     # 历史消息数阈值（超过才触发）
    CONTEXT_KEEP_RECENT: int = 12      # 压缩后保留的最近消息条数
    CONTEXT_DIGEST_MAX_CHARS: int = 1200  # 摘要文本最大字符数

    # ── R16：turn/step 事件语义（架构专项 P1）────
    # 开启后每轮问答落库 turn_start/turn_end 边界事件（node_index 即轮次、
    # run_id 即运行、事件 id 即 step 序），并在请求入口做不变量检查
    # （"进入模型上下文的内容必须已落库"）。
    TURN_EVENT_ENABLED: bool = True

    # ── R20：统一循环驱动器（架构专项 P2 第二步：已接管执行分发）────
    # ENABLED：总开关（false 时回退旧构造路径——仅压缩，分发规则不变）
    # SHADOW：影子比对（观察期工具，默认关闭；开启后额外与旧路径压缩结果
    #         比对并记日志，不影响执行）
    AGENT_LOOP_ENABLED: bool = True
    AGENT_LOOP_SHADOW: bool = False

    # ── R23：执行层扩展（架构专项 P5，默认关闭零攻击面）────
    # 开启后 DeepAgent 获得受控 write_file（exports/ 白名单目录）与
    # run_command（用户白名单 + 黑名单 + 档位管控）两个工具；
    # 命令白名单由用户自行维护：configs/command_whitelist.json
    EXEC_TOOLS_ENABLED: bool = False

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
