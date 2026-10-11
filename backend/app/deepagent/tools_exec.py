"""
执行层扩展工具（R23，架构专项 P5）+ seam 注册（R18）

对齐 Harness 的 fs / shell 能力，全部走既有安全设施：
    · R9 工具执行流水线（装配点统一包装：审计/超时/截断/异常兜底）
    · R11 审批档位（read_only 全拒；workspace_write 放行 write_file；
      run_command 仅 full_access 放行——DeepAgent 工具内无法挂
      LangGraph interrupt，人工审批以"拒绝+提示切档"实现）
    · R10 审计日志

安全边界：
    · write_file：路径 resolve 后必须位于白名单目录（backend/exports/）内，
      防目录逃逸；内容大小限制
    · run_command：白名单（configs/command_whitelist.json，**由用户自行维护**，
      决策点③）+ 硬编码危险模式黑名单 + shell=False + 超时 + 输出截断
    · 总开关 EXEC_TOOLS_ENABLED 默认 False（不启用不注册，零攻击面）

R18 seam：向能力接缝注册 "fs" 与 "shell" 服务（provider: builtin-exec），
后续替换为其他实现（如沙箱容器执行）时只换 provider 不改装配点。
"""
from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from app.core.config import settings
from app.utils.log_utils import log

# 写文件白名单根目录（项目内 exports/）
EXPORT_ROOT = Path(__file__).resolve().parent.parent.parent / "exports"
MAX_FILE_BYTES = 200 * 1024  # 单文件内容上限 200KB

# 硬编码危险模式（与用户白名单正交，任何情况下拒绝）
_COMMAND_DENY_PATTERNS = (
    "rm ", "rmdir", "sudo", "del ", "format ", "shutdown", "regsvr32",
    "curl", "wget", "Invoke-WebRequest", "Remove-Item", "rd /s",
    "mklink", "taskkill", "net user", "reg add", "reg delete",
)

_WHITELIST_FILE = "command_whitelist.json"


def _command_whitelist() -> list[str]:
    """读取用户自维护的命令白名单（决策点③：清单由用户自行维护）。"""
    try:
        from app.core.config_manager import get_config_manager
        data = get_config_manager().get(_WHITELIST_FILE)
        cmds = data.get("commands", [])
        return [str(c).strip().lower() for c in cmds if str(c).strip()]
    except Exception as exc:
        log.warning(f"[ExecTools] 白名单读取失败: {exc}")
        return []


def _current_tier() -> str:
    try:
        from app.core.approval_policy import get_tier
        return get_tier()
    except Exception:
        return "read_only"


def exec_tools_enabled() -> bool:
    return settings.EXEC_TOOLS_ENABLED


# ── 工具实现（经 R9 流水线包装后注册） ──────────────────────────

async def write_file_tool(path: str, content: str) -> str:
    """将分析结果或生成内容写入 exports 目录下的文件。

    仅允许写入 exports/ 白名单目录（自动创建子目录），路径逃逸会被拒绝。
    受审批档位管控：read_only 档位下拒绝执行。

    Args:
        path: 相对 exports/ 目录的目标文件路径，如 "reports/销售分析.md"
        content: 要写入的文本内容（UTF-8，上限 200KB）

    Returns:
        str: 写入结果说明（含绝对路径与字节数）；被拒绝或失败时返回原因
    """
    tier = _current_tier()
    if tier == "read_only":
        return (
            "当前审批档位为 read_only（只读模式），禁止写文件。"
            "如需写文件，请管理员在审批管理页将档位切换为 workspace_write 或 full_access。"
        )

    if not path or not path.strip():
        return "路径为空，拒绝写入。"
    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        return f"内容超过大小上限（{MAX_FILE_BYTES // 1024}KB），请分段写入。"

    EXPORT_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        target = (EXPORT_ROOT / path).resolve()
        if not str(target).startswith(str(EXPORT_ROOT.resolve())):
            return f"路径逃逸被拒绝：仅允许写入 exports/ 目录内（收到: {path}）"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except Exception as exc:
        return f"写入失败: {exc}"

    size = target.stat().st_size
    log.info(f"[ExecTools] write_file: {target} ({size} bytes) tier={tier}")
    return f"已写入 {size} 字节到 {target}"


async def run_command_tool(command: str, timeout: int = 30) -> str:
    """在服务器上执行白名单内的命令并返回输出。

    限制（四层管控）：
        1. 总开关 EXEC_TOOLS_ENABLED（默认关闭）
        2. 审批档位：仅 full_access 放行
        3. 用户白名单 configs/command_whitelist.json（首 token 匹配）
        4. 硬编码危险模式黑名单 + shell=False + 超时

    Args:
        command: 要执行的命令，如 "python --version"（白名单内的程序）
        timeout: 超时秒数（1~120，默认 30）

    Returns:
        str: 命令输出（stdout+stderr，截断至 4000 字符）或拒绝/失败原因
    """
    if not exec_tools_enabled():
        return "命令执行能力未启用（EXEC_TOOLS_ENABLED=false），请联系管理员。"

    tier = _current_tier()
    if tier != "full_access":
        return (
            f"命令执行仅 full_access 档位放行（当前: {tier}）。"
            "请管理员在审批管理页评估后切换档位。"
        )

    cmd = (command or "").strip()
    if not cmd:
        return "命令为空，拒绝执行。"
    low = cmd.lower()
    for pat in _COMMAND_DENY_PATTERNS:
        if pat in low:
            return f"命令包含被禁止的模式 '{pat.strip()}'，拒绝执行。"

    try:
        tokens = shlex.split(cmd)
    except ValueError as exc:
        return f"命令解析失败: {exc}"
    if not tokens:
        return "命令为空，拒绝执行。"
    whitelist = _command_whitelist()
    if not whitelist:
        return "命令白名单为空（configs/command_whitelist.json），拒绝执行。请管理员维护白名单。"
    if tokens[0].lower() not in whitelist:
        return f"命令 '{tokens[0]}' 不在白名单内。可用: {', '.join(sorted(set(whitelist)))}"

    timeout = max(1, min(int(timeout or 30), 120))
    try:
        proc = subprocess.run(
            tokens, shell=False, capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return f"命令执行超时（>{timeout}s），已终止。"
    except FileNotFoundError:
        return f"命令 '{tokens[0]}' 不存在。"
    except Exception as exc:
        return f"命令执行失败: {exc}"

    out = (proc.stdout or "") + (("\n[stderr] " + proc.stderr) if proc.stderr else "")
    log.info(f"[ExecTools] run_command: {cmd[:60]} rc={proc.returncode} tier={tier}")
    header = f"exit_code={proc.returncode}\n"
    return header + (out[:4000] or "(无输出)")


# ── R18 seam 注册 ────────────────────────────────────────────────

def register_exec_seam() -> None:
    """向能力接缝注册 fs / shell 服务（R18 扩展位）。

    后续若替换为沙箱容器执行等实现，只需注册新 provider 并 select，
    装配点（get_fixed_tools）无需改动。
    """
    try:
        from app.core.seam import get_seam, seam_enabled
        if not seam_enabled():
            return
        seam = get_seam()
        seam.define("fs", description="本地受控文件写入（exports/ 白名单）", default="builtin-exec")
        seam.register("fs", "builtin-exec", lambda: write_file_tool, description="受控文件写入")
        seam.define("shell", description="本地白名单命令执行", default="builtin-exec")
        seam.register("shell", "builtin-exec", lambda: run_command_tool, description="白名单命令执行")
        log.info("[ExecTools] seam 注册完成: fs/shell → builtin-exec")
    except Exception as exc:
        log.warning(f"[ExecTools] seam 注册失败（不影响工具注册）: {exc}")


def get_exec_tools() -> list:
    """返回执行层工具（仅 EXEC_TOOLS_ENABLED=true 时注册）。"""
    if not exec_tools_enabled():
        return []
    register_exec_seam()
    log.info("[DeepAgent] 执行层工具注册: write_file_tool, run_command_tool (经 R9 流水线+R11 档位管控)")
    return [write_file_tool, run_command_tool]
