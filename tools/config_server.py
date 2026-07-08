#!/usr/bin/env python3
"""
AgentBuddy 配置工具 Web UI 后端

启动: python tools/config_server.py
访问: http://127.0.0.1:5000
依赖: flask, pyyaml, requests
"""

import argparse
import csv
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

def _resolve_project_root() -> Path:
    """Frozen-aware 项目根定位。
    - dev: 仓库根（tools/config_server.py 的上两级）
    - frozen (PyInstaller onedir): exe 所在目录（_MEIPASS == exe dir，可写）
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _resolve_project_root()
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


def _script_run_cmd(script_name: str, args: list) -> list:
    """构建运行 scripts/ 下脚本的命令列表（frozen-aware）。
    - dev: [python, scripts/<name>.py, *args]
    - frozen: [exe, --run, <name>, *args]（由 app.py 的 --run 派发器执行）
    """
    if getattr(sys, "frozen", False):
        return [sys.executable, "--run", script_name, *args]
    return [sys.executable, str(SCRIPTS_DIR / f"{script_name}.py"), *args]


def _script_run_shell_cmd(script_name: str, args: list) -> str:
    """构建 shell 字符串形式的脚本运行命令（frozen-aware），用于 _stream_process。"""
    parts = _script_run_cmd(script_name, args)
    # 给含空格/特殊字符的路径加引号
    return " ".join(f'"{p}"' if (" " in p or '"' in p) else p for p in parts)

try:
    from flask import Flask, Response, jsonify, request, send_file, stream_with_context
except ImportError:
    print("[ERROR] Flask 未安装。请执行: pip install flask")
    sys.exit(1)

try:
    import yaml
except ImportError:
    print("[ERROR] PyYAML 未安装。请执行: pip install pyyaml")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("[ERROR] requests 未安装。请执行: pip install requests")
    sys.exit(1)


def _load_script_module(module_name: str, file_path: Path):
    """加载 scripts/ 目录下含连字符的脚本作为模块"""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载模块: {file_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# 从 lib/ 公共库导入（替代旧脚本的 importlib 加载）
sys.path.insert(0, str(SCRIPTS_DIR))
from lib.config_io import load_env_config_file, save_env_config_file
from lib.skills import build_install_command, parse_shorthand, enable_skill, disable_skill, get_enabled_skills
from lib.plugins import install_plugin, update_env_file, add_to_installed
from lib.ide.detect import detect_ide, detect_all
from lib.ide.session import list_sessions, export_session, import_session_to_ide
from lib.ide.launch import launch_ide, launch_ide_resume_session
from lib.ide.install import install_ide, uninstall_ide, reinstall_ide, get_install_info, IDE_INSTALL_META

app = Flask(__name__, static_folder=None)

# ============================================================
# 路径常量
# ============================================================
ENV_EXAMPLE = PROJECT_ROOT / "env.example.yaml"
ENV_FILE = PROJECT_ROOT / "env.yaml"
# 新拆分：env.yaml → llm.yaml + mcp.yaml
LLM_FILE = PROJECT_ROOT / "config" / "llm" / "llm.yaml"
MCP_CONFIG_FILE = PROJECT_ROOT / "config" / "mcp" / "mcp.yaml"
# 拆分后的示例模板（可安全提交）
LLM_EXAMPLE = PROJECT_ROOT / "template" / "llm" / "llm-env-example.yaml"
MCP_CONFIG_EXAMPLE = PROJECT_ROOT / "template" / "mcp" / "mcp-env-example.yaml"
MCP_TEMPLATE = PROJECT_ROOT / "template" / "mcp" / "mcp.template.json"
PLUGINS_DIR = PROJECT_ROOT / "template" / "plugins"
SKILLS_CSV = PROJECT_ROOT / "template" / "skills" / "skills-index.csv"
# 技能安装目标：~/.agents/skills/（用户级，下载/插件安装的默认目录）
AGENTS_SKILLS_INSTALL_DIR = Path.home() / ".agents" / "skills"
# 项目级技能目录：config/skills/（复制的可用技能 + skill.yaml 启用清单）
PROJECT_SKILLS_DIR = PROJECT_ROOT / "config" / "skills"
SKILL_YAML = PROJECT_SKILLS_DIR / "skill.yaml"
AGENTS_SKILLS_CACHE = PROJECT_ROOT / "template" / "skills"
# 安装目标（下载/插件/本地预置复制）
DOT_AGENTS_SKILLS = AGENTS_SKILLS_INSTALL_DIR
CMD_FILE = PROJECT_ROOT / "config" / "cmd" / "cmd.yaml"
CMD_EXAMPLE = PROJECT_ROOT / "template" / "cmd" / "cmd.yaml"
SUBAGENT_FILE = PROJECT_ROOT / "config" / "subagent" / "subagent.yaml"
SUBAGENT_EXAMPLE = PROJECT_ROOT / "template" / "subagent" / "subagent.yaml"

# env.yaml 中属于 llm.yaml 的顶层键（其余归 mcp.yaml 的只有 mcp）
LLM_TOP_KEYS = ["llm", "embedding", "tts", "asr", "vision", "misc"]

# 外部市场端点
MODELSCOPE_SKILLS_API = "https://www.modelscope.cn/openapi/v1/skills"
MODELSCOPE_MCP_LIST_API = "https://www.modelscope.cn/openapi/v1/mcp/servers"
MODELSCOPE_MCP_DETAIL_API = "https://www.modelscope.cn/openapi/v1/mcp/servers/{owner}/{name}"
SKILLS_SH_API = "https://skills.sh/api/search"

HTTP_TIMEOUT = 15  # 外部 API 超时秒数


def _ensure_config_dirs() -> None:
    """确保 config/ 下的所有子目录存在（打包后首次运行时创建）。

    _bootstrap_from_bundle 只复制 scripts/template/tools，
    config/ 目录由 _ensure_llm_file / _ensure_mcp_config_file 部分创建，
    但 skills/cmd/subagent/ide/proxy 等子目录需要显式创建。
    """
    config_dirs = [
        PROJECT_ROOT / "config",
        PROJECT_ROOT / "config" / "llm",
        PROJECT_ROOT / "config" / "mcp",
        PROJECT_ROOT / "config" / "skills",
        PROJECT_ROOT / "config" / "cmd",
        PROJECT_ROOT / "config" / "subagent",
        PROJECT_ROOT / "config" / "ide",
        PROJECT_ROOT / "config" / "ide" / "claude",
        PROJECT_ROOT / "config" / "ide" / "codex",
        PROJECT_ROOT / "config" / "ide" / "opencode",
        PROJECT_ROOT / "config" / "plugins",
        PROJECT_ROOT / "config" / "proxy",
        # 用户级技能安装目录（~/.agents/skills/，下载/插件安装目标）
        Path.home() / ".agents" / "skills",
    ]
    for d in config_dirs:
        d.mkdir(parents=True, exist_ok=True)


# 启动时确保目录存在
_ensure_config_dirs()


# ============================================================
# 通用工具
# ============================================================
def _ensure_llm_file() -> Path:
    """确保 llm.yaml 存在。
    优先级：
      1. llm.yaml 已存在 → 直接返回
      2. llm-env-example.yaml 存在 → 直接复制（推荐方式）
      3. env.yaml / env.example.yaml 存在 → 从中拆出 llm/embedding/tts/asr/vision/misc 部分（向后兼容）
      4. 创建空模板
    """
    if LLM_FILE.exists():
        return LLM_FILE
    # 优先使用拆分后的示例文件
    if LLM_EXAMPLE.exists():
        try:
            data = load_env_config_file(LLM_EXAMPLE)
            save_env_config_file(LLM_FILE, data)
            return LLM_FILE
        except Exception:
            pass
    # 向后兼容：从 env.yaml / env.example.yaml 拆分
    src = ENV_FILE if ENV_FILE.exists() else (ENV_EXAMPLE if ENV_EXAMPLE.exists() else None)
    if src and src.exists():
        try:
            data = load_env_config_file(src)
            llm_data = {k: v for k, v in (data or {}).items() if k in LLM_TOP_KEYS}
            save_env_config_file(LLM_FILE, llm_data)
            return LLM_FILE
        except Exception:
            pass
    save_env_config_file(LLM_FILE, {"llm": {"_active_provider": "", "_active_protocol": "openai|anthropic"}})
    return LLM_FILE


def _ensure_mcp_config_file() -> Path:
    """确保 mcp.yaml 存在（统一存放 mcpServers 服务定义 + mcp 密钥）。
    优先级：
      1. mcp.yaml 已存在 → 直接返回
      2. mcp-env-example.yaml 存在 → 直接复制（推荐方式）
      3. env.yaml / env.example.yaml 存在 → 从中拆出 mcp 部分（向后兼容）
      4. 创建空模板
    """
    if MCP_CONFIG_FILE.exists():
        return MCP_CONFIG_FILE
    # 优先使用拆分后的示例文件
    if MCP_CONFIG_EXAMPLE.exists():
        try:
            data = load_env_config_file(MCP_CONFIG_EXAMPLE)
            save_env_config_file(MCP_CONFIG_FILE, data)
            return MCP_CONFIG_FILE
        except Exception:
            pass
    # 向后兼容：从 env.yaml / env.example.yaml 拆分
    src = ENV_FILE if ENV_FILE.exists() else (ENV_EXAMPLE if ENV_EXAMPLE.exists() else None)
    if src and src.exists():
        try:
            data = load_env_config_file(src)
            mcp_data = {"mcp": (data or {}).get("mcp", {})}
            save_env_config_file(MCP_CONFIG_FILE, mcp_data)
            return MCP_CONFIG_FILE
        except Exception:
            pass
    save_env_config_file(MCP_CONFIG_FILE, {"mcp": {}})
    return MCP_CONFIG_FILE


def _load_mcp_yaml_full() -> dict:
    """加载 mcp.yaml 全量数据（含 mcpServers + mcp），并从 mcp.template.json 迁移。"""
    path = _ensure_mcp_config_file()
    try:
        data = load_env_config_file(path)
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    # 迁移：若 mcp.yaml 没有 mcpServers，但 mcp.template.json 存在，则合并进来
    if "mcpServers" not in data and MCP_TEMPLATE.exists():
        try:
            tpl = _read_json(MCP_TEMPLATE)
            if isinstance(tpl.get("mcpServers"), dict):
                data["mcpServers"] = tpl["mcpServers"]
                save_env_config_file(path, data)
        except Exception:
            pass
    if "mcpServers" not in data:
        data["mcpServers"] = {}
    if "mcp" not in data or not isinstance(data.get("mcp"), dict):
        data["mcp"] = {}
    return data


def _save_mcp_yaml_full(data: dict) -> None:
    """保存 mcp.yaml 全量数据。"""
    path = _ensure_mcp_config_file()
    save_env_config_file(path, data)


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _stream_process(cmd: str, cwd: Optional[Path] = None):
    """运行子进程并以生成器形式逐行产出日志（SSE 格式）"""
    yield f"data: [CMD] {cmd}\n\n"
    try:
        proc = subprocess.Popen(
            cmd,
            shell=True,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore",
            bufsize=1,
        )
        try:
            for line in iter(proc.stdout.readline, ""):
                if line:
                    # SSE 每行一条
                    yield f"data: {line.rstrip()}\n\n"
            proc.wait(timeout=300)
            yield f"data: [EXIT] returncode={proc.returncode}\n\n"
        except subprocess.TimeoutExpired:
            proc.kill()
            yield "data: [TIMEOUT] 进程超时被终止（>300s）\n\n"
    except Exception as e:
        yield f"data: [ERROR] {e}\n\n"
    yield "data: [DONE]\n\n"


def _stream_process_rc(cmd: str, cwd: Optional[Path] = None):
    """类似 _stream_process，但返回 returncode（用于安装流程判断），不发 [DONE]。"""
    yield f"data: [CMD] {cmd}\n\n"
    rc = 1
    try:
        proc = subprocess.Popen(
            cmd,
            shell=True,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore",
            bufsize=1,
        )
        try:
            for line in iter(proc.stdout.readline, ""):
                if line:
                    yield f"data: {line.rstrip()}\n\n"
            proc.wait(timeout=300)
            rc = proc.returncode
            yield f"data: [EXIT] returncode={proc.returncode}\n\n"
        except subprocess.TimeoutExpired:
            proc.kill()
            yield "data: [TIMEOUT] 进程超时被终止（>300s）\n\n"
            rc = -1
    except Exception as e:
        yield f"data: [ERROR] {e}\n\n"
        rc = -1
    return rc


# ============================================================
# 首页
# ============================================================
@app.route("/")
def index():
    """根路由：返回 Vite 构建产物（Vue 3 + Vite）。"""
    dist_ui = PROJECT_ROOT / "tools" / "dist-ui" / "index.html"
    if dist_ui.exists():
        return send_file(dist_ui)
    return "Frontend not built. Run: cd frontend && npm run build-only", 503


@app.route("/assets/<path:filename>")
def dist_assets(filename):
    """Vite 构建产物（JS/CSS chunk）。"""
    from flask import send_from_directory
    return send_from_directory(PROJECT_ROOT / "tools" / "dist-ui" / "assets", filename)


@app.route("/api/version", methods=["GET"])
def api_version():
    """返回应用版本号。构建时由 build.py 写入 tools/dist-ui/version.json。"""
    import json
    version_file = PROJECT_ROOT / "tools" / "dist-ui" / "version.json"
    if version_file.exists():
        try:
            with open(version_file, "r", encoding="utf-8") as f:
                return jsonify(json.load(f))
        except Exception:
            pass
    return jsonify({"version": "dev", "build_time": ""})


# ============================================================
# Env 配置 API（向后兼容：从 llm.yaml + mcp.yaml 合并读写）
# ============================================================
@app.route("/api/env", methods=["GET"])
def get_env():
    """返回合并后的配置（llm.yaml + mcp.yaml）。"""
    try:
        llm_data = load_env_config_file(_ensure_llm_file())
        mcp_data = load_env_config_file(_ensure_mcp_config_file())
        merged = {}
        for k in LLM_TOP_KEYS:
            if k in llm_data:
                merged[k] = llm_data[k]
        merged["mcp"] = (mcp_data or {}).get("mcp", {})
        if isinstance(llm_data, dict) and "_description" in llm_data:
            merged["_description"] = llm_data["_description"]
        return jsonify({"ok": True, "data": merged, "path": "llm.yaml + mcp.yaml"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/env", methods=["POST"])
def save_env():
    """向后兼容：将合并配置拆分保存到 llm.yaml + mcp.yaml。"""
    body = request.get_json(force=True)
    data = body.get("data")
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "data 必须是对象"}), 400
    try:
        llm_data = {k: v for k, v in data.items() if k in LLM_TOP_KEYS}
        if "_description" in data:
            llm_data["_description"] = data["_description"]
        mcp_data = {"mcp": data.get("mcp", {})}
        save_env_config_file(_ensure_llm_file(), llm_data)
        save_env_config_file(_ensure_mcp_config_file(), mcp_data)
        return jsonify({"ok": True, "path": "llm.yaml + mcp.yaml"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# LLM Provider 配置 API (llm.yaml)
# ============================================================
@app.route("/api/llm", methods=["GET"])
def get_llm():
    path = _ensure_llm_file()
    try:
        data = load_env_config_file(path)
        return jsonify({
            "ok": True,
            "data": data,
            "path": str(path.relative_to(PROJECT_ROOT)),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/llm", methods=["POST"])
def save_llm():
    body = request.get_json(force=True)
    data = body.get("data")
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "data 必须是对象"}), 400
    try:
        path = _ensure_llm_file()
        save_env_config_file(path, data)
        return jsonify({"ok": True, "path": str(path.relative_to(PROJECT_ROOT))})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# MCP 配置 API (mcp.yaml - 密钥层)
# ============================================================
@app.route("/api/mcp-config", methods=["GET"])
def get_mcp_config():
    path = _ensure_mcp_config_file()
    try:
        full = _load_mcp_yaml_full()
        return jsonify({
            "ok": True,
            "data": {"mcp": full.get("mcp", {})},
            "path": str(path.relative_to(PROJECT_ROOT)),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/mcp-config", methods=["POST"])
def save_mcp_config():
    body = request.get_json(force=True)
    data = body.get("data")
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "data 必须是对象"}), 400
    try:
        full = _load_mcp_yaml_full()
        full["mcp"] = data.get("mcp", {})
        _save_mcp_yaml_full(full)
        return jsonify({"ok": True, "path": str(MCP_CONFIG_FILE.relative_to(PROJECT_ROOT))})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/mcp-config/key", methods=["POST"])
def add_mcp_config_key():
    """添加单个 MCP 密钥条目。Body: {key, value=''}"""
    body = request.get_json(force=True)
    key = (body.get("key") or "").strip()
    if not key:
        return jsonify({"ok": False, "error": "key 必填"}), 400
    try:
        full = _load_mcp_yaml_full()
        if not isinstance(full.get("mcp"), dict):
            full["mcp"] = {}
        full["mcp"][key] = body.get("value", "")
        _save_mcp_yaml_full(full)
        return jsonify({"ok": True, "key": key})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/mcp-config/key/<key>", methods=["DELETE"])
def delete_mcp_config_key(key):
    try:
        full = _load_mcp_yaml_full()
        if isinstance(full.get("mcp"), dict) and key in full["mcp"]:
            del full["mcp"][key]
            _save_mcp_yaml_full(full)
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": f"未找到 key: {key}"}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# Skills API
# ============================================================
@app.route("/api/skills/local", methods=["GET"])
def list_local_skills():
    """列出本地预置技能：仅返回 template/skills/ 下有 SKILL.md 的技能。

    CSV 提供 category/role/description 等元信息；
    目录扫描确保所有实际存在的本地 skill 都能展示。
    不含 remote 类型（远程技能在市场搜索中获取）。
    """
    rows = []
    csv_map: dict[str, dict] = {}
    if SKILLS_CSV.exists():
        with open(SKILLS_CSV, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get("skill_name") or row.get("name") or ""
                if name:
                    csv_map[name] = row

    # 仅扫描 template/skills/ 下有 SKILL.md 的目录
    if AGENTS_SKILLS_CACHE.exists():
        for d in sorted(AGENTS_SKILLS_CACHE.iterdir()):
            if not d.is_dir() or not (d / "SKILL.md").exists():
                continue
            name = d.name
            if name in csv_map:
                # CSV 中有元信息，合并
                row = dict(csv_map[name])
                row["skill_name"] = name
                rows.append(row)
            else:
                # CSV 中未登记，用基本信息
                rows.append({
                    "skill_name": name,
                    "category": "",
                    "role": "",
                    "description": "",
                    "trigger_keywords": "",
                    "installable": "false",
                    "source_type": "local",
                    "source": name,
                    "url": "",
                    "market_channel": "",
                    "short_name": name,
                })
    return jsonify({"ok": True, "data": rows})


@app.route("/api/skills/installed", methods=["GET"])
def list_installed_skills():
    enabled_set = get_enabled_skills(SKILL_YAML)
    installed = []
    # 只扫描当前项目 config/skills/（~/.agents/skills/ 是用户级共享目录，不在此展示）
    if PROJECT_SKILLS_DIR.exists():
        for d in PROJECT_SKILLS_DIR.iterdir():
            if not d.is_dir() or not (d / "SKILL.md").exists():
                continue
            installed.append({
                "name": d.name,
                "path": str(d.relative_to(PROJECT_ROOT)),
                "skill_md_exists": True,
                "enabled": d.name in enabled_set,
            })
    return jsonify({"ok": True, "data": installed})


@app.route("/api/skills/<name>/toggle", methods=["POST"])
def toggle_skill_enabled(name):
    """切换技能启用状态：启用/禁用并自动同步到选定 IDE。
    Body: { enabled: true|false, ides: ["Codex", "Claude"] }
    """
    body = request.get_json(silent=True) or {}
    enabled = bool(body.get("enabled", True))
    ides = body.get("ides") or []
    if not isinstance(ides, list):
        ides = []
    # 安全校验 IDE 名
    allowed_ides = {"Agents", "Claude", "Codex", "Cursor", "IDEA", "OpenClaw",
                    "OpenCode", "Qoder", "QoderCN", "Trae", "TraeCN", "TraeSoloCN", "WorkBuddy",
                    "ZCode", "All"}
    safe_ides = [i for i in ides if i in allowed_ides]

    try:
        if enabled:
            enable_skill(SKILL_YAML, name)
        else:
            disable_skill(SKILL_YAML, name)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    # 自动同步到选定 IDE（scope=skill）
    sync_logs = []
    if safe_ides:
        ide_arg = "All" if "All" in safe_ides else ",".join(safe_ides)
        try:
            cmd = _script_run_cmd("agentctl", ["sync", "--ide", ide_arg, "--force", "--scope", "skill"])
            result = subprocess.run(
                cmd, cwd=str(PROJECT_ROOT),
                capture_output=True, text=True,
                encoding="utf-8", errors="ignore",
                timeout=120,
            )
            sync_logs.append(result.stdout or "")
            if result.returncode != 0:
                sync_logs.append("[WARN] " + (result.stderr or ""))
        except Exception as e:
            sync_logs.append(f"[ERROR] sync 失败: {e}")

    return jsonify({
        "ok": True,
        "name": name,
        "enabled": enabled,
        "synced_ides": safe_ides,
        "sync_log": "\n".join(sync_logs).strip(),
    })


@app.route("/api/skills/search", methods=["GET"])
def search_skills():
    """聚合搜索: source=modelscope|skillssh|all"""
    q = request.args.get("q", "").strip()
    source = request.args.get("source", "all")
    if not q:
        return jsonify({"ok": False, "error": "缺少 q 参数"}), 400

    results = []
    errors = []

    if source in ("modelscope", "all"):
        try:
            resp = requests.get(
                MODELSCOPE_SKILLS_API,
                params={"page_number": 1, "page_size": 30, "search": q},
                timeout=HTTP_TIMEOUT,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            payload = resp.json()
            data = payload.get("data") or payload
            items = data.get("skills") or data.get("list") or []
            for it in items:
                results.append({
                    "source": "modelscope",
                    "name": it.get("name") or it.get("skill_name") or "",
                    "description": it.get("description") or it.get("chinese_description") or "",
                    "install_command": it.get("install_command") or "",
                    "install_count": it.get("install_count") or it.get("download_count") or 0,
                    "author": it.get("owner") or it.get("author") or "",
                    "license": it.get("license") or "",
                    "raw": it,
                })
        except Exception as e:
            errors.append(f"ModelScope: {e}")

    if source in ("skillssh", "all"):
        try:
            resp = requests.get(
                SKILLS_SH_API,
                params={"q": q},
                timeout=HTTP_TIMEOUT,
            )
            resp.raise_for_status()
            payload = resp.json()
            items = payload.get("skills") or payload.get("data") or []
            if isinstance(items, dict):
                items = list(items.values())
            for it in items:
                if not isinstance(it, dict):
                    continue
                results.append({
                    "source": "skillssh",
                    "name": it.get("name") or it.get("title") or "",
                    "description": it.get("description") or "",
                    "install_command": f"npx skills add {it.get('source', '')}".strip(),
                    "install_count": it.get("install_count") or 0,
                    "author": it.get("owner") or "",
                    "license": "",
                    "raw": it,
                })
        except Exception as e:
            errors.append(f"skills.sh: {e}")

    return jsonify({"ok": True, "data": results, "errors": errors})


@app.route("/api/skills/install", methods=["GET"])
def install_skill_sse():
    """SSE: 流式安装 skill。
    Query: source=owner/repo[&skill=name] 或 command=完整 npx 命令
    """
    source = request.args.get("source", "").strip()
    skill = request.args.get("skill", "").strip()
    command = request.args.get("command", "").strip()

    # 本地预置技能：直接从 template/skills/ 复制到 config/skills/
    if source.startswith("local:"):
        skill_name = source[6:] or skill
        if not skill_name:
            return Response("data: [ERROR] 缺少技能名\n\n", mimetype="text/event-stream")
        cache = PROJECT_ROOT / "template" / "skills" / skill_name
        target = DOT_AGENTS_SKILLS / skill_name
        def _local_copy():
            if not cache.exists() or not (cache / "SKILL.md").exists():
                yield f"data: [ERROR] 本地预置技能不存在: {skill_name}\n\n"
                return
            if target.exists():
                yield f"data: [-] 技能已存在，跳过: {skill_name}\n\n"
                yield f"data: [OK] {skill_name} (already installed)\n\n"
                return
            try:
                import shutil
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(cache, target, ignore=shutil.ignore_patterns('.git'))
                yield f"data: [OK] Skill copied from template: {skill_name}\n\n"
            except Exception as e:
                yield f"data: [ERROR] 复制失败: {e}\n\n"
        return Response(stream_with_context(_local_copy()), mimetype="text/event-stream")

    if command:
        cmd = command
        skill_name = skill or "custom"
    else:
        if not source:
            return Response("data: [ERROR] 缺少 source 或 command\n\n", mimetype="text/event-stream")
        # 构造 npx skills add 命令（强制 --copy）
        parsed_source, parsed_skill = parse_shorthand(source)
        effective_source = parsed_source or source
        effective_skill = skill or parsed_skill
        if effective_skill:
            cmd = f"npx skills add {effective_source} --skill {effective_skill} --copy -y"
        else:
            cmd = f"npx skills add {effective_source} --copy -y"
        skill_name = effective_skill or effective_source

    return Response(
        stream_with_context(_stream_process(cmd, cwd=PROJECT_ROOT)),
        mimetype="text/event-stream",
    )


@app.route("/api/skills/<name>", methods=["DELETE"])
def uninstall_skill(name):
    target = DOT_AGENTS_SKILLS / name
    if not target.exists() or not target.is_dir():
        return jsonify({"ok": False, "error": f"未找到技能: {name}"}), 404
    # 防路径穿越
    try:
        target.resolve().relative_to(DOT_AGENTS_SKILLS.resolve())
    except ValueError:
        return jsonify({"ok": False, "error": "非法路径"}), 400
    try:
        shutil.rmtree(target)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/skills/<name>/skillmd", methods=["GET"])
def get_skill_md(name):
    target = DOT_AGENTS_SKILLS / name / "SKILL.md"
    if not target.exists():
        return jsonify({"ok": False, "error": "SKILL.md 不存在"}), 404
    try:
        content = target.read_text(encoding="utf-8")
        return jsonify({"ok": True, "content": content})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# MCP API
# ============================================================
@app.route("/api/mcp/list", methods=["GET"])
def mcp_list():
    full = _load_mcp_yaml_full()
    data = {"mcpServers": full.get("mcpServers", {})}
    return jsonify({"ok": True, "data": data, "path": str(MCP_CONFIG_FILE.relative_to(PROJECT_ROOT))})


@app.route("/api/mcp/save", methods=["POST"])
def mcp_save():
    body = request.get_json(force=True)
    data = body.get("data")
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "data 必须是对象"}), 400
    try:
        full = _load_mcp_yaml_full()
        full["mcpServers"] = data.get("mcpServers", data)
        _save_mcp_yaml_full(full)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/mcp/search", methods=["GET"])
def mcp_search():
    q = request.args.get("q", "").strip()
    page = int(request.args.get("page", 1))
    if not q:
        return jsonify({"ok": False, "error": "缺少 q 参数"}), 400
    try:
        # ModelScope 列表用 PUT
        resp = requests.put(
            MODELSCOPE_MCP_LIST_API,
            json={"page_number": page, "page_size": 20, "search": q},
            headers={"Content-Type": "application/json"},
            timeout=HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
        data = payload.get("data") or payload
        servers = data.get("servers") or data.get("list") or []
        results = []
        for s in servers:
            sid = s.get("id") or s.get("mcp_server_id") or ""
            # id 格式 @owner/name
            owner = ""
            name = s.get("name") or s.get("en_name") or ""
            if sid.startswith("@") and "/" in sid:
                owner = sid[1:].split("/")[0]
            results.append({
                "id": sid,
                "name": name,
                "owner": owner,
                "description": s.get("description") or s.get("chinese_description") or "",
                "author": s.get("author") or owner,
                "categories": s.get("categories") or [],
                "is_hosted": s.get("is_hosted", False),
                "raw": s,
            })
        return jsonify({"ok": True, "data": results, "total": data.get("total_count", 0)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/mcp/detail", methods=["GET"])
def mcp_detail():
    owner = request.args.get("owner", "").strip()
    name = request.args.get("name", "").strip()
    if not owner or not name:
        return jsonify({"ok": False, "error": "缺少 owner/name"}), 400
    try:
        url = MODELSCOPE_MCP_DETAIL_API.format(owner=owner, name=name)
        resp = requests.get(
            url,
            params={"get_operational_url": "true"},
            headers={"Content-Type": "application/json"},
            timeout=HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
        data = payload.get("data") or payload
        return jsonify({"ok": True, "data": data})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# Plugin API
# ============================================================
@app.route("/api/plugins", methods=["GET"])
def list_plugins():
    from lib.plugins import read_installed_plugins
    installed_names = set(read_installed_plugins(PROJECT_ROOT))
    plugins = []
    if PLUGINS_DIR.exists():
        # 支持 .plugin.yaml / .plugin.yml / .plugin.json
        files = []
        for pat in ("*.plugin.yaml", "*.plugin.yml", "*.plugin.json"):
            files.extend(PLUGINS_DIR.glob(pat))
        for f in sorted(files):
            try:
                cfg = load_env_config_file(f)
                if isinstance(cfg, dict) and "name" in cfg:
                    plugins.append({
                        "file": f.name,
                        "name": cfg.get("name"),
                        "version": cfg.get("version", ""),
                        "description": cfg.get("description", ""),
                        "skills_count": len(cfg.get("skills", [])),
                        "mcp_count": len(cfg.get("mcpServers", {})),
                        "installed": cfg.get("name") in installed_names,
                    })
            except Exception:
                continue
    return jsonify({"ok": True, "data": plugins})


@app.route("/api/plugin/save", methods=["POST"])
def save_plugin():
    body = request.get_json(force=True)
    name = body.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "name 必填"}), 400
    config = {
        "name": name,
        "version": body.get("version", "1.0.0").strip() or "1.0.0",
        "description": body.get("description", "").strip(),
        "author": body.get("author", "AgentBuddy").strip() or "AgentBuddy",
        "mcpServers": body.get("mcpServers", {}),
        "skills": body.get("skills", []),
        "llm": body.get("llm", []),
    }
    # 可选：初始化脚本（install script）
    scripts = body.get("scripts")
    if isinstance(scripts, dict) and scripts.get("install", "").strip():
        config["scripts"] = {"install": scripts["install"].strip()}
    # 安全文件名
    safe_name = "".join(c for c in name if c.isalnum() or c in ("-", "_"))
    out_path = PLUGINS_DIR / f"{safe_name}.plugin.yaml"
    try:
        save_env_config_file(out_path, config)
        return jsonify({"ok": True, "path": str(out_path.relative_to(PROJECT_ROOT))})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/plugin/load", methods=["GET"])
def load_plugin():
    """加载完整 plugin 配置。Query: file=xxx.plugin.yaml"""
    fname = request.args.get("file", "").strip()
    if not fname:
        return jsonify({"ok": False, "error": "缺少 file 参数"}), 400
    path = (PLUGINS_DIR / fname).resolve()
    try:
        path.relative_to(PLUGINS_DIR.resolve())
    except ValueError:
        return jsonify({"ok": False, "error": "非法路径"}), 400
    if not path.exists():
        return jsonify({"ok": False, "error": "文件不存在"}), 404
    try:
        data = load_env_config_file(path)
        return jsonify({"ok": True, "data": data, "path": str(path.relative_to(PROJECT_ROOT))})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/plugin/delete", methods=["POST"])
def delete_plugin():
    """删除 plugin 配置。Body: {file: xxx.plugin.yaml}"""
    body = request.get_json(force=True)
    fname = (body.get("file") or "").strip()
    if not fname:
        return jsonify({"ok": False, "error": "缺少 file 参数"}), 400
    path = (PLUGINS_DIR / fname).resolve()
    try:
        path.relative_to(PLUGINS_DIR.resolve())
    except ValueError:
        return jsonify({"ok": False, "error": "非法路径"}), 400
    if not path.exists():
        return jsonify({"ok": False, "error": "文件不存在"}), 404
    try:
        path.unlink()
        return jsonify({"ok": True, "path": str(path.relative_to(PROJECT_ROOT))})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/plugin/export", methods=["GET"])
def export_plugin():
    """导出单个插件 yaml。query: file=xxx.plugin.yaml"""
    fname = (request.args.get("file") or "").strip()
    if not fname:
        return jsonify({"ok": False, "error": "缺少 file 参数"}), 400
    path = (PLUGINS_DIR / fname).resolve()
    try:
        path.relative_to(PLUGINS_DIR.resolve())
    except ValueError:
        return jsonify({"ok": False, "error": "非法路径"}), 400
    if not path.exists():
        return jsonify({"ok": False, "error": "文件不存在"}), 404
    try:
        import io
        buf = io.BytesIO(path.read_bytes())
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name=fname,
                         mimetype="application/yaml")
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/plugin/export-all", methods=["GET"])
def export_all_plugins():
    """导出全部预定义插件为 zip。"""
    import io, zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if PLUGINS_DIR.exists():
            for f in PLUGINS_DIR.glob("*.plugin.yaml"):
                zf.write(f, arcname=f.name)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="plugins-export.zip",
                     mimetype="application/zip")


@app.route("/api/plugin/import", methods=["POST"])
def import_plugin():
    """导入插件 yaml。Body: {filename: 'xxx.plugin.yaml', content: '...'}
    会校验 yaml 合法性 + 文件名安全 + 是否重名。
    """
    body = request.get_json(force=True)
    fname = (body.get("filename") or "").strip()
    content = body.get("content") or ""
    if not fname:
        return jsonify({"ok": False, "error": "缺少 filename"}), 400
    if not fname.endswith(".plugin.yaml"):
        return jsonify({"ok": False, "error": "文件名必须以 .plugin.yaml 结尾"}), 400
    safe_name = "".join(c for c in fname if c.isalnum() or c in ("-", "_", "."))
    if safe_name != fname:
        return jsonify({"ok": False, "error": "文件名含非法字符"}), 400
    # yaml 校验
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        return jsonify({"ok": False, "error": f"YAML 解析失败: {e}"}), 400
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "yaml 顶层应为 dict"}), 400
    if not data.get("name"):
        return jsonify({"ok": False, "error": "缺少 name 字段"}), 400
    out_path = PLUGINS_DIR / safe_name
    overwrite = bool(body.get("overwrite"))
    if out_path.exists() and not overwrite:
        return jsonify({"ok": False, "error": "exists",
                        "msg": f"{safe_name} 已存在，是否覆盖？"}), 409
    try:
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        return jsonify({"ok": True, "path": str(out_path.relative_to(PROJECT_ROOT)),
                        "name": data.get("name")})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/plugin/uninstall", methods=["POST"])
def uninstall_plugin_api():
    """卸载插件：从清单移除 + 删除已安装 skill + generate + sync。
    Body: { name: "plugin-name", ides: ["Codex", "Claude"] }
    """
    from lib.plugins import remove_from_installed
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "缺少 name 参数"}), 400
    ides = body.get("ides") or []
    allowed_ides = {"Agents", "Claude", "Codex", "Cursor", "IDEA", "OpenClaw",
                    "OpenCode", "Qoder", "QoderCN", "Trae", "TraeCN", "TraeSoloCN", "WorkBuddy",
                    "ZCode", "All"}
    safe_ides = [i for i in ides if i in allowed_ides]

    # 1. 从已安装清单移除
    try:
        remove_from_installed(PROJECT_ROOT, name)
    except Exception as e:
        return jsonify({"ok": False, "error": f"移除清单失败: {e}"}), 500

    # 2. 删除 config/skills/ 下该插件关联的 skill（通过查找 plugin.yaml 获取 skills 列表）
    # 查找对应的 plugin.yaml
    plugin_file = None
    if PLUGINS_DIR.exists():
        for pat in ("*.plugin.yaml", "*.plugin.yml", "*.plugin.json"):
            for f in PLUGINS_DIR.glob(pat):
                try:
                    cfg = load_env_config_file(f)
                    if isinstance(cfg, dict) and cfg.get("name") == name:
                        plugin_file = f
                        break
                except Exception:
                    continue
            if plugin_file:
                break

    deleted_skills = []
    if plugin_file:
        try:
            cfg = load_env_config_file(plugin_file)
            skills_list = cfg.get("skills", []) or []
            for s in skills_list:
                skill_name = s.get("skill") or s.get("name") if isinstance(s, dict) else str(s)
                if skill_name:
                    skill_dir = DOT_AGENTS_SKILLS / skill_name
                    if skill_dir.exists():
                        import shutil
                        shutil.rmtree(skill_dir, ignore_errors=True)
                        deleted_skills.append(skill_name)
        except Exception:
            pass

    # 3. generate 刷新 mcp.json（移除已卸载插件的 mcpServers）
    try:
        subprocess.run(
            _script_run_cmd("agentctl", ["generate"]),
            cwd=str(PROJECT_ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="ignore", timeout=60,
        )
    except Exception:
        pass

    # 4. sync 到选定 IDE
    sync_logs = []
    if safe_ides:
        ide_list = safe_ides if "All" not in safe_ides else ["All"]
        for ide_arg in ide_list:
            try:
                subprocess.run(
                    _script_run_cmd("agentctl", ["sync", "--ide", ide_arg, "--force"]),
                    cwd=str(PROJECT_ROOT), capture_output=True, text=True,
                    encoding="utf-8", errors="ignore", timeout=120,
                )
            except Exception as e:
                sync_logs.append(f"[ERROR] {ide_arg} sync: {e}")

    return jsonify({
        "ok": True,
        "name": name,
        "deleted_skills": deleted_skills,
        "synced_ides": safe_ides,
    })


@app.route("/api/plugin/import-from-ide", methods=["GET"])
def import_from_ide():
    """从本地所有 IDE 配置中扫描 MCP 和 skills，合并去重后返回，供填入插件构建表单。

    扫描范围：
      - MCP: 所有 IDE 的项目级 + 全局级配置文件（JSON / TOML）
      - Skills: 所有 IDE 的全局 skills 目录 + config/skills/
    合并策略：同名 MCP/Skill 首次出现保留，记录来源 IDE。
    """
    home = Path.home()
    # 各 IDE 的 MCP 配置文件（项目级 + 全局级），(路径, 格式, ide名)
    mcp_files = [
        # 项目级
        (PROJECT_ROOT / ".mcp.json", "json", "Project(.mcp.json)"),
        (PROJECT_ROOT / ".cursor" / "mcp.json", "json", "Cursor"),
        (PROJECT_ROOT / ".claude" / "mcp.json", "json", "Claude"),
        (PROJECT_ROOT / ".qoder" / "mcp.json", "json", "Qoder"),
        (PROJECT_ROOT / ".openclaw" / "mcp.json", "json", "OpenClaw"),
        (PROJECT_ROOT / ".workbuddy" / "mcp.json", "json", "WorkBuddy"),
        (PROJECT_ROOT / "opencode.json", "json", "OpenCode"),
        (PROJECT_ROOT / ".codex" / "config.toml", "toml", "Codex"),
        # 全局级
        (home / ".cursor" / "mcp.json", "json", "Cursor(global)"),
        (home / ".claude" / "mcp.json", "json", "Claude(global)"),
        (home / ".qoder" / "mcp.json", "json", "Qoder(global)"),
        (home / ".openclaw" / "mcp.json", "json", "OpenClaw(global)"),
        (home / ".workbuddy" / "mcp.json", "json", "WorkBuddy(global)"),
        (home / ".codex" / "config.toml", "toml", "Codex(global)"),
        (home / ".trae" / "mcp.json", "json", "Trae(global)"),
        (home / ".traecn" / "mcp.json", "json", "TraeCN(global)"),
        (home / ".traesolocn" / "mcp.json", "json", "TraeSoloCN(global)"),
    ]
    # Trae macOS Application Support 路径
    if sys.platform == "darwin":
        for ide_name in ("Trae", "Trae CN", "Trae Solo CN"):
            user_dir = home / "Library" / "Application Support" / ide_name / "User"
            mcp_files.append((user_dir / "mcp.json", "json", f"{ide_name}(app)"))

    merged_mcp = {}  # name -> config
    mcp_sources = {}  # name -> [ide名]
    scanned_files = []

    for path, fmt, ide_label in mcp_files:
        if not path.exists():
            continue
        scanned_files.append(str(path))
        try:
            servers = {}
            if fmt == "json":
                data = json.loads(path.read_text(encoding="utf-8"))
                # 兼容 {mcpServers:{}} 和顶层直接是 servers 的情况
                if isinstance(data, dict):
                    servers = data.get("mcpServers") or data.get("mcp_servers") or {}
                    # opencode.json 的 mcp 在不同位置
                    if not servers and isinstance(data.get("mcp"), dict):
                        servers = data["mcp"]
            elif fmt == "toml":
                servers = _parse_codex_toml_mcp(path)
            if not isinstance(servers, dict):
                continue
            for name, cfg in servers.items():
                if name in merged_mcp:
                    mcp_sources[name].append(ide_label)
                else:
                    merged_mcp[name] = cfg
                    mcp_sources[name] = [ide_label]
        except Exception:
            continue

    # Skills: 扫描所有 IDE 的全局 skills 目录
    skills_dirs = [
        (home / ".cursor" / "skills", "Cursor"),
        (home / ".claude" / "skills", "Claude"),
        (home / ".codex" / "skills", "Codex"),
        (home / ".qoder" / "skills", "Qoder"),
        (home / ".openclaw" / "skills", "OpenClaw"),
        (home / ".workbuddy" / "skills", "WorkBuddy"),
        (home / ".idea" / "skills", "IDEA"),
        (home / ".config" / "opencode" / "skills", "OpenCode"),
        (home / ".trae" / "skills", "Trae"),
        (home / ".traecn" / "skills", "TraeCN"),
        (home / ".traesolocn" / "skills", "TraeSoloCN"),
        (DOT_AGENTS_SKILLS, "Project(config/skills)"),
    ]
    merged_skills = []  # [{name, sources:[]}]
    skill_name_sources = {}  # name -> [ide名]
    scanned_dirs = []
    for sdir, ide_label in skills_dirs:
        if not sdir.exists():
            continue
        scanned_dirs.append(str(sdir))
        try:
            for d in sdir.iterdir():
                if d.is_dir() and (d / "SKILL.md").exists():
                    if d.name in skill_name_sources:
                        skill_name_sources[d.name].append(ide_label)
                    else:
                        skill_name_sources[d.name] = [ide_label]
        except Exception:
            continue
    merged_skills = [{"name": n, "sources": ss} for n, ss in skill_name_sources.items()]

    # LLM 配置：从项目 llm.yaml 读取已配置的 provider（有 api_key 的算已配置）
    llm_providers = []
    try:
        llm_path = PROJECT_ROOT / "config" / "llm" / "llm.yaml"
        if llm_path.exists():
            llm_data = load_env_config_file(llm_path)
            if isinstance(llm_data, dict):
                llm_section = llm_data.get("llm", {})
                active = llm_section.get("_active_provider", "")
                for prov_name, prov_cfg in llm_section.items():
                    if prov_name.startswith("_") or not isinstance(prov_cfg, dict):
                        continue
                    # 每个 provider 下有 openai/anthropic 等协议
                    for proto, proto_cfg in prov_cfg.items():
                        if not isinstance(proto_cfg, dict):
                            continue
                        api_key = proto_cfg.get("api_key", "")
                        base_url = proto_cfg.get("base_url", "")
                        models = proto_cfg.get("models", {})
                        model_names = list(models.keys()) if isinstance(models, dict) else []
                        llm_providers.append({
                            "provider": prov_name,
                            "protocol": proto,
                            "base_url": base_url,
                            "has_key": bool(api_key),
                            "active": prov_name == active,
                            "models": model_names[:5],  # 最多展示5个
                            "model_count": len(model_names),
                        })
    except Exception:
        pass

    return jsonify({
        "ok": True,
        "mcpServers": merged_mcp,
        "mcp_sources": mcp_sources,
        "skills": merged_skills,
        "llm_providers": llm_providers,
        "scanned_files": scanned_files,
        "scanned_dirs": scanned_dirs,
        "stats": {
            "mcp_count": len(merged_mcp),
            "skill_count": len(merged_skills),
            "llm_count": len(llm_providers),
            "files_scanned": len(scanned_files),
            "dirs_scanned": len(scanned_dirs),
        }
    })


def _parse_codex_toml_mcp(path: Path) -> dict:
    """解析 Codex config.toml 中的 [mcp_servers.xxx] 段，返回 {name: config}。"""
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            return {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        servers = data.get("mcp_servers", {})
        # Codex 格式: {command, args, env}，需转为通用 {command, args, env}
        result = {}
        for name, cfg in servers.items():
            if isinstance(cfg, dict):
                entry = {}
                if "command" in cfg:
                    entry["command"] = cfg["command"]
                if "args" in cfg:
                    entry["args"] = list(cfg["args"]) if isinstance(cfg["args"], (list, tuple)) else [str(cfg["args"])]
                if "env" in cfg and isinstance(cfg["env"], dict):
                    entry["env"] = {k: str(v) for k, v in cfg["env"].items()}
                if entry:
                    result[name] = entry
        return result
    except Exception:
        return {}


@app.route("/api/plugin/install", methods=["GET"])
def install_plugin_sse():
    """SSE: 流式安装插件。Query: file=xxx.plugin.yaml&ide=Codex"""
    fname = request.args.get("file", "").strip()
    if not fname:
        return Response("data: [ERROR] 缺少 file 参数\n\n", mimetype="text/event-stream")
    target_ide = request.args.get("ide", "").strip()  # 空=所有 IDE
    plugin_path = (PLUGINS_DIR / fname).resolve()
    try:
        plugin_path.relative_to(PLUGINS_DIR.resolve())
    except ValueError:
        return Response("data: [ERROR] 非法路径\n\n", mimetype="text/event-stream")
    if not plugin_path.exists():
        return Response(f"data: [ERROR] 文件不存在: {fname}\n\n", mimetype="text/event-stream")

    def gen():
        yield f"data: [PLUGIN] {fname}\n\n"
        yield f"data: [STEP] 加载插件配置\n\n"
        try:
            cfg = load_env_config_file(plugin_path)
            yield f"data:   名称: {cfg.get('name')}\n\n"
            yield f"data:   版本: {cfg.get('version')}\n\n"
            yield f"data:   技能数: {len(cfg.get('skills', []))}\n\n"
        except Exception as e:
            yield f"data: [ERROR] 加载失败: {e}\n\n"
            yield "data: [DONE]\n\n"
            return

        # 复用 install_plugin 的底层步骤（capture 部分输出无法流式，这里直接调用）
        # 注意：plugin.yaml 的 mcpServers 不在此阶段合并，由 agentctl generate
        # 阶段同时读取 mcp.yaml + plugins/*.plugin.yaml 合并生成 mcp.json
        yield f"data: [STEP] 更新 llm.yaml\n\n"
        try:
            env_path = _ensure_llm_file()
            # 重定向 stdout 到管道（update_env_file 内部有 print）
            import contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                update_env_file(env_path, cfg)
            for line in buf.getvalue().splitlines():
                if line.strip():
                    yield f"data: {line}\n\n"
        except Exception as e:
            yield f"data: [ERROR] llm 更新失败: {e}\n\n"

        yield f"data: [STEP] 安装技能\n\n"
        try:
            skills = cfg.get("skills", [])
            for i, sk in enumerate(skills):
                skill_name, cmd = build_install_command(sk, use_symlink=False)
                yield f"data: [{i+1}/{len(skills)}] {skill_name}\n\n"
                # 判断 source 类型
                is_whole_repo = (
                    ' add ' in cmd and '/' in cmd.split(' add ', 1)[1].split(' ', 1)[0]
                    and '--skill' not in cmd
                )
                has_explicit_source = (
                    '--skill' in cmd or cmd.startswith('http')
                    or (' add ' in cmd and '/' in cmd.split(' add ', 1)[1].split(' ', 1)[0])
                )

                # Step 1: 已存在则跳过（仅单技能）
                if not is_whole_repo:
                    target = PROJECT_ROOT / "config" / "skills" / skill_name
                    if target.exists():
                        yield f"data: [-] Skill already exists: {skill_name}, skipping\n\n"
                        continue

                # Step 2: source 有效 → 执行 source 命令
                rc = None
                if has_explicit_source:
                    rc = yield from _stream_process_rc(cmd, cwd=PROJECT_ROOT)
                    if rc == 0:
                        # 验证（整仓库跳过目录验证）
                        if is_whole_repo or (PROJECT_ROOT / "config" / "skills" / skill_name).exists():
                            yield f"data: [OK] Skill installed via source: {skill_name}\n\n"
                            continue
                        yield f"data: [!] source 命令成功但目录未找到，尝试 find-skills\n\n"
                    else:
                        yield f"data: [!] source 安装失败(rc={rc})，尝试 find-skills\n\n"

                # Step 3: find-skills 按名查找
                find_cmd = f"npx skills add {skill_name} -y"
                rc = yield from _stream_process_rc(find_cmd, cwd=PROJECT_ROOT)
                if rc == 0 and (is_whole_repo or (PROJECT_ROOT / "config" / "skills" / skill_name).exists()):
                    yield f"data: [OK] Skill installed from marketplace: {skill_name}\n\n"
                    continue

                # Step 4: 本地缓存（仅单技能）
                if not is_whole_repo:
                    cache = PROJECT_ROOT / "template" / "skills" / skill_name
                    if cache.exists():
                        yield f"data: [-] Copying from local cache: {skill_name}\n\n"
                        try:
                            import shutil
                            target = PROJECT_ROOT / "config" / "skills" / skill_name
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copytree(cache, target, ignore=shutil.ignore_patterns('.git'))
                            yield f"data: [OK] Skill copied from cache: {skill_name}\n\n"
                            continue
                        except Exception as e:
                            yield f"data: [ERROR] cache copy failed: {e}\n\n"

                yield f"data: [FAIL] Skill installation failed: {skill_name}\n\n"
        except Exception as e:
            yield f"data: [ERROR] 技能安装失败: {e}\n\n"

        # 注册到已安装清单（让 generate 合并该插件的 mcpServers）
        yield f"data: [STEP] 注册到已安装清单\n\n"
        try:
            add_to_installed(PROJECT_ROOT, cfg.get("name", ""))
            yield f"data:   已注册: {cfg.get('name', '')}\n\n"
        except Exception as e:
            yield f"data: [ERROR] 注册失败: {e}\n\n"

        # 自动 generate（刷新 mcp.json + config/ide/ 产物）
        yield f"data: [STEP] 生成配置 (generate)\n\n"
        try:
            result = subprocess.run(
                _script_run_cmd("agentctl", ["generate"]),
                cwd=str(PROJECT_ROOT),
                capture_output=True, text=True,
                encoding="utf-8", errors="ignore",
                timeout=60,
            )
            if result.returncode == 0:
                yield f"data:   generate 完成\n\n"
            else:
                yield f"data: [WARN] generate 有警告: {result.stderr[-500:]}\n\n"
        except Exception as e:
            yield f"data: [ERROR] generate 失败: {e}\n\n"

        # 自动 sync（按 target_ide 或所有 IDE；支持逗号分隔多 IDE）
        ide_list = [i.strip() for i in target_ide.split(",") if i.strip()] if target_ide else ["All"]
        for ide_arg in ide_list:
            yield f"data: [STEP] 同步到 IDE: {ide_arg}\n\n"
            try:
                result = subprocess.run(
                    _script_run_cmd("agentctl", ["sync", "--ide", ide_arg, "--force"]),
                    cwd=str(PROJECT_ROOT),
                    capture_output=True, text=True,
                    encoding="utf-8", errors="ignore",
                    timeout=120,
                )
                if result.returncode == 0:
                    # 提取关键输出行
                    for line in result.stdout.splitlines():
                        if "[OK]" in line or "[DONE]" in line or "Synced" in line:
                            yield f"data:   {line.strip()}\n\n"
                    yield f"data:   {ide_arg} sync 完成\n\n"
                else:
                    yield f"data: [WARN] {ide_arg} sync 有警告: {result.stderr[-500:]}\n\n"
            except Exception as e:
                yield f"data: [ERROR] {ide_arg} sync 失败: {e}\n\n"

        yield "data: [DONE] 插件安装并同步完成\n\n"

    return Response(stream_with_context(gen()), mimetype="text/event-stream")


# ============================================================
# init-env / init-ide 触发
# ============================================================
@app.route("/api/init-env", methods=["POST"])
def trigger_init_env():
    """触发 agentctl generate（原 init-env.py -a Generate）"""
    try:
        result = subprocess.run(
            _script_run_cmd("agentctl", ["generate"]),
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=60,
        )
        return jsonify({
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout[-2000:],
            "stderr": result.stderr[-2000:],
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/init-ide", methods=["GET"])
def trigger_init_ide_sse():
    """SSE: 触发 agentctl sync --ide <ide> --force --scope <scope>"""
    ide = request.args.get("ide", "All")
    scope = request.args.get("scope", "llm,mcp,skill,plugin").strip()
    # 白名单校验，防止注入
    allowed = {"llm", "mcp", "skill", "plugin", "rules"}
    scopes = [s.strip().lower() for s in scope.split(",") if s.strip().lower() in allowed]
    if not scopes:
        scopes = ["llm", "mcp", "skill", "plugin"]
    scope_arg = ",".join(scopes)
    cmd_args = ["sync", "--ide", ide, "--force", "--scope", scope_arg]
    # 可选：仅同步勾选的技能（逗号分隔的技能名）
    skills = request.args.get("skills", "").strip()
    if skills:
        # 仅保留安全字符（字母、数字、-、_、逗号、空格），防止注入
        safe_skills = ",".join(s.strip() for s in skills.split(",") if s.strip() and all(c.isalnum() or c in "-_ " for c in s.strip()))
        if safe_skills:
            cmd_args += ["--skills", safe_skills]
    cmd = _script_run_shell_cmd("agentctl", cmd_args)
    return Response(
        stream_with_context(_stream_process(cmd, cwd=PROJECT_ROOT)),
        mimetype="text/event-stream",
    )


@app.route("/api/proxy/start", methods=["GET"])
def start_proxy_sse():
    """SSE: 启动 LLM 代理服务（litellm）。
    Query: cmd=启动命令（默认 litellm --config proxy/config.yaml --port 4000）
    """
    cmd = request.args.get("cmd", "").strip()
    if not cmd:
        cmd = "litellm --config proxy/config.yaml --port 4000"
    # 代理服务是长期运行进程，直接流式输出直到用户中断或进程退出
    return Response(
        stream_with_context(_stream_process(cmd, cwd=PROJECT_ROOT)),
        mimetype="text/event-stream",
    )


# ============================================================
# IDE 管理 API：检测 / 启动 / 会话扫描 / 会话恢复 / 会话共享
# ============================================================

@app.route("/api/ide/detect", methods=["GET"])
def api_ide_detect():
    """检测所有 IDE 安装状态。

    Returns:
        {ok, ides: [{key, label, installed, exe_path, app_path, version, config_paths, sessions_dir}], stats}
    """
    try:
        ides = detect_all()
        installed_count = sum(1 for i in ides if i["installed"])
        return jsonify({
            "ok": True,
            "ides": ides,
            "stats": {
                "total": len(ides),
                "installed": installed_count,
                "not_installed": len(ides) - installed_count,
            },
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/ide/sessions", methods=["GET"])
def api_ide_sessions():
    """列出指定 IDE 的会话。

    Query: ide=<IDE key>&limit=<N, 默认 50>
    """
    ide_key = request.args.get("ide", "").strip()
    if not ide_key:
        return jsonify({"ok": False, "error": "missing ide parameter"}), 400
    try:
        limit = int(request.args.get("limit", "50"))
    except ValueError:
        limit = 50
    try:
        info = detect_ide(ide_key)
        if not info["installed"]:
            return jsonify({"ok": False, "error": f"IDE {ide_key} not installed"}), 404
        sessions_dir = info.get("sessions_dir", "")
        if not sessions_dir:
            return jsonify({"ok": True, "sessions": [], "ide": ide_key, "sessions_dir": "",
                            "stats": {"total": 0}})
        sessions = list_sessions(ide_key, sessions_dir)
        # 应用 limit
        truncated = len(sessions) > limit
        sessions = sessions[:limit]
        return jsonify({
            "ok": True,
            "ide": ide_key,
            "sessions_dir": sessions_dir,
            "sessions": sessions,
            "stats": {
                "total": len(sessions),
                "truncated": truncated,
            },
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/ide/launch", methods=["POST"])
def api_ide_launch():
    """启动 IDE。

    Body: {ide: <IDE key>, cwd?: <工作目录>, session_id?: <会话 ID>, mode?: "cli"|"app"|""}
    """
    body = request.get_json(silent=True) or {}
    ide_key = (body.get("ide") or "").strip()
    if not ide_key:
        return jsonify({"ok": False, "error": "missing ide"}), 400
    cwd = (body.get("cwd") or "").strip()
    session_id = (body.get("session_id") or "").strip()
    mode = (body.get("mode") or "").strip()
    try:
        if session_id:
            result = launch_ide_resume_session(ide_key, session_id, cwd, mode=mode)
        else:
            result = launch_ide(ide_key, cwd, mode=mode)
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/ide/open-config", methods=["POST"])
def api_ide_open_config():
    """打开 IDE 的全局配置目录（用系统文件管理器）。

    Body: {ide: <IDE key>}
    Returns: {ok, ide, path, error}
    """
    body = request.get_json(silent=True) or {}
    ide_key = (body.get("ide") or "").strip()
    if not ide_key:
        return jsonify({"ok": False, "error": "missing ide"}), 400
    try:
        info = detect_ide(ide_key)
        config_paths = info.get("config_paths") or []
        if not config_paths:
            return jsonify({"ok": False, "ide": ide_key, "path": "",
                            "error": f"IDE {ide_key} 无配置目录"}), 404
        target = config_paths[0]
        import subprocess, sys, os
        if sys.platform == "win32":
            # explorer.exe 直接打开目录；CREATE_NO_WINDOW 避免黑窗
            subprocess.Popen(["explorer.exe", target],
                             creationflags=0x08000000)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])
        return jsonify({"ok": True, "ide": ide_key, "path": target, "error": ""})
    except Exception as e:
        return jsonify({"ok": False, "ide": ide_key, "path": "",
                        "error": str(e)}), 500


@app.route("/api/ide/install", methods=["POST"])
def api_ide_install():
    """安装 IDE（CLI 或 App）。

    Body: {ide: <IDE key>, mode: "cli" | "app"}
    Returns: {ok, ide, mode, method, message, cmd, stdout, stderr, url?}
    """
    body = request.get_json(silent=True) or {}
    ide_key = (body.get("ide") or "").strip()
    mode = (body.get("mode") or "cli").strip()
    if not ide_key:
        return jsonify({"ok": False, "error": "missing ide"}), 400
    if mode not in ("cli", "app"):
        return jsonify({"ok": False, "error": "mode must be 'cli' or 'app'"}), 400
    if ide_key not in IDE_INSTALL_META:
        return jsonify({"ok": False, "error": f"unsupported IDE: {ide_key}"}), 400
    try:
        result = install_ide(ide_key, mode)
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/ide/uninstall", methods=["POST"])
def api_ide_uninstall():
    """卸载 IDE（CLI 或 App）。

    Body: {ide: <IDE key>, mode: "cli" | "app"}
    """
    body = request.get_json(silent=True) or {}
    ide_key = (body.get("ide") or "").strip()
    mode = (body.get("mode") or "cli").strip()
    if not ide_key:
        return jsonify({"ok": False, "error": "missing ide"}), 400
    if mode not in ("cli", "app"):
        return jsonify({"ok": False, "error": "mode must be 'cli' or 'app'"}), 400
    if ide_key not in IDE_INSTALL_META:
        return jsonify({"ok": False, "error": f"unsupported IDE: {ide_key}"}), 400
    try:
        result = uninstall_ide(ide_key, mode)
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/ide/reinstall", methods=["POST"])
def api_ide_reinstall():
    """重装 IDE（先卸载再安装）。

    Body: {ide: <IDE key>, mode: "cli" | "app"}
    """
    body = request.get_json(silent=True) or {}
    ide_key = (body.get("ide") or "").strip()
    mode = (body.get("mode") or "cli").strip()
    if not ide_key:
        return jsonify({"ok": False, "error": "missing ide"}), 400
    if mode not in ("cli", "app"):
        return jsonify({"ok": False, "error": "mode must be 'cli' or 'app'"}), 400
    if ide_key not in IDE_INSTALL_META:
        return jsonify({"ok": False, "error": f"unsupported IDE: {ide_key}"}), 400
    try:
        result = reinstall_ide(ide_key, mode)
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/ide/install-info", methods=["GET"])
def api_ide_install_info():
    """获取所有 IDE 的安装元信息。

    Query: ide=<IDE key>（可选，不传返回全部）
    """
    ide_key = request.args.get("ide", "").strip()
    try:
        if ide_key:
            return jsonify({"ok": True, "info": get_install_info(ide_key)})
        infos = [{"ide": k, **get_install_info(k)} for k in IDE_INSTALL_META.keys()]
        return jsonify({"ok": True, "infos": infos})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/ide/session/export", methods=["GET"])
def api_ide_session_export():
    """导出会话为通用 JSON 格式（用于跨 IDE 共享）。

    Query: ide=<IDE key>&session_id=<会话 ID>
    """
    ide_key = request.args.get("ide", "").strip()
    session_id = request.args.get("session_id", "").strip()
    if not ide_key or not session_id:
        return jsonify({"ok": False, "error": "missing ide or session_id"}), 400
    try:
        info = detect_ide(ide_key)
        if not info["installed"]:
            return jsonify({"ok": False, "error": f"IDE {ide_key} not installed"}), 404
        sessions = list_sessions(ide_key, info.get("sessions_dir", ""))
        target = next((s for s in sessions if s["id"] == session_id), None)
        if not target:
            return jsonify({"ok": False, "error": "session not found"}), 404
        exported = export_session(target)
        return jsonify({
            "ok": True,
            "session": exported,
            "download_filename": f"session-{ide_key}-{session_id[:8]}.json",
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/ide/session/import", methods=["POST"])
def api_ide_session_import():
    """将通用会话格式导入到目标 IDE（写为 markdown 摘要）。

    Body: {session: <exported session dict>, target_ide: <IDE key>}
    """
    body = request.get_json(silent=True) or {}
    session_data = body.get("session")
    target_ide = (body.get("target_ide") or "").strip()
    if not session_data or not target_ide:
        return jsonify({"ok": False, "error": "missing session or target_ide"}), 400
    try:
        info = detect_ide(target_ide)
        if not info["installed"]:
            return jsonify({"ok": False, "error": f"IDE {target_ide} not installed"}), 404
        # 写入目标 IDE 的 sessions 目录下的 imported 子目录
        sessions_dir = info.get("sessions_dir", "")
        if not sessions_dir:
            return jsonify({"ok": False, "error": f"IDE {target_ide} has no sessions_dir"}), 400
        target_dir = Path(sessions_dir) / "imported"
        out_file = import_session_to_ide(session_data, target_ide, str(target_dir))
        return jsonify({
            "ok": True,
            "file": out_file,
            "target_ide": target_ide,
            "messages_count": len(session_data.get("messages", [])),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# Main
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="AgentBuddy 配置工具 Web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    _ensure_llm_file()
    _ensure_mcp_config_file()

    url = f"http://{args.host}:{args.port}"
    print(f"[Config UI] 服务启动中: {url}")
    print(f"[Config UI] 项目根: {PROJECT_ROOT}")
    print(f"[Config UI] Ctrl+C 退出")

    if not args.no_open:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    app.run(host=args.host, port=args.port, debug=False, threaded=True)


# ============================================================
# Command 配置 API (cmd.yaml - 常用命令集合)
# ============================================================
def _ensure_cmd_file() -> Path:
    """确保 cmd.yaml 存在，不存在则从模板复制。"""
    if CMD_FILE.exists():
        return CMD_FILE
    CMD_FILE.parent.mkdir(parents=True, exist_ok=True)
    if CMD_EXAMPLE.exists():
        import shutil
        shutil.copy2(CMD_EXAMPLE, CMD_FILE)
    else:
        CMD_FILE.write_text("commands: []\n", encoding="utf-8")
    return CMD_FILE


@app.route("/api/cmd", methods=["GET"])
def get_cmd():
    path = _ensure_cmd_file()
    try:
        data = load_env_config_file(path)
        return jsonify({"ok": True, "data": data, "path": str(path.relative_to(PROJECT_ROOT))})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/cmd", methods=["POST"])
def save_cmd():
    body = request.get_json(force=True)
    data = body.get("data")
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "data 必须是对象"}), 400
    try:
        save_env_config_file(_ensure_cmd_file(), data)
        return jsonify({"ok": True, "path": "config/cmd/cmd.yaml"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# Subagent 角色配置 API (subagent.yaml - 预设开发/产品角色)
# ============================================================
def _ensure_subagent_file() -> Path:
    """确保 subagent.yaml 存在，不存在则从模板复制。"""
    if SUBAGENT_FILE.exists():
        return SUBAGENT_FILE
    SUBAGENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    if SUBAGENT_EXAMPLE.exists():
        import shutil
        shutil.copy2(SUBAGENT_EXAMPLE, SUBAGENT_FILE)
    else:
        SUBAGENT_FILE.write_text("subagents: []\n", encoding="utf-8")
    return SUBAGENT_FILE


@app.route("/api/subagent", methods=["GET"])
def get_subagent():
    path = _ensure_subagent_file()
    try:
        data = load_env_config_file(path)
        return jsonify({"ok": True, "data": data, "path": str(path.relative_to(PROJECT_ROOT))})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/subagent", methods=["POST"])
def save_subagent():
    body = request.get_json(force=True)
    data = body.get("data")
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "data 必须是对象"}), 400
    try:
        save_env_config_file(_ensure_subagent_file(), data)
        return jsonify({"ok": True, "path": "config/subagent/subagent.yaml"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# LLM key 验证 + model 获取（调 provider 的 /v1/models）
# ============================================================
@app.route("/api/llm/verify", methods=["POST"])
def verify_llm():
    """验证 LLM api_key 是否可用，并返回可用 model 列表。

    Body: {base_url, api_key, protocol?}
    调 base_url + /v1/models（OpenAI 兼容），成功返回 model 列表。
    """
    body = request.get_json(force=True)
    base_url = (body.get("base_url") or "").rstrip("/")
    api_key = body.get("api_key", "")
    protocol = (body.get("protocol") or "openai").lower()
    if not base_url or not api_key:
        return jsonify({"ok": False, "error": "base_url 和 api_key 必填"}), 400
    try:
        import requests as _req
        # OpenAI 兼容：/v1/models（base_url 可能已含 /v1）
        url = base_url.rstrip("/")
        if not url.endswith("/v1/models") and not url.endswith("/models"):
            url = url + ("/v1/models" if not url.endswith("/v1") else "/models")
        headers = {"Authorization": f"Bearer {api_key}"}
        if protocol == "anthropic":
            headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
        r = _req.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            models = []
            if isinstance(data, dict) and "data" in data:
                models = sorted([m.get("id") for m in data["data"] if m.get("id")])
            elif isinstance(data, dict) and "models" in data:
                models = sorted([m.get("id", m) if isinstance(m, dict) else m for m in data["models"]])
            return jsonify({"ok": True, "models": models, "count": len(models)})
        return jsonify({"ok": False, "error": f"HTTP {r.status_code}: {r.text[:300]}"})
    except _req.exceptions.Timeout:
        return jsonify({"ok": False, "error": "请求超时（15s），请检查 base_url 或网络"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ===== cmd/subagent 导入导出 =====
@app.route("/api/cmd/export", methods=["GET"])
def export_cmd():
    return send_file(_ensure_cmd_file(), as_attachment=True, download_name="cmd.yaml")


@app.route("/api/cmd/import", methods=["POST"])
def import_cmd():
    body = request.get_json(force=True)
    content = body.get("content", "")
    try:
        import yaml as _yaml
        data = _yaml.safe_load(content)
        save_env_config_file(_ensure_cmd_file(), data if isinstance(data, dict) else {"commands": []})
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/subagent/export", methods=["GET"])
def export_subagent():
    return send_file(_ensure_subagent_file(), as_attachment=True, download_name="subagent.yaml")


@app.route("/api/subagent/import", methods=["POST"])
def import_subagent():
    body = request.get_json(force=True)
    content = body.get("content", "")
    try:
        import yaml as _yaml
        data = _yaml.safe_load(content)
        save_env_config_file(_ensure_subagent_file(), data if isinstance(data, dict) else {"subagents": []})
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    main()

# ============================================================
# cmd/subagent 同步到 OpenCode
# ============================================================
@app.route("/api/cmd/sync", methods=["POST"])
def sync_cmd():
    """同步 cmd.yaml 到所有支持命令的 IDE。

    支持命令的 IDE：
    - OpenCode: ~/.config/opencode/commands/*.md
    - Claude:   .claude/commands/*.md（项目根）
    - OpenClaw: .openclaw/commands/*.md（项目根）
    """
    import json as _json
    from pathlib import Path as _Path
    try:
        cmd_path = _ensure_cmd_file()
        data = load_env_config_file(cmd_path)
        commands = data.get("commands", []) if isinstance(data, dict) else []
        # 各 IDE 的命令目录
        targets = [
            ("OpenCode", _Path.home() / ".config" / "opencode" / "commands"),
            ("Claude", PROJECT_ROOT / ".claude" / "commands"),
            ("OpenClaw", PROJECT_ROOT / ".openclaw" / "commands"),
        ]
        results = {}
        for ide_name, cmd_dir in targets:
            cmd_dir.mkdir(parents=True, exist_ok=True)
            count = 0
            for cmd in commands:
                name = cmd.get("name", "").strip()
                if not name:
                    continue
                safe_name = "".join(c for c in name if c.isalnum() or c in "-_")
                if not safe_name:
                    continue
                md = f"---\ndescription: {cmd.get('description', '')}\n---\n{cmd.get('prompt', '')}\n"
                (cmd_dir / f"{safe_name}.md").write_text(md, encoding="utf-8")
                count += 1
            results[ide_name] = count
        total = sum(results.values())
        return jsonify({"ok": True, "count": len(commands), "results": results,
                        "message": f"已同步到 {', '.join(f'{k}({v})' for k,v in results.items() if v)}"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/subagent/sync", methods=["POST"])
def sync_subagent():
    """同步 subagent.yaml 到所有支持 agent 的 IDE。

    支持 agent 的 IDE：
    - OpenCode: opencode.json 的 agent 字段
    """
    import json as _json
    from pathlib import Path as _Path
    try:
        sa_path = _ensure_subagent_file()
        data = load_env_config_file(sa_path)
        subagents = data.get("subagents", []) if isinstance(data, dict) else []
        results = {}
        # OpenCode: opencode.json agent 字段
        oc_config = _Path.home() / ".config" / "opencode" / "opencode.json"
        oc_config.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if oc_config.exists():
            try:
                existing = _json.loads(oc_config.read_text(encoding="utf-8"))
            except Exception:
                existing = {}
        agents = existing.get("agent", {})
        if not isinstance(agents, dict):
            agents = {}
        for sa in subagents:
            name = sa.get("name", "").strip()
            if not name:
                continue
            safe_name = "".join(c for c in name if c.isalnum() or c in "-_")
            if not safe_name:
                continue
            agents[safe_name] = {
                "name": sa.get("role", name),
                "description": sa.get("desc", ""),
                "prompt": sa.get("prompt", ""),
            }
        existing["agent"] = agents
        oc_config.write_text(_json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        results["OpenCode"] = len(subagents)
        return jsonify({"ok": True, "count": len(subagents), "results": results,
                        "message": f"已同步到 {', '.join(f'{k}({v})' for k,v in results.items())}"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
