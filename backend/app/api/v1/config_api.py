"""
配置管理 API (V2.0) — LLM / Skill / MCP 增删改查 + 热更新。

所有接口需要 admin 权限（user_type == "00"）。
"""
import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from pathlib import Path
from pydantic import BaseModel

from app.api.v1.auth import get_current_user
from app.core.config_manager import get_config_manager

router = APIRouter(prefix="/config", tags=["config"])


# ── 权限检查 ──

async def require_admin(user: dict = Depends(get_current_user)):
    if user.get("user_type") != "00":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


# ── LLM Providers ──

@router.get("/llm")
async def list_llm(_admin=Depends(require_admin)):
    mgr = get_config_manager()
    return {"providers": mgr.llm_providers, "mode_defaults": mgr.mode_defaults}


class LLMProvider(BaseModel):
    id: str
    name: str
    api_base: str
    api_key_env: str = ""
    api_key: str = ""
    key_mode: str = "env"  # "env" = 从环境变量读取 / "direct" = 直接使用 api_key
    model: str
    temperature: float = 0.3
    max_tokens: int = 4096
    is_default: bool = False
    enabled: bool = True


@router.post("/llm")
async def create_llm(provider: LLMProvider, _admin=Depends(require_admin)):
    if not provider.id or not provider.id.strip():
        raise HTTPException(400, "Provider id 不能为空")
    mgr = get_config_manager()
    data = mgr.get("llm_providers.json")
    providers = data.get("providers", [])
    if any(p["id"] == provider.id for p in providers):
        raise HTTPException(400, f"Provider {provider.id} 已存在")
    if provider.is_default:
        for p in providers:
            p["is_default"] = False
    providers.append(provider.model_dump())
    data["providers"] = providers
    err = mgr.save("llm_providers.json", data)
    if err:
        raise HTTPException(500, f"保存失败: {err}")
    return {"ok": True}


@router.put("/llm/{provider_id}")
async def update_llm(provider_id: str, provider: LLMProvider, _admin=Depends(require_admin)):
    mgr = get_config_manager()
    data = mgr.get("llm_providers.json")
    providers = data.get("providers", [])
    idx = next((i for i, p in enumerate(providers) if p["id"] == provider_id), None)
    if idx is None:
        raise HTTPException(404, f"Provider {provider_id} 不存在")
    if provider.is_default:
        for p in providers:
            p["is_default"] = False
    providers[idx] = provider.model_dump()
    data["providers"] = providers
    mgr.save("llm_providers.json", data)
    return {"ok": True}


@router.delete("/llm/{provider_id}")
async def delete_llm(provider_id: str, _admin=Depends(require_admin)):
    mgr = get_config_manager()
    data = mgr.get("llm_providers.json")
    providers = [p for p in data.get("providers", []) if p["id"] != provider_id]
    if len(providers) == len(data.get("providers", [])):
        raise HTTPException(404, f"Provider {provider_id} 不存在")
    data["providers"] = providers
    mgr.save("llm_providers.json", data)
    return {"ok": True}


@router.put("/llm/mode-defaults")
async def update_mode_defaults(body: dict, _admin=Depends(require_admin)):
    mgr = get_config_manager()
    data = mgr.get("llm_providers.json")
    data["mode_defaults"] = body
    mgr.save("llm_providers.json", data)
    return {"ok": True}


# ── Skills ──

# 技能实体目录（已安装 skill 实际落盘位置）与目录库（安装模板来源）
_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills" / "skills"
_CATALOG_DIR = Path(__file__).resolve().parent.parent.parent / "skills" / "catalog"


def _skill_installed(skill_id: str) -> bool:
    """判断 folder 类型技能是否已安装（文件夹存在）"""
    return (_SKILLS_DIR / skill_id).is_dir()


@router.get("/skills")
async def list_skills(_admin=Depends(require_admin)):
    """列出全部技能，folder 类型的 installed 状态按磁盘实时计算"""
    mgr = get_config_manager()
    result = []
    for s in mgr.skills:
        item = dict(s)
        if item.get("type") == "folder":
            item["installed"] = _skill_installed(item["id"])
        else:
            item["installed"] = True
        result.append(item)
    return {"skills": result}


class SkillAction(BaseModel):
    id: str


@router.post("/skills/install")
async def install_skill(body: SkillAction, _admin=Depends(require_admin)):
    """安装技能：从目录库复制 SKILL.md + 执行脚本到 skills 实体目录"""
    import shutil

    mgr = get_config_manager()
    data = mgr.get("skills.json")
    skills = data.get("skills", [])
    skill = next((s for s in skills if s["id"] == body.id), None)
    if skill is None:
        raise HTTPException(404, f"未找到技能 {body.id}")
    if skill.get("type") != "folder":
        raise HTTPException(400, "该技能为内置能力，不支持安装/卸载")

    src = _CATALOG_DIR / body.id
    if not src.is_dir():
        raise HTTPException(404, f"目录库缺少模板: {body.id}")

    dst = _SKILLS_DIR / body.id
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)

    skill["installed"] = True
    skill["enabled"] = True
    mgr.save("skills.json", data)
    return {"ok": True, "installed": True}


@router.post("/skills/uninstall")
async def uninstall_skill(body: SkillAction, _admin=Depends(require_admin)):
    """卸载技能：删除 skills 实体目录（保留目录库模板，可再次安装）"""
    import shutil

    mgr = get_config_manager()
    data = mgr.get("skills.json")
    skills = data.get("skills", [])
    skill = next((s for s in skills if s["id"] == body.id), None)
    if skill is None:
        raise HTTPException(404, f"未找到技能 {body.id}")
    if skill.get("type") != "folder":
        raise HTTPException(400, "该技能为内置能力，不支持安装/卸载")

    dst = _SKILLS_DIR / body.id
    if dst.is_dir():
        shutil.rmtree(dst)

    skill["installed"] = False
    skill["enabled"] = False
    mgr.save("skills.json", data)
    return {"ok": True, "installed": False}


@router.put("/skills/{skill_id}")
async def update_skill(skill_id: str, body: dict, _admin=Depends(require_admin)):
    mgr = get_config_manager()
    data = mgr.get("skills.json")
    skills = data.get("skills", [])
    idx = next((i for i, s in enumerate(skills) if s["id"] == skill_id), None)
    if idx is None:
        raise HTTPException(404)
    skills[idx].update(body)
    data["skills"] = skills
    mgr.save("skills.json", data)
    return {"ok": True}


# ── MCP Servers ──

@router.get("/mcp")
async def list_mcp(_admin=Depends(require_admin)):
    return {"servers": get_config_manager().mcp_servers}


@router.post("/mcp")
async def create_mcp(body: dict, _admin=Depends(require_admin)):
    mgr = get_config_manager()
    data = mgr.get("mcp_servers.json")
    servers = data.get("servers", [])
    servers.append(body)
    data["servers"] = servers
    mgr.save("mcp_servers.json", data)
    return {"ok": True}


@router.put("/mcp/{server_id}")
async def update_mcp(server_id: str, body: dict, _admin=Depends(require_admin)):
    mgr = get_config_manager()
    data = mgr.get("mcp_servers.json")
    servers = data.get("servers", [])
    idx = next((i for i, s in enumerate(servers) if s["id"] == server_id), None)
    if idx is None:
        raise HTTPException(404)
    servers[idx].update(body)
    data["servers"] = servers
    mgr.save("mcp_servers.json", data)
    return {"ok": True}


@router.delete("/mcp/{server_id}")
async def delete_mcp(server_id: str, _admin=Depends(require_admin)):
    mgr = get_config_manager()
    data = mgr.get("mcp_servers.json")
    servers = [s for s in data.get("servers", []) if s["id"] != server_id]
    data["servers"] = servers
    mgr.save("mcp_servers.json", data)
    return {"ok": True}


# ── MCP 连接测试（原生 stdio JSON-RPC 握手，无需 mcp SDK）──

@router.post("/mcp/test")
async def test_mcp(body: dict, _admin=Depends(require_admin)):
    """
    在保存前验证 MCP 服务端点的连通性。

    通过子进程以 stdio 方式启动 server，发送 MCP `initialize` 请求，
    并等待其 JSON-RPC 响应，据此判断服务是否可用。
    """
    command = (body.get("command") or "").strip()
    args = body.get("args") or []
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            args = [a for a in args.split() if a]
    if not isinstance(args, list):
        args = []

    if not command:
        return {"ok": False, "success": False, "message": "启动命令不能为空"}

    def _probe():
        """在线程中通过 stdio 启动 MCP server 并完成 initialize 握手。

        不使用 asyncio.create_subprocess_exec：在 Windows 的某些事件循环策略下
        该方法会抛 NotImplementedError。改用标准库 subprocess + 线程读取（带超时），
        跨平台更稳健。
        """
        import subprocess
        import threading

        init_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "dataagent-probe", "version": "1.0"},
            },
        }
        payload = json.dumps(init_req) + "\n"

        try:
            proc = subprocess.Popen(
                [command, *args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError:
            return {"ok": False, "success": False, "message": f"命令未找到: {command}（请确认已安装并在 PATH 中）"}
        except Exception as exc:
            return {"ok": False, "success": False, "message": f"启动失败: {type(exc).__name__}: {exc}"}

        try:
            proc.stdin.write(payload)
            proc.stdin.flush()

            # 读取首行响应（部分 server 会先输出日志行），带 10s 超时
            box: dict = {}

            def _read_line():
                try:
                    box["line"] = proc.stdout.readline()
                except Exception:
                    box["line"] = ""

            th = threading.Thread(target=_read_line)
            th.start()
            th.join(timeout=10)
            if th.is_alive():
                proc.kill()
                return {"ok": False, "success": False, "message": "连接超时（>10s），服务未返回 initialize 响应"}

            raw = (box.get("line") or "").strip()
            if not raw:
                return {"ok": False, "success": False, "message": "服务未返回任何响应"}

            try:
                resp = json.loads(raw)
            except json.JSONDecodeError:
                return {"ok": False, "success": False, "message": f"未收到有效 JSON-RPC 响应: {raw[:160]}"}

            if resp.get("jsonrpc") == "2.0" and "id" in resp:
                proto = resp.get("result", {}).get("protocolVersion", "未知")
                return {"ok": True, "success": True, "message": f"连接成功（MCP 协议版本: {proto}）"}
            return {"ok": False, "success": False, "message": f"响应格式异常: {raw[:160]}"}
        except Exception as exc:
            return {"ok": False, "success": False, "message": f"握手失败: {type(exc).__name__}: {exc}"}
        finally:
            try:
                proc.kill()
            except Exception:
                pass

    return await asyncio.to_thread(_probe)
