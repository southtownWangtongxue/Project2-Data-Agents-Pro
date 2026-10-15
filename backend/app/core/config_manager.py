"""
ConfigManager — JSON 文件配置管理 + watchdog 热更新。

参考 ClaudeCode/CodeBuddy 的 JSON 配置模式：
  - 所有配置以 JSON 文件存储于 backend/configs/ 目录
  - watchdog 监听文件变更，自动重载到内存
  - 变更后无需重启，下次 API 请求即时生效
  - JSON Schema 校验 + 降级兜底
"""
import json
import os
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.utils.log_utils import log

CONFIGS_DIR = Path(__file__).parent.parent.parent / "configs"


class ConfigManager:
    """配置管理器单例：加载 + 监听 + 热更新"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._cache = {}
                    cls._instance._watcher_started = False
        return cls._instance

    def _load_json(self, filename: str) -> dict:
        path = CONFIGS_DIR / filename
        if not path.exists():
            log.warning(f"[ConfigManager] 配置文件不存在: {path}")
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            log.error(f"[ConfigManager] 加载 {filename} 失败: {e}，使用缓存")
            return self._cache.get(filename, {})

    def load_all(self):
        """加载 configs/ 目录下所有 .json 配置文件到内存。

        目录扫描（R19/P5）：新增配置文件（如 patch.json、command_whitelist.json）
        无需修改本清单即可被加载；_comment 等元键由各消费方自行过滤。
        首次启动：缺失的运行时文件从 *.example.json 拷贝生成。
        """
        from app.core.config_bootstrap import ensure_runtime_configs

        ensure_runtime_configs(CONFIGS_DIR)
        for path in sorted(CONFIGS_DIR.glob("*.json")):
            # Path.glob("*.json") also matches "*.example.json"
            if path.name.endswith(".example.json"):
                continue
            self._cache[path.name] = self._load_json(path.name)
        log.info("[ConfigManager] 配置加载完成")

    def reload_file(self, filename: str):
        """重载单个配置文件（watchdog 触发）"""
        new_data = self._load_json(filename)
        if new_data:
            self._cache[filename] = new_data
            log.info(f"[ConfigManager] 热更新: {filename}")

    def get(self, filename: str) -> dict:
        """获取配置（始终返回最新缓存）"""
        return deepcopy(self._cache.get(filename, {}))

    def save(self, filename: str, data: dict) -> str | None:
        """保存配置到文件（触发 watchdog 重载）"""
        path = CONFIGS_DIR / filename
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._cache[filename] = deepcopy(data)
            log.info(f"[ConfigManager] 保存成功: {filename}")
            return None
        except IOError as e:
            return str(e)

    def start_watcher(self):
        """启动 watchdog 文件监听（后台线程）"""
        if self._watcher_started:
            return
        self._watcher_started = True

        def _watch():
            try:
                from watchdog.observers import Observer
                from watchdog.events import FileSystemEventHandler

                class ConfigHandler(FileSystemEventHandler):
                    def __init__(self, outer):
                        super().__init__()
                        self._outer = outer

                    def on_modified(self, event):
                        if event.is_directory:
                            return
                        fname = os.path.basename(event.src_path)
                        if fname.endswith(".json") and fname in self._outer._cache:
                            log.info(f"[ConfigManager] watchdog 检测变更: {fname}")
                            self._outer.reload_file(fname)

                observer = Observer()
                observer.schedule(ConfigHandler(self), str(CONFIGS_DIR), recursive=False)
                observer.start()
                log.info("[ConfigManager] watchdog 文件监听已启动")
                observer.join()
            except ImportError:
                log.info("[ConfigManager] watchdog 未安装，热更新需手动调用 reload")
            except Exception as e:
                log.error(f"[ConfigManager] watchdog 异常: {e}")

        thread = threading.Thread(target=_watch, daemon=True, name="config-watcher")
        thread.start()

    # ── 便捷访问方法 ──

    @property
    def llm_providers(self) -> list[dict]:
        return self.get("llm_providers.json").get("providers", [])

    @property
    def mode_defaults(self) -> dict:
        return self.get("llm_providers.json").get("mode_defaults", {})

    @property
    def skills(self) -> list[dict]:
        return self.get("skills.json").get("skills", [])

    @property
    def mcp_servers(self) -> list[dict]:
        return self.get("mcp_servers.json").get("servers", [])

    @property
    def default_config(self) -> dict:
        return self.get("default.json")

    def get_enabled_skills(self, mode: str) -> list[dict]:
        """获取指定模式下已启用的 Skill 列表"""
        return [
            s for s in self.skills
            if s.get("enabled") and ("all" in s.get("modes", []) or mode in s.get("modes", []))
        ]

    def get_llm_config(self, provider_id: str | None = None) -> dict | None:
        """获取指定 LLM 配置；未指定则返回默认

        回退顺序：is_default 且 enabled 的 provider → 第一个 enabled 的 provider → None。
        避免无默认标记时静默回退到 .env（如已耗尽额度的 DashScope）。
        """
        providers = self.llm_providers
        if provider_id:
            return next((p for p in providers if p["id"] == provider_id and p.get("enabled")), None)
        return (
            next((p for p in providers if p.get("is_default") and p.get("enabled")), None)
            or next((p for p in providers if p.get("enabled")), None)
        )

    def resolve_api_key(self, provider: dict) -> str:
        """解析 API Key。

        顺序:key_mode=direct 直配 → 进程环境变量(api_key_env) → .env 文件同名变量。
        解析不到时返回空字符串——**绝不回退 settings.LLM_API_KEY**:那是另一个厂商的
        key(如 .env 的 DashScope key),兜底会把错误 key 发往目标 API,表现为
        401 Missing Authentication header,且极难定位。

        .env 补偿路径的必要性:项目未调用 load_dotenv(),pydantic 只把 .env 灌进
        Settings 实例,os.getenv 读不到(与 HARNESS_MODE 同源问题)。
        """
        import os

        if provider.get("key_mode") == "direct" and provider.get("api_key"):
            return provider["api_key"]

        env_var = provider.get("api_key_env", "")
        if not env_var:
            return provider.get("api_key", "")

        val = os.getenv(env_var, "")
        if val:
            return val

        from app.core.config import PROJECT_PATH

        env_file = PROJECT_PATH / ".env"
        try:
            if env_file.exists():
                for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    name, _, value = line.partition("=")
                    if name.strip() == env_var:
                        return value.strip().strip('"').strip("'")
        except OSError:
            pass
        return provider.get("api_key", "")


# 全局单例
_config_manager: ConfigManager | None = None


def get_config_manager() -> ConfigManager:
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
        _config_manager.load_all()
    return _config_manager
