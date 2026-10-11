"""
MCP 运行时客户端 — 将配置中心登记的 MCP Server 工具接入 DeepAgent（DEF-004）。

设计要点：
- 原生 stdio JSON-RPC 实现（不依赖 mcp SDK），与 config_api.py /mcp/test 的
  探测模式一致：subprocess + 线程读取，规避 Windows 事件循环下
  asyncio.create_subprocess_exec 的 NotImplementedError。
- 进程级缓存：同一 (command, args) 的 server 进程被复用（带活性检查，
  进程消亡后下次调用自动重启），避免每次工具调用都重新拉起 npx（秒级开销）。
- 命名空间隔离：工具名统一为 mcp_{server_id}_{tool_name}，防止跨 server
  与本地工具重名。
- 优雅降级：单个 server 握手/列举失败只跳过该 server，不影响主流程。

生命周期：
- get_mcp_tools()：Agent 装配时（get_deep_agent，全局单例）调用一次，
  为每个 enabled server 拉取工具清单并包装为异步闭包。
- shutdown_mcp_servers()：应用关闭时（main.py lifespan）回收全部子进程。
"""
from __future__ import annotations

import json
import queue
import re
import subprocess
import threading
import time
from typing import Any

from app.utils.log_utils import log

_INIT_TIMEOUT = 15.0      # initialize 握手超时（秒）
_LIST_TIMEOUT = 15.0      # tools/list 超时（秒）
_CALL_TIMEOUT = 120.0     # tools/call 超时（秒，工具执行可能较慢）

# 进程缓存：key = (command, tuple(args)) → McpStdioServer
_SERVER_CACHE: dict[tuple[str, tuple[str, ...]], "McpStdioServer"] = {}
_CACHE_LOCK = threading.Lock()


class McpStdioServer:
    """单个 stdio MCP Server 的进程管理与 JSON-RPC 客户端。"""

    def __init__(self, command: str, args: list[str]):
        self.command = command
        self.args = args
        self._proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._resp_queue: queue.Queue[dict] = queue.Queue()
        self._next_id = 1
        # RLock：start() 持锁期间会经 _request() 再次申请同一把锁，
        # 普通 Lock 会自死锁，必须用可重入锁
        self._lock = threading.RLock()
        self._server_info: dict = {}

    # ── 进程与读取线程 ──────────────────────────────────────

    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        """拉起子进程 + initialize 握手（阻塞，线程安全，重复调用幂等）。"""
        if self.alive():
            return
        with self._lock:
            if self.alive():
                return
            self._resp_queue = queue.Queue()
            self._proc = subprocess.Popen(
                [self.command, *self.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
            self._reader = threading.Thread(
                target=self._read_loop, daemon=True, name=f"mcp-reader-{id(self):x}"
            )
            self._reader.start()

            resp = self._request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "dataagent-pro", "version": "0.1.0"},
                },
                timeout=_INIT_TIMEOUT,
            )
            self._server_info = resp.get("result", {}) or {}
            # initialized 通知：无 id，不产生响应
            self._notify("notifications/initialized", {})
            log.info(
                f"[MCP] server 已连接: {self.command} "
                f"(protocol={self._server_info.get('protocolVersion', '?')})"
            )

    def _read_loop(self) -> None:
        """后台线程：持续读取 stdout，将带 id 的响应入队。"""
        proc = self._proc
        assert proc and proc.stdout
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue  # 非 JSON 日志行，忽略
            if isinstance(msg, dict) and "id" in msg:
                self._resp_queue.put(msg)

    # ── JSON-RPC ────────────────────────────────────────────

    def _notify(self, method: str, params: dict) -> None:
        assert self._proc and self._proc.stdin
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        try:
            self._proc.stdin.write(json.dumps(payload) + "\n")
            self._proc.stdin.flush()
        except Exception as exc:
            log.warning(f"[MCP] 通知发送失败 ({method}): {exc}")

    def _request(self, method: str, params: dict, timeout: float) -> dict:
        """发送请求并等待响应；超时/进程死亡抛 RuntimeError。"""
        if not self.alive():
            raise RuntimeError(f"MCP server 进程已退出: {self.command}")
        with self._lock:
            req_id = self._next_id
            self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
        try:
            assert self._proc and self._proc.stdin
            self._proc.stdin.write(json.dumps(payload) + "\n")
            self._proc.stdin.flush()
        except Exception as exc:
            raise RuntimeError(f"MCP 请求发送失败: {exc}") from exc

        deadline = time.monotonic() + timeout
        # 只消费属于当前请求之前的积压响应（如上次超时的迟到响应）
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(f"MCP 请求超时 ({timeout}s): {method}")
            try:
                msg = self._resp_queue.get(timeout=remaining)
            except queue.Empty:
                continue
            if msg.get("id") == req_id:
                if "error" in msg:
                    err = msg["error"]
                    raise RuntimeError(f"MCP 错误: {err.get('message', err)}")
                return msg
            # 迟到的其他响应：丢弃

    # ── MCP 能力 ────────────────────────────────────────────

    def list_tools(self) -> list[dict]:
        resp = self._request("tools/list", {}, timeout=_LIST_TIMEOUT)
        return resp.get("result", {}).get("tools", []) or []

    def call_tool(self, name: str, arguments: dict) -> str:
        resp = self._request(
            "tools/call", {"name": name, "arguments": arguments}, timeout=_CALL_TIMEOUT
        )
        result = resp.get("result", {}) or {}
        if result.get("isError"):
            content = result.get("content") or []
            text = content[0].get("text", "") if content else ""
            raise RuntimeError(f"工具执行失败: {text[:300]}")
        # content 为 [{type: text, text: ...}, ...] → 拼接纯文本
        parts = []
        for block in result.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts) if parts else json.dumps(result, ensure_ascii=False)

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.kill()
            except Exception:
                pass
        self._proc = None


def _get_server(command: str, args: list[str]) -> McpStdioServer:
    """取缓存 server 实例；进程消亡时自动重启。"""
    key = (command, tuple(args))
    with _CACHE_LOCK:
        server = _SERVER_CACHE.get(key)
    if server is None:
        server = McpStdioServer(command, args)
        with _CACHE_LOCK:
            _SERVER_CACHE[key] = server
    if not server.alive():
        server.start()
    return server


def get_mcp_tools() -> list[Any]:
    """
    扫描配置中心启用的 MCP server，拉取工具清单并包装为 DeepAgent 工具。

    同步阻塞（内部 subprocess + 线程），调用方应放线程池：
        mcp_tools = await asyncio.to_thread(get_mcp_tools)

    返回:
        异步工具函数列表；单个 server 失败只记日志并跳过。
    """
    from app.core.config_manager import get_config_manager

    tools: list[Any] = []
    servers = [s for s in get_config_manager().mcp_servers if s.get("enabled")]
    for srv in servers:
        sid = str(srv.get("id") or "").strip()
        command = str(srv.get("command") or "").strip()
        args = srv.get("args") or []
        if not sid or not command:
            continue
        try:
            server = _get_server(command, [str(a) for a in args])
            mcp_tools = server.list_tools()
        except Exception as exc:
            log.warning(f"[MCP] server {sid}({command}) 不可用，跳过: {exc}")
            continue

        for t in mcp_tools:
            raw_name = str(t.get("name") or "").strip()
            if not raw_name:
                continue
            tool_name = "mcp_" + re.sub(r"[^A-Za-z0-9_]", "_", f"{sid}_{raw_name}")
            description = str(t.get("description") or f"MCP 工具 {raw_name}（来自 server {sid}）")
            schema = t.get("inputSchema") or {"type": "object", "properties": {}}
            srv_cmd = command
            srv_args = [str(a) for a in args]

            def _invoke(closure_raw: str, closure_srv_cmd: str, closure_srv_args: list[str]):
                async def _call(**kwargs: Any) -> str:
                    """执行 MCP 工具（进程消亡时自动重启 server 重试一次）。"""
                    log.info(f"[MCP] 工具调用: {closure_raw} args={str(kwargs)[:200]}")
                    try:
                        srv = _get_server(closure_srv_cmd, closure_srv_args)
                        return srv.call_tool(closure_raw, kwargs)
                    except RuntimeError as exc:
                        # 进程中途消亡：重启一次重试
                        try:
                            srv = _get_server(closure_srv_cmd, closure_srv_args)
                            if not srv.alive():
                                srv.start()
                            return srv.call_tool(closure_raw, kwargs)
                        except Exception as retry_exc:
                            return f"MCP 工具 {closure_raw} 执行失败: {retry_exc}"
                return _call

            tool = _build_structured_tool(
                name=tool_name,
                description=f"{description}\n\n（MCP server: {srv_cmd}）",
                input_schema=schema,
                coroutine=_invoke(raw_name, srv_cmd, srv_args),
            )
            tools.append(tool)
            log.info(f"[MCP] 注册工具: {tool_name} (server={sid})")

    log.info(f"[MCP] 工具装配完成: {len(tools)} 个工具 / {len(servers)} 个 server")
    return tools


def _build_structured_tool(name: str, description: str,
                           input_schema: dict, coroutine) -> Any:
    """
    按 MCP inputSchema 构建 LangChain StructuredTool。

    不能用裸 **kwargs 函数：langchain 从函数签名推导参数 schema 时无法
    识别 **kwargs，导致模型传参被嵌套成 {'kwargs': {...}}（实测缺陷）。
    此处用 pydantic create_model 从 inputSchema.properties 精确生成 args_schema。
    """
    from pydantic import create_model
    from langchain_core.tools import StructuredTool

    props = input_schema.get("properties") or {}
    required = set(input_schema.get("required") or [])
    _TYPE_MAP = {
        "string": str, "integer": int, "number": float,
        "boolean": bool, "array": list, "object": dict,
    }
    fields: dict[str, tuple] = {}
    for pname, pspec in props.items():
        ptype = pspec.get("type") if isinstance(pspec, dict) else None
        ann = _TYPE_MAP.get(ptype, str)
        if pname not in required:
            fields[pname] = (ann | None, pspec.get("default") if isinstance(pspec, dict) else None)
        else:
            fields[pname] = (ann, ...)

    args_model = create_model(f"{name}_Args", **fields)
    return StructuredTool.from_function(
        name=name,
        description=description,
        args_schema=args_model,
        coroutine=coroutine,
    )


def shutdown_mcp_servers() -> None:
    """应用关闭时回收全部 MCP 子进程。"""
    with _CACHE_LOCK:
        servers = list(_SERVER_CACHE.values())
        _SERVER_CACHE.clear()
    for srv in servers:
        srv.stop()
    if servers:
        log.info(f"[MCP] 已回收 {len(servers)} 个 server 进程")
