#!/usr/bin/env python3
"""
飞翼 Web UI 后端

启动: python tools/config_server.py
访问: http://127.0.0.1:5050
依赖: flask, pyyaml, requests
"""

import argparse
import re
import csv
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
import webbrowser
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

def _resolve_project_root() -> Path:
    """Frozen-aware 项目根定位。
    - dev: 仓库根（tools/config_server.py 的上两级）
    - frozen (PyInstaller onedir): exe 所在目录（_MEIPASS == exe dir，可写）
    - macOS .app bundle: exe 在 /Applications 下不可写，改用
      ~/Library/Application Support/AgentBuddy/ 作为用户数据目录
    """
    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            data_root = Path.home() / "Library" / "Application Support" / "AgentBuddy"
            data_root.mkdir(parents=True, exist_ok=True)
            return data_root
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
from lib.skills import build_install_command, parse_shorthand, enable_skill, disable_skill, get_enabled_skills, list_remote_skills, ensure_npx_yes
from lib.plugins import install_plugin, update_env_file, add_to_installed
from lib.ide.detect import detect_ide, detect_all
from lib.ide.session import list_sessions, export_session, import_session_to_ide
from lib.ide.launch import launch_ide, launch_ide_resume_session
from lib.ide.install import (
    install_ide, uninstall_ide, reinstall_ide, get_install_info,
    IDE_INSTALL_META, validate_ide_meta,
)
from lib.provider_catalog import (
    apply_provider_to_env,
    classify_api_key,
    detect_providers,
    load_provider_catalog,
    needs_choice_for_candidates,
)
from lib.mcp_market import (
    SOURCE_LABELS,
    SOURCE_PRIORITY,
    resolve_mcp_install,
    search_mcp_market,
)
from lib.skill_market import (
    SOURCE_LABELS as SKILL_SOURCE_LABELS,
    SOURCE_PRIORITY as SKILL_SOURCE_PRIORITY,
    search_skill_market,
)

app = Flask(__name__, static_folder=None)

# ============================================================
# 路径常量
# ============================================================
ENV_EXAMPLE = PROJECT_ROOT / "env.example.yaml"
ENV_FILE = PROJECT_ROOT / "env.yaml"
# 新拆分：env.yaml → llm.yaml + mcp.yaml
LLM_FILE = PROJECT_ROOT / "config" / "llm" / "llm.yaml"
MCP_CONFIG_FILE = PROJECT_ROOT / "config" / "mcp" / "mcp.yaml"
# 独立密钥/环境变量文件（优先级高于 mcp.yaml.mcp 段）
# 与 mcp.yaml / llm.yaml 平级，强调"跨配置共享的密钥层"定位
KEYS_FILE = PROJECT_ROOT / "config" / "keys.yaml"
# 旧路径（向后兼容迁移用）
KEYS_FILE_LEGACY = PROJECT_ROOT / "config" / "mcp" / "keys.yaml"
# 旧路径2：config/keys/keys.yaml → config/keys.yaml（曾用 keys/ 子目录存放）
KEYS_FILE_LEGACY_2 = PROJECT_ROOT / "config" / "keys" / "keys.yaml"
# 拆分后的示例模板（可安全提交）
LLM_EXAMPLE = PROJECT_ROOT / "template" / "llm" / "llm-env-example.yaml"
MCP_CONFIG_EXAMPLE = PROJECT_ROOT / "template" / "mcp" / "mcp-env-example.yaml"
MCP_TEMPLATE = PROJECT_ROOT / "template" / "mcp" / "mcp.template.json"
PLUGINS_DIR = PROJECT_ROOT / "template" / "plugins"
CONFIG_PLUGINS_DIR = PROJECT_ROOT / "config" / "plugins"
SKILLS_CSV = PROJECT_ROOT / "template" / "skills" / "skills-index.csv"
# 技能安装目标：项目根 .agents/skills/（当前目录，非用户主目录）
AGENTS_SKILLS_INSTALL_DIR = PROJECT_ROOT / ".agents" / "skills"
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
# Rules：config/rules/（用户编辑）+ template/rules/（内置预置）
RULES_DIR = PROJECT_ROOT / "config" / "rules"
RULES_TEMPLATE_DIR = PROJECT_ROOT / "template" / "rules"
# Hooks：config/hooks/hooks.json（用户编辑）+ template/hooks/hooks.json（模板）
HOOKS_DIR = PROJECT_ROOT / "config" / "hooks"
HOOKS_FILE = HOOKS_DIR / "hooks.json"
HOOKS_TEMPLATE_DIR = PROJECT_ROOT / "template" / "hooks"
HOOKS_EXAMPLE = HOOKS_TEMPLATE_DIR / "hooks.json"
# 自建市场：config/marketplace/（索引 + zip 包）
MARKETPLACE_DIR = PROJECT_ROOT / "config" / "marketplace"
MARKETPLACE_PACKAGES_DIR = MARKETPLACE_DIR / "packages"
MARKETPLACE_INDEX = MARKETPLACE_DIR / "index.json"

# env.yaml 中属于 llm.yaml 的顶层键（其余归 mcp.yaml 的只有 mcp）
LLM_TOP_KEYS = ["llm", "embedding", "tts", "asr", "vision", "misc"]

# 外部市场端点
MODELSCOPE_SKILLS_API = "https://www.modelscope.cn/openapi/v1/skills"
MODELSCOPE_MCP_LIST_API = "https://www.modelscope.cn/openapi/v1/mcp/servers"
# 详情需完整 mcp_id（@owner/name）；实际请求由 lib.mcp_market.ModelScopeClient 处理
MODELSCOPE_MCP_DETAIL_API = "https://www.modelscope.cn/openapi/v1/mcp/servers/{mcp_id}"
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
        PROJECT_ROOT / "config" / "rules",
        PROJECT_ROOT / "config" / "hooks",
        PROJECT_ROOT / "config" / "ide",
        PROJECT_ROOT / "config" / "ide" / "claude",
        PROJECT_ROOT / "config" / "ide" / "codex",
        PROJECT_ROOT / "config" / "ide" / "opencode",
        PROJECT_ROOT / "config" / "plugins",
        PROJECT_ROOT / "config" / "marketplace",
        PROJECT_ROOT / "config" / "marketplace" / "packages",
        PROJECT_ROOT / "config" / "proxy",
        # 技能安装目录（项目级 .agents/skills/）
        PROJECT_ROOT / ".agents" / "skills",
    ]
    for d in config_dirs:
        d.mkdir(parents=True, exist_ok=True)


# 启动时确保目录存在
_ensure_config_dirs()


# ============================================================
# 通用工具
# ============================================================
def _now_iso() -> str:
    """当前 UTC 时间 ISO 字符串。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
            stdin=subprocess.DEVNULL,
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
            stdin=subprocess.DEVNULL,
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
    """返回应用版本号。构建时由 build.py 写入 tools/dist-ui/version.json，供运行时 /api/version 读取。"""
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
# 升级检查 API
# ============================================================
GITHUB_REPO = "superproxy/AgentBuddy"
GITHUB_RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"


def _parse_version(v: str):
    """把 'v1.10.2' 解析为 (1, 10, 2) 元组，便于比较。"""
    v = (v or "").strip().lstrip("vV")
    parts = re.split(r"[.\-+]", v)
    result = []
    for p in parts[:3]:
        try:
            result.append(int(p))
        except (ValueError, TypeError):
            result.append(0)
    while len(result) < 3:
        result.append(0)
    return tuple(result)


@app.route("/api/upgrade/check", methods=["GET"])
def upgrade_check():
    """检查 GitHub Release 是否有新版本。

    返回：
      {
        "ok": true,
        "current": "1.10.2",
        "latest": "1.11.0",
        "has_upgrade": true,
        "release_url": "https://github.com/.../releases/tag/v1.11.0",
        "release_notes": "...",  # release body（markdown）
        "published_at": "2026-...",
        "downloads": [
          {"platform": "windows", "filename": "AgentBuddy-Setup-1.11.0-x64.exe", "url": "...", "size": 12345678},
          {"platform": "macos", "filename": "AgentBuddy-1.11.0-macos.pkg", "url": "...", "size": 23456789}
        ]
      }

    失败时返回 {ok: false, error: "..."}
    """
    import urllib.request
    import urllib.error

    # 读取当前版本
    current = "dev"
    version_file = PROJECT_ROOT / "tools" / "dist-ui" / "version.json"
    if version_file.exists():
        try:
            with open(version_file, "r", encoding="utf-8") as f:
                current = (json.load(f) or {}).get("version") or "dev"
        except Exception:
            pass

    # 开发模式直接返回无升级
    if current == "dev":
        return jsonify({
            "ok": True,
            "current": "dev",
            "latest": None,
            "has_upgrade": False,
            "release_url": GITHUB_RELEASES_URL,
            "downloads": [],
            "note": "开发模式不检查升级",
        })

    try:
        req = urllib.request.Request(
            GITHUB_RELEASES_API,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "AgentBuddy-Updater/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        return jsonify({"ok": False, "error": f"网络错误: {e}"}), 502
    except Exception as e:
        return jsonify({"ok": False, "error": f"解析失败: {e}"}), 500

    latest = (data.get("tag_name") or "").lstrip("vV")
    has_upgrade = bool(latest) and _parse_version(latest) > _parse_version(current)

    # 收集 Windows / macOS 安装包
    downloads = []
    for asset in data.get("assets", []) or []:
        name = asset.get("name", "")
        url = asset.get("browser_download_url", "")
        size = asset.get("size", 0)
        if not name or not url:
            continue
        lower = name.lower()
        if lower.endswith(".exe") and "x64" in lower:
            downloads.append({"platform": "windows", "filename": name, "url": url, "size": size})
        elif lower.endswith(".pkg"):
            downloads.append({"platform": "macos", "filename": name, "url": url, "size": size})
        elif lower.endswith(".dmg"):
            downloads.append({"platform": "macos-dmg", "filename": name, "url": url, "size": size})
        elif lower.endswith(".zip") and "macos" in lower:
            downloads.append({"platform": "macos-zip", "filename": name, "url": url, "size": size})

    return jsonify({
        "ok": True,
        "current": current,
        "latest": latest,
        "has_upgrade": has_upgrade,
        "release_url": data.get("html_url") or GITHUB_RELEASES_URL,
        "release_notes": data.get("body") or "",
        "published_at": data.get("published_at") or "",
        "downloads": downloads,
    })


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


@app.route("/api/llm/catalog", methods=["GET"])
def get_llm_catalog():
    """返回 llm-env-example.yaml 中的 Provider Catalog（预设 base_url / models）。"""
    try:
        catalog = load_provider_catalog(LLM_EXAMPLE)
        return jsonify({"ok": True, "catalog": catalog, "count": len(catalog)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/llm/detect", methods=["POST"])
def detect_llm_provider():
    """根据 api_key / base_url 推断厂商 + 协议（配置管道 Detect 步）。

    Body: {api_key, base_url?, probe?: true}
      probe=true（默认）时，对模糊 sk- / 智谱 Key 并行探测默认端点以消歧。
    返回: {ok, candidates: [{provider, detected_protocol, protocol_reason, ...}], needs_choice}
    """
    body = request.get_json(force=True) or {}
    api_key = (body.get("api_key") or "").strip()
    base_url = (body.get("base_url") or "").strip()
    probe = body.get("probe", True)
    if not api_key:
        return jsonify({"ok": False, "error": "api_key 必填"}), 400
    try:
        candidates = detect_providers(
            api_key, base_url, example_path=LLM_EXAMPLE, probe=bool(probe),
        )
        top = candidates[0] if candidates else None
        return jsonify({
            "ok": True,
            "candidates": candidates,
            "needs_choice": needs_choice_for_candidates(candidates),
            "count": len(candidates),
            "detected_provider": (top or {}).get("provider"),
            "detected_protocol": (top or {}).get("detected_protocol"),
            "protocol_reason": (top or {}).get("protocol_reason"),
            "fingerprint": (classify_api_key(api_key) or {}).get("id") if api_key else None,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/llm/apply", methods=["POST"])
def apply_llm_provider():
    """将候选 preset 写入 llm.yaml（配置管道 Apply 步）。

    Body: {
      api_key,
      provider,                 # 必填：候选 provider 名
      protocol?,                # 可选：覆盖识别出的协议
      base_url?,                # 可选覆盖
      set_active?: true,
      candidate?: {...},        # 可选：前端传入的完整候选；缺省则从 catalog 重建
    }
    返回: {ok, applied, data}  — data 为更新后的完整 llm.yaml
    """
    body = request.get_json(force=True) or {}
    api_key = (body.get("api_key") or "").strip()
    provider = (body.get("provider") or "").strip()
    protocol = (body.get("protocol") or "").strip()
    base_url = (body.get("base_url") or "").strip()
    set_active = body.get("set_active", True)
    if not api_key:
        return jsonify({"ok": False, "error": "api_key 必填"}), 400
    if not provider:
        return jsonify({"ok": False, "error": "provider 必填"}), 400
    try:
        candidate = body.get("candidate")
        if not isinstance(candidate, dict) or candidate.get("provider") != provider:
            catalog = load_provider_catalog(LLM_EXAMPLE)
            cmap = {c["provider"]: c for c in catalog}
            entry = cmap.get(provider)
            if not entry:
                return jsonify({"ok": False, "error": f"未知 provider: {provider}"}), 400
            from lib.provider_catalog import infer_protocol
            detected, p_reason = infer_protocol(
                api_key, base_url, entry.get("protocols"),
            )
            candidate = {
                **entry,
                "score": 100,
                "reason": "用户选择",
                "detected_protocol": protocol or detected,
                "protocol_reason": p_reason,
                "suggested_protocol": protocol or detected,
            }
            if base_url:
                target = protocol or detected
                for proto, cfg in (candidate.get("protocols") or {}).items():
                    if isinstance(cfg, dict) and (proto == target or len(candidate["protocols"]) == 1):
                        cfg["base_url"] = base_url

        path = _ensure_llm_file()
        env_data = load_env_config_file(path) or {}
        applied = apply_provider_to_env(
            env_data, candidate, api_key,
            set_active=bool(set_active),
            base_url_override=base_url,
            protocol=protocol,
        )
        save_env_config_file(path, env_data)
        return jsonify({
            "ok": True,
            "applied": applied,
            "data": env_data,
            "path": str(path.relative_to(PROJECT_ROOT)),
        })
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
# Keys API (config/keys.yaml - 独立密钥/环境变量层)
# ============================================================
def _ensure_keys_file() -> Path:
    """确保 keys.yaml 存在。优先级：
      1. 路径 config/keys.yaml 已存在 → 直接返回
      2. 旧路径 config/keys/keys.yaml 存在 → 迁移到新路径，删除旧文件
      3. 旧路径 config/mcp/keys.yaml 存在 → 迁移到新路径，删除旧文件
      4. mcp.yaml 有 mcp: 段且非空 → 迁移到 keys.yaml（清空 mcp.yaml.mcp）
      5. 创建空模板 {"mcp": {}}
    """
    if KEYS_FILE.exists():
        return KEYS_FILE
    # 旧路径迁移：config/keys/keys.yaml → config/keys.yaml
    try:
        if KEYS_FILE_LEGACY_2.exists():
            legacy_data = load_env_config_file(KEYS_FILE_LEGACY_2) or {}
            KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
            save_env_config_file(KEYS_FILE, legacy_data)
            # 删除旧文件，避免双源冲突
            try:
                KEYS_FILE_LEGACY_2.unlink()
            except Exception:
                pass
            # 清理空的 config/keys/ 目录
            try:
                if KEYS_FILE_LEGACY_2.parent.exists() and not any(KEYS_FILE_LEGACY_2.parent.iterdir()):
                    KEYS_FILE_LEGACY_2.parent.rmdir()
            except Exception:
                pass
            return KEYS_FILE
    except Exception:
        pass
    # 旧路径迁移：config/mcp/keys.yaml → config/keys.yaml
    try:
        if KEYS_FILE_LEGACY.exists():
            legacy_data = load_env_config_file(KEYS_FILE_LEGACY) or {}
            KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
            save_env_config_file(KEYS_FILE, legacy_data)
            # 删除旧文件，避免双源冲突
            try:
                KEYS_FILE_LEGACY.unlink()
            except Exception:
                pass
            return KEYS_FILE
    except Exception:
        pass
    # 从 mcp.yaml.mcp 段迁移
    try:
        if MCP_CONFIG_FILE.exists():
            mcp_full = load_env_config_file(MCP_CONFIG_FILE) or {}
            mcp_keys = mcp_full.get("mcp", {}) or {}
            if isinstance(mcp_keys, dict) and mcp_keys:
                KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
                save_env_config_file(KEYS_FILE, {"mcp": mcp_keys})
                # 清空 mcp.yaml.mcp 段（避免双源冲突）
                mcp_full["mcp"] = {}
                save_env_config_file(MCP_CONFIG_FILE, mcp_full)
                return KEYS_FILE
    except Exception:
        pass
    KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    save_env_config_file(KEYS_FILE, {"mcp": {}})
    return KEYS_FILE


def _normalize_key_entry(raw) -> dict:
    """规范化单个密钥条目为 {value, description}。

    兼容三种输入：
      - 字符串 "xxx" → {"value": "xxx", "description": ""}
      - dict {"value": "...", "description": "..."} → 原样
      - dict 缺字段 → 补默认值
      - 其他类型 → {"value": str(raw), "description": ""}
    """
    if isinstance(raw, dict):
        v = raw.get("value", "")
        d = raw.get("description", "")
        if not isinstance(v, str):
            v = "" if v is None else str(v)
        if not isinstance(d, str):
            d = "" if d is None else str(d)
        return {"value": v, "description": d}
    if isinstance(raw, str):
        return {"value": raw, "description": ""}
    if raw is None:
        return {"value": "", "description": ""}
    return {"value": str(raw), "description": ""}


def _load_keys_full() -> dict:
    """加载 keys.yaml 全量数据。返回 {"mcp": {KEY: {value, description}}}。

    规范化后所有条目都是 {value, description} 对象，前端无需关心原始格式。
    """
    path = _ensure_keys_file()
    try:
        data = load_env_config_file(path) or {}
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    if not isinstance(data.get("mcp"), dict):
        data["mcp"] = {}
    # 规范化每一条
    data["mcp"] = {k: _normalize_key_entry(v) for k, v in data["mcp"].items()}
    return data


def _save_keys_full(data: dict) -> None:
    """保存 keys.yaml 全量数据。

    存储格式：所有条目统一存为 {value, description} 对象。
    """
    path = _ensure_keys_file()
    if not isinstance(data, dict):
        data = {}
    if not isinstance(data.get("mcp"), dict):
        data["mcp"] = {}
    # 规范化后再存
    data["mcp"] = {k: _normalize_key_entry(v) for k, v in data["mcp"].items()}
    save_env_config_file(path, data)


def _compute_key_usages() -> dict:
    """扫描 mcp.yaml 和 llm.yaml，反查每个变量名的引用出处。

    返回：{KEY: [{source: "mcp.yaml", scope: "服务名/Redis", field: "env.REDIS_URL"}, ...]}

    匹配规则：
      1. ${KEY} 或 ${KEY:-default} 占位符（任何字段值中）
      2. mcp.yaml 中 env 段的 key 名直接匹配（明文配置也算引用）
      3. llm.yaml 中字段名匹配（api_key/base_url 等）暂不识别明文（太宽泛）
    """
    usages: dict = {}
    placeholder_re = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-[^\}]*)?\}")

    # 1) 扫描 mcp.yaml
    try:
        mcp_path = MCP_CONFIG_FILE
        if mcp_path.exists():
            mcp_data = load_env_config_file(mcp_path) or {}
            servers = mcp_data.get("mcpServers", {}) if isinstance(mcp_data, dict) else {}
            for srv_name, srv_cfg in servers.items():
                if not isinstance(srv_cfg, dict):
                    continue
                # env 段：key 名匹配 / 值中的占位符
                env_seg = srv_cfg.get("env")
                if isinstance(env_seg, dict):
                    for env_k, env_v in env_seg.items():
                        # 明文：env 段的 key 名直接是变量名
                        if env_k in usages:
                            pass  # 已存在
                        usages.setdefault(env_k, []).append({
                            "source": "mcp.yaml",
                            "scope": str(srv_name),
                            "field": f"env.{env_k}",
                            "kind": "plaintext",
                        })
                        # 占位符：值中引用
                        if isinstance(env_v, str):
                            for m in placeholder_re.finditer(env_v):
                                var = m.group(1)
                                usages.setdefault(var, []).append({
                                    "source": "mcp.yaml",
                                    "scope": str(srv_name),
                                    "field": f"env.{env_k}",
                                    "kind": "placeholder",
                                })
                # headers 段：值中的占位符
                headers_seg = srv_cfg.get("headers")
                if isinstance(headers_seg, dict):
                    for h_k, h_v in headers_seg.items():
                        if isinstance(h_v, str):
                            for m in placeholder_re.finditer(h_v):
                                var = m.group(1)
                                usages.setdefault(var, []).append({
                                    "source": "mcp.yaml",
                                    "scope": str(srv_name),
                                    "field": f"headers.{h_k}",
                                    "kind": "placeholder",
                                })
                # args / url / command 等字符串字段：占位符
                for field_name in ("url", "command"):
                    fv = srv_cfg.get(field_name)
                    if isinstance(fv, str):
                        for m in placeholder_re.finditer(fv):
                            var = m.group(1)
                            usages.setdefault(var, []).append({
                                "source": "mcp.yaml",
                                "scope": str(srv_name),
                                "field": field_name,
                                "kind": "placeholder",
                            })
                args_seg = srv_cfg.get("args")
                if isinstance(args_seg, list):
                    for i, av in enumerate(args_seg):
                        if isinstance(av, str):
                            for m in placeholder_re.finditer(av):
                                var = m.group(1)
                                usages.setdefault(var, []).append({
                                    "source": "mcp.yaml",
                                    "scope": str(srv_name),
                                    "field": f"args[{i}]",
                                    "kind": "placeholder",
                                })
    except Exception:
        pass

    # 2) 扫描 llm.yaml（仅识别 ${KEY} 占位符，避免误报明文）
    try:
        llm_path = LLM_FILE
        if llm_path.exists():
            llm_data = load_env_config_file(llm_path) or {}
            if isinstance(llm_data, dict):
                def _walk(obj, path_str):
                    if isinstance(obj, dict):
                        for k, v in obj.items():
                            _walk(v, f"{path_str}.{k}" if path_str else str(k))
                    elif isinstance(obj, list):
                        for i, v in enumerate(obj):
                            _walk(v, f"{path_str}[{i}]")
                    elif isinstance(obj, str):
                        for m in placeholder_re.finditer(obj):
                            var = m.group(1)
                            usages.setdefault(var, []).append({
                                "source": "llm.yaml",
                                "scope": path_str.split(".")[0] if path_str else "",
                                "field": path_str,
                                "kind": "placeholder",
                            })
                _walk(llm_data, "")
    except Exception:
        pass

    return usages


@app.route("/api/keys", methods=["GET"])
def get_keys():
    """返回 keys.yaml 全量数据 + 每个变量的引用出处。"""
    path = _ensure_keys_file()
    try:
        full = _load_keys_full()
        usages = _compute_key_usages()
        return jsonify({
            "ok": True,
            "data": {"mcp": full.get("mcp", {})},
            "usages": usages,
            "path": str(path.relative_to(PROJECT_ROOT)),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/keys", methods=["POST"])
def save_keys():
    """保存 keys.yaml 全量数据。Body: {data: {mcp: {...}}}"""
    body = request.get_json(force=True)
    data = body.get("data")
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "data 必须是对象"}), 400
    try:
        full = _load_keys_full()
        full["mcp"] = data.get("mcp", {})
        _save_keys_full(full)
        return jsonify({"ok": True, "path": str(KEYS_FILE.relative_to(PROJECT_ROOT))})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/keys/key", methods=["POST"])
def add_key():
    """添加单个密钥条目。Body: {key, value='', description=''}"""
    body = request.get_json(force=True)
    key = (body.get("key") or "").strip()
    if not key:
        return jsonify({"ok": False, "error": "key 必填"}), 400
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
        return jsonify({"ok": False, "error": "仅支持字母、数字、下划线，且不能以数字开头"}), 400
    try:
        full = _load_keys_full()
        if key in full["mcp"]:
            return jsonify({"ok": False, "error": f"变量已存在: {key}"}), 409
        full["mcp"][key] = {
            "value": body.get("value", "") or "",
            "description": body.get("description", "") or "",
        }
        _save_keys_full(full)
        return jsonify({"ok": True, "key": key})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/keys/key/<key>", methods=["PATCH"])
def update_key(key):
    """更新单个密钥条目的 value 和/或 description。Body: {value?, description?}"""
    body = request.get_json(force=True) or {}
    try:
        full = _load_keys_full()
        if key not in full["mcp"]:
            return jsonify({"ok": False, "error": f"未找到 key: {key}"}), 404
        entry = full["mcp"][key]
        if "value" in body:
            v = body["value"]
            entry["value"] = "" if v is None else (str(v) if not isinstance(v, str) else v)
        if "description" in body:
            d = body["description"]
            entry["description"] = "" if d is None else (str(d) if not isinstance(d, str) else d)
        _save_keys_full(full)
        return jsonify({"ok": True, "key": key, "entry": entry})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/keys/key/<key>", methods=["DELETE"])
def delete_key(key):
    """删除单个密钥条目。"""
    try:
        full = _load_keys_full()
        if key in full["mcp"]:
            del full["mcp"][key]
            _save_keys_full(full)
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": f"未找到 key: {key}"}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/keys/apply-env", methods=["POST"])
def apply_keys_to_env():
    """把 keys.yaml 中的变量应用到操作系统，使其在系统中立即生效。

    平台行为：
      Windows  → 调用 PowerShell [Environment]::SetEnvironmentVariable(name, value, 'User')
                 写入用户级环境变量（持久化，新开 shell/进程可读）
      macOS    → 追加 `export KEY='value'` 到 ~/.zshrc
      Linux    → 追加 `export KEY='value'` 到 ~/.bashrc

    请求体可选字段：
      - keys: [str]  仅应用指定变量；省略则应用全部
      - include_empty: bool  是否包含空值变量（默认 False）

    返回：{ok, applied: [{key, value}], skipped: [{key, reason}], target, note}
    """
    body = request.get_json(silent=True) or {}
    only_keys = body.get("keys") or None
    include_empty = bool(body.get("include_empty", False))

    try:
        full = _load_keys_full()
        mcp = full.get("mcp", {}) or {}
    except Exception as e:
        return jsonify({"ok": False, "error": f"读取 keys.yaml 失败: {e}"}), 500

    applied: list = []
    skipped: list = []
    target = ""
    note = ""

    if sys.platform == "win32":
        # Windows: 直接写注册表 HKCU\Environment，避免 PowerShell 启动开销
        # （PowerShell [Environment]::SetEnvironmentVariable 每条都会广播
        #  WM_SETTINGCHANGE 给所有窗口，多条变量累积会超时）
        target = "Windows 用户环境变量（HKCU\\Environment）"
        note = "已写入注册表（HKCU\\Environment），新开终端/进程即可读取；当前进程不自动刷新。"

        # 先收集要写的变量
        to_write: list = []
        for k, v in mcp.items():
            if only_keys and k not in only_keys:
                skipped.append({"key": k, "reason": "未在指定列表"})
                continue
            value = v.get("value", "") if isinstance(v, dict) else (v or "")
            if not value and not include_empty:
                skipped.append({"key": k, "reason": "值为空"})
                continue
            to_write.append((k, value))
            applied.append({"key": k, "value": value})

        if not to_write:
            return jsonify({
                "ok": True,
                "applied": [],
                "skipped": skipped,
                "target": target,
                "note": "无变量需要应用",
            })

        try:
            import winreg
            import ctypes
            # 打开 HKCU\Environment（读写）
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                "Environment",
                0,
                winreg.KEY_READ | winreg.KEY_WRITE,
            ) as reg_key:
                for k, value in to_write:
                    # REG_SZ：纯字符串（不展开 %VAR%）
                    # 若需支持 %VAR% 引用，可改 REG_EXPAND_SZ
                    winreg.SetValueEx(reg_key, k, 0, winreg.REG_SZ, value)

            # 广播一次 WM_SETTINGCHANGE，让其他进程感知环境变量变化
            # HWND_BROADCAST = 0xFFFF, WM_SETTINGCHANGE = 0x001A
            # SMTO_ABORTIFHUNG = 0x0002（接收进程挂起时立即返回，不等待）
            try:
                ctypes.windll.user32.SendMessageTimeoutW(
                    0xFFFF,           # HWND_BROADCAST
                    0x001A,           # WM_SETTINGCHANGE
                    0,
                    "Environment",
                    0x0002,           # SMTO_ABORTIFHUNG
                    1000,             # 超时 1s
                )
            except Exception:
                # 广播失败不影响写入结果，新开进程仍可读到
                pass

        except PermissionError as e:
            return jsonify({
                "ok": False,
                "error": f"写入注册表权限不足: {e}",
                "applied": [],
                "skipped": skipped,
                "target": target,
            }), 500
        except OSError as e:
            return jsonify({
                "ok": False,
                "error": f"写入注册表失败: {e}",
                "applied": [],
                "skipped": skipped,
                "target": target,
            }), 500

    elif sys.platform == "darwin":
        # macOS: 追加到 ~/.zshrc
        rc_path = Path.home() / ".zshrc"
        target = f"macOS {rc_path}"
        note = f"已追加到 {rc_path}，新开终端会话会自动 source；当前会话需手动 `source {rc_path}`。"
        lines_to_write = []
        for k, v in mcp.items():
            if only_keys and k not in only_keys:
                skipped.append({"key": k, "reason": "未在指定列表"})
                continue
            value = v.get("value", "") if isinstance(v, dict) else (v or "")
            if not value and not include_empty:
                skipped.append({"key": k, "reason": "值为空"})
                continue
            v_esc = value.replace("'", "'\\''")
            lines_to_write.append(f"export {k}='{v_esc}'")
            applied.append({"key": k, "value": value})

        if lines_to_write:
            marker_begin = "# >>> AgentBuddy env >>>"
            marker_end = "# <<< AgentBuddy env <<<"
            try:
                old = rc_path.read_text(encoding="utf-8") if rc_path.exists() else ""
            except Exception:
                old = ""
            # 替换已有块（若存在）
            if marker_begin in old and marker_end in old:
                pre = old[: old.index(marker_begin)]
                post = old[old.index(marker_end) + len(marker_end):]
                old = (pre + post).rstrip("\n") + "\n"
            block = "\n".join([marker_begin] + lines_to_write + [marker_end, ""])
            rc_path.write_text(old.rstrip("\n") + "\n\n" + block, encoding="utf-8")

    else:
        # Linux/其他: 追加到 ~/.bashrc
        rc_path = Path.home() / ".bashrc"
        target = f"Linux {rc_path}"
        note = f"已追加到 {rc_path}，新开终端会话会自动 source；当前会话需手动 `source {rc_path}`。"
        lines_to_write = []
        for k, v in mcp.items():
            if only_keys and k not in only_keys:
                skipped.append({"key": k, "reason": "未在指定列表"})
                continue
            value = v.get("value", "") if isinstance(v, dict) else (v or "")
            if not value and not include_empty:
                skipped.append({"key": k, "reason": "值为空"})
                continue
            v_esc = value.replace("'", "'\\''")
            lines_to_write.append(f"export {k}='{v_esc}'")
            applied.append({"key": k, "value": value})

        if lines_to_write:
            marker_begin = "# >>> AgentBuddy env >>>"
            marker_end = "# <<< AgentBuddy env <<<"
            try:
                old = rc_path.read_text(encoding="utf-8") if rc_path.exists() else ""
            except Exception:
                old = ""
            if marker_begin in old and marker_end in old:
                pre = old[: old.index(marker_begin)]
                post = old[old.index(marker_end) + len(marker_end):]
                old = (pre + post).rstrip("\n") + "\n"
            block = "\n".join([marker_begin] + lines_to_write + [marker_end, ""])
            rc_path.write_text(old.rstrip("\n") + "\n\n" + block, encoding="utf-8")

    return jsonify({
        "ok": True,
        "applied": applied,
        "skipped": skipped,
        "target": target,
        "note": note,
    })


# ============================================================
# Skills API
# ============================================================
@app.route("/api/skills/local", methods=["GET"])
def list_local_skills():
    """列出本地预置技能：扫描三源目录（template/skills + config/skills + .agents/skills）下有 SKILL.md 的技能。

    CSV 提供 category/role/description 等元信息；
    三源扫描确保所有实际存在的本地 skill 都能展示，前源优先去重。
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

    # 扫描三源本地 skill 目录，前源优先，同名跳过：
    #   template/skills/（预置缓存）→ config/skills/（项目级副本）→ .agents/skills/（安装目标）
    seen = set()
    for scan_dir in (AGENTS_SKILLS_CACHE, PROJECT_SKILLS_DIR, DOT_AGENTS_SKILLS):
        if not scan_dir.exists():
            continue
        for d in sorted(scan_dir.iterdir()):
            if not d.is_dir() or not (d / "SKILL.md").exists():
                continue
            name = d.name
            if name in seen:
                continue
            seen.add(name)
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
    # 预读 skills-index.csv，用于补充 github 作者/仓库信息
    csv_map: dict[str, dict] = {}
    if SKILLS_CSV.exists():
        try:
            with open(SKILLS_CSV, "r", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    name = row.get("skill_name") or row.get("name") or ""
                    if name:
                        csv_map[name] = row
        except Exception:
            pass

    def _parse_github_source(meta: dict) -> tuple[str, str, str]:
        """从 CSV 行解析 (author, repo, github_url)。

        source 字段格式：
          - remote: "owner/repo"（可能带 @skill 后缀，如 "owner/repo@skill"）
          - local:  仅技能名（无 github 信息）
        url 字段优先作为 github_url。
        """
        source = (meta.get("source") or "").strip()
        url = (meta.get("url") or "").strip()
        # 去掉 @skill 后缀
        if "@" in source:
            source = source.split("@", 1)[0].strip()
        author = ""
        repo = ""
        if "/" in source:
            parts = source.split("/", 1)
            author = parts[0].strip()
            repo = parts[1].strip() if len(parts) > 1 else ""
        # 仅当 url 看起来是 github 链接时才返回
        github_url = url if url and "github.com" in url else ""
        # 若无 url 但有 author/repo，构造 github url
        if not github_url and author and repo:
            github_url = f"https://github.com/{author}/{repo}"
        return author, repo, github_url

    installed = []
    seen = set()
    # 扫描两个项目级技能目录：.agents/skills/（安装目标）+ config/skills/（项目复制）
    scan_dirs = [
        DOT_AGENTS_SKILLS,       # .agents/skills/
        PROJECT_SKILLS_DIR,      # config/skills/
    ]
    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for d in scan_dir.iterdir():
            if not d.is_dir() or not (d / "SKILL.md").exists():
                continue
            if d.name in seen:
                continue
            seen.add(d.name)
            try:
                rel = str(d.relative_to(PROJECT_ROOT))
            except ValueError:
                rel = str(d)
            # 从 CSV 补充 github 作者/仓库信息
            meta = csv_map.get(d.name, {})
            author, repo, github_url = _parse_github_source(meta)
            installed.append({
                "name": d.name,
                "path": rel,
                "skill_md_exists": True,
                "enabled": d.name in enabled_set,
                "author": author,
                "repo": repo,
                "github_url": github_url,
                "source_type": meta.get("source_type") or "",
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


@app.route("/api/skills/import", methods=["POST"])
def import_skills():
    """批量导入技能启用清单。

    Body: { names: [str], mode: "merge"|"overwrite", ides: ["Claude", ...] }
    语义：
      - 仅写入 skill.yaml 的 enabled 清单（不安装/卸载）
      - mode=merge: 追加；mode=overwrite: 清空后追加
      - 未安装的技能名会被跳过并记入 not_installed
      - 完成后自动同步到指定 IDE（scope=skill）
    """
    body = request.get_json(silent=True) or {}
    names = body.get("names") or []
    mode = str(body.get("mode") or "merge")
    ides = body.get("ides") or []
    if not isinstance(names, list):
        return jsonify({"ok": False, "error": "names 必须为数组"}), 400
    if not isinstance(ides, list):
        ides = []
    allowed_ides = {"Agents", "Claude", "Codex", "Cursor", "IDEA", "OpenClaw",
                    "OpenCode", "Qoder", "QoderCN", "Trae", "TraeCN", "TraeSoloCN", "WorkBuddy",
                    "ZCode", "All"}
    safe_ides = [i for i in ides if i in allowed_ides]

    # 收集已安装技能名集合
    installed = set()
    for base in (DOT_AGENTS_SKILLS, PROJECT_SKILLS_DIR):
        if not base.exists():
            continue
        for p in base.iterdir():
            if p.is_dir():
                installed.add(p.name)

    # 清洗目标名称
    target = [str(n).strip() for n in names if str(n).strip()]
    added = []
    skipped = []
    not_installed = []
    for name in target:
        if name not in installed:
            not_installed.append(name)
            continue
        added.append(name)

    try:
        from lib.skills import load_skill_yaml, save_skill_yaml
        data = load_skill_yaml(SKILL_YAML)
        cur = data.get("enabled", []) or []
        if mode == "overwrite":
            cur = []
        cur_set = set(cur)
        for name in added:
            if name not in cur_set:
                cur.append(name)
                cur_set.add(name)
            else:
                skipped.append(name)
        data["enabled"] = cur
        save_skill_yaml(SKILL_YAML, data)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    # 同步到 IDE
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
        "added": len(added),
        "skipped": len(skipped),
        "not_installed": not_installed,
        "synced_ides": safe_ides,
        "sync_log": "\n".join(sync_logs).strip(),
    })


@app.route("/api/skills/search", methods=["GET"])
def search_skills():
    """多源 Skills 市场聚合搜索。

    Query:
      q         关键词（必填）
      sources   逗号分隔源过滤，默认全部：
                skillssh,smithery,modelscope,skillsmp,clawhub,anthropics,github
      source    兼容旧参数：modelscope|skillssh|smithery|all
      limit     每源条数，默认 12
    """
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"ok": False, "error": "缺少 q 参数"}), 400

    sources_raw = request.args.get("sources", "").strip()
    legacy = request.args.get("source", "").strip().lower()
    if sources_raw:
        sources = [s.strip() for s in sources_raw.split(",") if s.strip()]
    elif legacy in ("modelscope", "skillssh", "smithery", "skillsmp", "clawhub", "anthropics", "github"):
        sources = [legacy]
    elif legacy == "all" or not legacy:
        sources = None
    else:
        sources = [s.strip() for s in legacy.split(",") if s.strip()] or None

    try:
        limit = int(request.args.get("limit", 12))
    except ValueError:
        limit = 12

    try:
        result = search_skill_market(q, sources=sources, limit_per_source=max(1, min(limit, 30)))
        result["source_labels"] = SKILL_SOURCE_LABELS
        result["source_order"] = list(SKILL_SOURCE_PRIORITY)
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/skills/market-status", methods=["GET"])
def skills_market_status():
    """返回 Skills 市场源依赖状态。"""
    import os
    gh = bool(os.environ.get("GITHUB_TOKEN", "").strip())
    smp = bool(os.environ.get("SKILLSMP_API_KEY", "").strip())
    smithery = bool(os.environ.get("SMITHERY_API_KEY", "").strip())
    return jsonify({
        "ok": True,
        "sources": {
            "skillssh": {"configured": True, "note": "公开 API"},
            "smithery": {
                "configured": True,
                "authenticated": smithery,
                "note": "公开 GET /skills；配置 SMITHERY_API_KEY 可选",
                "docs_url": "https://smithery.ai/docs/api-reference/skills/list-or-search-skills",
            },
            "modelscope": {"configured": True, "note": "公开 API"},
            "skillsmp": {
                "configured": True,
                "authenticated": smp,
                "note": "匿名配额有限；配置 SKILLSMP_API_KEY 可提高限额",
            },
            "clawhub": {"configured": True, "note": "公开语义搜索"},
            "anthropics": {"configured": True, "note": "anthropics/skills 官方库"},
            "github": {
                "configured": True,
                "code_search": gh,
                "note": "仓库搜索始终可用；配置 GITHUB_TOKEN 启用 filename:SKILL.md code search",
            },
        },
        "source_order": list(SKILL_SOURCE_PRIORITY),
        "source_labels": SKILL_SOURCE_LABELS,
    })


@app.route("/api/skills/preview", methods=["GET"])
def preview_skills_source():
    """预览远程源中的技能列表（手动安装勾选前）。

    Query: source=owner/repo 或 GitHub URL 或 owner/repo@skill
    """
    source = request.args.get("source", "").strip()
    if not source:
        return jsonify({"ok": False, "error": "缺少 source 参数"}), 400
    try:
        data = list_remote_skills(source)
        return jsonify({"ok": True, **data})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/skills/install", methods=["GET"])
def install_skill_sse():
    """SSE: 流式安装 skill。
    Query:
      source=owner/repo[&skill=name] 或 skills=a,b,c（多选）
      或 command=完整 npx 命令
    """
    source = request.args.get("source", "").strip()
    skill = request.args.get("skill", "").strip()
    skills_csv = request.args.get("skills", "").strip()
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
        parsed_source, parsed_skill = parse_shorthand(source)
        effective_source = parsed_source or source
        selected = [s.strip() for s in skills_csv.split(",") if s.strip()]
        if skill:
            selected = [skill] + [s for s in selected if s != skill]
        elif parsed_skill and not selected:
            selected = [parsed_skill]

        if selected:
            skill_flags = " ".join(f'--skill {s}' for s in selected)
            cmd = f"npx --yes skills add {effective_source} {skill_flags} --copy -y"
            skill_name = ",".join(selected)
        else:
            # 未指定技能：仍允许安装全部（兼容旧行为）；UI 会先引导勾选
            cmd = f"npx --yes skills add {effective_source} --copy -y"
            skill_name = effective_source

    cmd = ensure_npx_yes(cmd)
    return Response(
        stream_with_context(_stream_process(cmd, cwd=PROJECT_ROOT)),
        mimetype="text/event-stream",
    )


@app.route("/api/skills/<name>", methods=["DELETE"])
def uninstall_skill(name):
    """卸载技能：同时清理 .agents/skills/ 与 config/skills/，并从启用清单移除。"""
    name = (name or "").strip()
    if not name or "/" in name or "\\" in name or name in (".", ".."):
        return jsonify({"ok": False, "error": "非法技能名"}), 400

    targets = []
    for base in (DOT_AGENTS_SKILLS, PROJECT_SKILLS_DIR):
        cand = base / name
        if not cand.exists() or not cand.is_dir():
            continue
        try:
            cand.resolve().relative_to(base.resolve())
        except ValueError:
            return jsonify({"ok": False, "error": "非法路径"}), 400
        targets.append(cand)

    if not targets:
        return jsonify({"ok": False, "error": f"未找到技能: {name}"}), 404

    removed = []
    try:
        for t in targets:
            shutil.rmtree(t)
            removed.append(str(t.relative_to(PROJECT_ROOT)))
        # 从启用清单移除（若存在）
        try:
            disable_skill(SKILL_YAML, name)
        except Exception:
            pass
        return jsonify({"ok": True, "removed": removed})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/skills/<name>/skillmd", methods=["GET"])
def get_skill_md(name):
    name = (name or "").strip()
    if not name or "/" in name or "\\" in name:
        return jsonify({"ok": False, "error": "非法技能名"}), 400
    target = None
    for base in (DOT_AGENTS_SKILLS, PROJECT_SKILLS_DIR, PROJECT_ROOT / "template" / "skills"):
        cand = base / name / "SKILL.md"
        if cand.exists():
            target = cand
            break
    if not target:
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
    """多源 MCP 市场搜索。

    Query:
      q         关键词（必填）
      sources   逗号分隔源过滤，默认全部：
                registry,smithery,modelscope,pulsemcp,glama
      limit     每源条数，默认 12
    """
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"ok": False, "error": "缺少 q 参数"}), 400
    sources_raw = request.args.get("sources", "").strip()
    sources = [s.strip() for s in sources_raw.split(",") if s.strip()] or None
    try:
        limit = int(request.args.get("limit", 12))
    except ValueError:
        limit = 12
    try:
        result = search_mcp_market(q, sources=sources, limit_per_source=max(1, min(limit, 30)))
        result["source_labels"] = SOURCE_LABELS
        result["source_order"] = list(SOURCE_PRIORITY)
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/mcp/market-status", methods=["GET"])
def mcp_market_status():
    """返回市场源依赖状态（如 PulseMCP API Key 是否已配置）。"""
    import os
    configured = bool(os.environ.get("PULSEMCP_API_KEY", "").strip())
    return jsonify({
        "ok": True,
        "configured": configured,
        "pulsemcp": {
            "configured": configured,
            "mode": "v0.1" if configured else "v0beta",
            "docs_url": "https://www.pulsemcp.com/api/docs/v0.1",
            "api_url": "https://www.pulsemcp.com/api",
            "mailto": "mailto:hello@pulsemcp.com",
        },
    })


@app.route("/api/mcp/detail", methods=["GET"])
def mcp_detail():
    """获取 MCP 详情 / 可安装配置。

    兼容旧参数 owner+name（默认 modelscope）；
    新参数：source + id（及可选 owner/name）。
    """
    source = (request.args.get("source") or "").strip().lower() or "modelscope"
    sid = request.args.get("id", "").strip()
    owner = request.args.get("owner", "").strip()
    name = request.args.get("name", "").strip()
    if source == "modelscope" and (not owner or not name) and not sid:
        return jsonify({"ok": False, "error": "缺少 owner/name 或 id"}), 400
    if source != "modelscope" and not sid and not (owner and name) and not name:
        return jsonify({"ok": False, "error": "缺少 id 或 owner/name"}), 400

    detail_data: Any = None
    install_info: Any = None
    install_error: Optional[str] = None
    repo_url = (request.args.get("repo_url") or "").strip()

    # 先尽量拉取原始详情（便于「查看配置」）
    try:
        if source == "modelscope":
            from lib.mcp_market import ModelScopeClient
            # 必须优先用完整 id（如 @modelcontextprotocol/github）；
            # item.name 常为展示名「GitHub」，不能用来拼详情路径。
            detail_data = ModelScopeClient().detail(
                server_id=sid,
                owner=owner if not sid else "",
                name=name if not sid else "",
            )
        elif source == "registry":
            from lib.mcp_market import RegistryClient
            detail_data = RegistryClient().detail(sid or name)
        elif source == "smithery":
            from lib.mcp_market import SmitheryClient
            detail_data = SmitheryClient().detail(sid or name)
        elif source == "glama":
            from lib.mcp_market import GlamaClient, _glama_ns_slug, _glama_repo_fallback
            ns, slug = _glama_ns_slug(server_id=sid, owner=owner, name=name)
            try:
                detail_data = GlamaClient().detail(namespace=ns, slug=slug, server_id=sid)
            except Exception:
                # 详情失败不立刻判死：resolve 仍可从 GitHub 仓库自动解析安装 JSON
                fallback_repo = _glama_repo_fallback(ns, slug, repo_url)
                detail_data = {
                    "id": sid or (f"{ns}/{slug}" if ns and slug else ""),
                    "name": name or slug,
                    "namespace": ns,
                    "slug": slug,
                    "description": "",
                    "repository": {"url": fallback_repo} if fallback_repo else {},
                    "url": "",
                }
        elif source == "pulsemcp":
            from lib.mcp_market import PulseMCPClient
            hits = PulseMCPClient().search(sid or name, limit=5)
            detail_data = (hits[0].get("raw") if hits else None) or {"id": sid or name}
    except Exception as e:
        # 详情失败时仍尝试 resolve_install，并把错误落到 install_error（避免整页硬失败）
        install_error = f"获取详情失败: {e}"
        detail_data = None

    try:
        # Glama：把已拉取/降级的 detail 传入，避免再打一次 Glama 详情；仓库解析仍会请求 GitHub
        install_info = resolve_mcp_install(
            source=source,
            id=sid,
            owner=owner,
            name=name,
            detail=detail_data if source == "glama" else None,
            repo_url=repo_url,
        )
        if install_info:
            install_error = None
    except Exception as e:
        msg = str(e)
        if not install_error:
            install_error = msg
        elif source == "glama":
            install_error = msg
        elif not msg.startswith("获取详情"):
            install_error = f"{install_error}；安装解析: {msg}"

    if detail_data is None and install_info is None:
        return jsonify({"ok": False, "error": install_error or "获取详情失败"}), 500

    return jsonify({
        "ok": True,
        "data": detail_data or (install_info or {}).get("detail"),
        "install": install_info,
        "install_error": install_error,
    })


# ============================================================
# Plugin 目录辅助（template/plugins/ + config/plugins/ 双目录）
# ============================================================
def _plugin_search_dirs() -> list[Path]:
    """返回插件搜索目录列表（优先级：config/plugins/ → template/plugins/）。

    config/plugins/ 是用户创建/导入的运行态插件；
    template/plugins/ 是内置预置插件（随程序分发，只读）。
    """
    dirs = []
    if CONFIG_PLUGINS_DIR.exists():
        dirs.append(CONFIG_PLUGINS_DIR)
    if PLUGINS_DIR.exists():
        dirs.append(PLUGINS_DIR)
    return dirs


def _resolve_plugin_path(fname: str) -> Path | None:
    """在 config/plugins/ 和 template/plugins/ 中查找插件文件。

    Returns:
        Path 或 None（未找到）。config/plugins/ 优先。
    """
    for d in _plugin_search_dirs():
        p = (d / fname).resolve()
        try:
            p.relative_to(d.resolve())
        except ValueError:
            continue  # 非法路径，跳过
        if p.exists():
            return p
    return None


# ============================================================
# Plugin API
# ============================================================
def _collect_plugin_skill_dirs(cfg: dict) -> list:
    """从插件配置中收集本地存在的 skill 目录列表。

    遍历 plugin.yaml 的 skills 字段，在三个 skill 目录中搜索匹配的目录：
      1. config/skills/      - 项目级复制的技能（优先）
      2. .agents/skills/     - 项目级安装的技能（下载/插件安装目标）
      3. template/skills/    - 内置预置技能（只读缓存）

    Returns:
        [(skill_name, Path), ...]  仅返回实际存在的目录。
    """
    skills_list = cfg.get("skills", []) or []
    result: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for s in skills_list:
        if isinstance(s, dict):
            name = s.get("skill") or s.get("name") or ""
        else:
            name = str(s)
        if not name or name in seen:
            continue
        seen.add(name)
        for base in (PROJECT_SKILLS_DIR, DOT_AGENTS_SKILLS, AGENTS_SKILLS_CACHE):
            skill_dir = base / name
            if skill_dir.exists() and skill_dir.is_dir():
                result.append((name, skill_dir))
                break
    return result


def _add_dir_to_zip(zf: zipfile.ZipFile, src_dir: Path, arc_prefix: str) -> int:
    """将 src_dir 下的所有文件写入 zip，arc 路径前缀为 arc_prefix。返回文件数。"""
    count = 0
    for f in src_dir.rglob("*"):
        if not f.is_file():
            continue
        # 跳过 .git 目录
        if ".git" in f.parts:
            continue
        rel = f.relative_to(src_dir)
        arc = str(Path(arc_prefix) / rel)
        zf.write(f, arcname=arc)
        count += 1
    return count


def _strip_api_keys_deep(obj):
    """深拷贝并将所有 api_key 字段置空（脱敏导出用）。"""
    import copy
    cloned = copy.deepcopy(obj)
    def _walk(o):
        if isinstance(o, dict):
            for k, v in list(o.items()):
                if k == "api_key" and isinstance(v, str):
                    o[k] = ""
                else:
                    _walk(v)
        elif isinstance(o, list):
            for item in o:
                _walk(item)
    _walk(cloned)
    return cloned


_KEY_PLACEHOLDER_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-[^\}]*)?\}")
_KEY_ENV_RE = re.compile(r"\benv:([A-Za-z_][A-Za-z0-9_]*)")


def _find_referenced_keys(*texts: str) -> set:
    """从多段文本中提取 ${KEY} 与 env:KEY 引用的密钥名集合。"""
    refs: set[str] = set()
    for text in texts:
        if not text:
            continue
        for m in _KEY_PLACEHOLDER_RE.finditer(text):
            refs.add(m.group(1))
        for m in _KEY_ENV_RE.finditer(text):
            refs.add(m.group(1))
    return refs


def _build_value_to_key_map() -> dict:
    """构建 {密钥明文值 -> key名} 反向映射，用于把明文替换为 ${KEY} 引用。"""
    try:
        full = _load_keys_full()
    except Exception:
        return {}
    all_keys = full.get("mcp", {}) if isinstance(full, dict) else {}
    mapping = {}
    for k, entry in all_keys.items():
        if isinstance(entry, dict):
            v = entry.get("value", "")
            if v and isinstance(v, str) and len(v) >= 8:  # 太短的值不替换，避免误匹配
                mapping[v] = k
    return mapping


def _replace_plaintext_with_refs(obj, value_map: dict):
    """深拷贝并把明文密钥值替换为 ${KEY} 引用（仅替换 api_key 字段和 ${...} 可识别的值）。

    替换策略：
    - api_key 字段：若值与 keys.yaml 某条目的 value 完全相同，替换为 ${KEY}
    - 其他字符串字段中的明文值也做替换（覆盖 env/args 等）
    """
    import copy
    cloned = copy.deepcopy(obj)

    def _walk(o):
        if isinstance(o, dict):
            for k, v in list(o.items()):
                if isinstance(v, str) and v in value_map:
                    o[k] = "${" + value_map[v] + "}"
                else:
                    _walk(v)
        elif isinstance(o, list):
            for i, item in enumerate(o):
                if isinstance(item, str) and item in value_map:
                    o[i] = "${" + value_map[item] + "}"
                else:
                    _walk(item)
    _walk(cloned)
    return cloned


def _build_keys_yaml_for_export(referenced: set, include_values: bool) -> str | None:
    """构建导出用 keys.yaml 内容（仅含被引用的密钥）。

    include_values=True  → vault 模式，含密钥明文值
    include_values=False → redacted 模式，值置空仅保留 key 名与描述
    """
    if not referenced:
        return None
    try:
        full = _load_keys_full()
    except Exception:
        return None
    all_keys = full.get("mcp", {}) if isinstance(full, dict) else {}
    exported = {}
    for k in sorted(referenced):
        if k in all_keys and isinstance(all_keys[k], dict):
            entry = all_keys[k]
            if include_values:
                exported[k] = {"value": entry.get("value", ""), "description": entry.get("description", "")}
            else:
                exported[k] = {"value": "", "description": entry.get("description", "")}
        else:
            exported[k] = {"value": "", "description": "（导出时缺失，请填写）"}
    if not exported:
        return None
    import yaml as _yaml
    return _yaml.dump({"mcp": exported}, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _collect_plugin_llm(cfg: dict, key_mode: str = "plain") -> str | None:
    """从 plugin.yaml 的 llm 列表中提取 provider 名，再从 llm.yaml 中提取对应配置（含 api_key）。

    key_mode:
      - plain: 原样导出（含 api_key 明文或 env: 引用）
      - vault: 明文 api_key 替换为 ${KEY} 引用（若 keys.yaml 有相同值），密钥值由 keys.yaml 单独导出
      - redacted: 脱敏导出（api_key 字段置空）
    返回 YAML 字符串（仅含声明的 provider），如无匹配返回 None。
    """
    llm_list = cfg.get("llm", []) or []
    if not llm_list:
        return None
    # 提取 plugin 声明的 provider 名
    provider_names = set()
    for item in llm_list:
        if isinstance(item, dict):
            p = item.get("provider", "").strip()
            if p:
                provider_names.add(p)
        elif isinstance(item, str):
            provider_names.add(item)
    if not provider_names:
        return None
    # 从 llm.yaml 中提取对应 provider
    try:
        llm_data = load_env_config_file(_ensure_llm_file())
    except Exception:
        return None
    llm_section = llm_data.get("llm", {}) if isinstance(llm_data, dict) else {}
    # vault 模式：构建明文→key名 反向映射，用于替换明文
    value_map = _build_value_to_key_map() if key_mode == "vault" else {}
    extracted = {"llm": {}}
    if "_active_provider" in llm_section:
        extracted["llm"]["_active_provider"] = llm_section["_active_provider"]
    if "_active_protocol" in llm_section:
        extracted["llm"]["_active_protocol"] = llm_section["_active_protocol"]
    found = False
    for pname in provider_names:
        if pname in llm_section and isinstance(llm_section[pname], dict):
            prov_cfg = llm_section[pname]
            if key_mode == "redacted":
                prov_cfg = _strip_api_keys_deep(prov_cfg)
            elif key_mode == "vault" and value_map:
                prov_cfg = _replace_plaintext_with_refs(prov_cfg, value_map)
            extracted["llm"][pname] = prov_cfg
            found = True
    if not found:
        return None
    import yaml as _yaml
    return _yaml.dump(extracted, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _collect_plugin_subagents(cfg: dict) -> str | None:
    """从 subagent.yaml 中提取 plugin 声明的 subagents，返回 YAML 字符串。"""
    sa_names = cfg.get("subagents", []) or []
    if not sa_names:
        return None
    if isinstance(sa_names, bool):
        return None  # true 不是列表
    name_set = set(str(n).strip() for n in sa_names if str(n).strip())
    if not name_set:
        return None
    try:
        sa_data = load_env_config_file(_ensure_subagent_file())
    except Exception:
        return None
    all_sa = sa_data.get("subagents", []) if isinstance(sa_data, dict) else []
    filtered = [s for s in all_sa if isinstance(s, dict) and s.get("name", "").strip() in name_set]
    if not filtered:
        return None
    import yaml as _yaml
    return _yaml.dump({"subagents": filtered}, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _collect_plugin_rules(cfg: dict) -> list[tuple[str, Path]]:
    """收集 plugin 声明的 rules .md 文件。

    Returns:
        [(rel_path, Path), ...]  仅返回存在的文件。
    """
    rule_paths = cfg.get("rules", []) or []
    if not rule_paths or isinstance(rule_paths, bool):
        return []
    result: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for r in rule_paths:
        rel = str(r).strip()
        if not rel or rel in seen:
            continue
        seen.add(rel)
        # 确保有 .md 扩展名
        if not rel.endswith(".md"):
            rel = rel + ".md"
        # 在 config/rules/ 和 template/rules/ 中查找
        for base in (RULES_DIR, RULES_TEMPLATE_DIR):
            p = base / rel
            if p.exists() and p.is_file():
                result.append((rel, p))
                break
    return result


def _collect_plugin_commands(cfg: dict) -> str | None:
    """从 cmd.yaml 中提取 plugin 声明的 commands，返回 YAML 字符串。"""
    cmd_names = cfg.get("commands", []) or []
    if not cmd_names or isinstance(cmd_names, bool):
        return None
    name_set = set(str(n).strip() for n in cmd_names if str(n).strip())
    if not name_set:
        return None
    try:
        cmd_data = load_env_config_file(_ensure_cmd_file())
    except Exception:
        return None
    all_cmds = cmd_data.get("commands", []) if isinstance(cmd_data, dict) else []
    filtered = [c for c in all_cmds if isinstance(c, dict) and c.get("name", "").strip() in name_set]
    if not filtered:
        return None
    import yaml as _yaml
    return _yaml.dump({"commands": filtered}, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _collect_plugin_hooks(cfg: dict) -> Path | None:
    """如果 plugin 声明了 hooks=true，返回 hooks.json 路径。"""
    hooks_flag = cfg.get("hooks")
    if not hooks_flag:
        return None
    try:
        path = _ensure_hooks_file()
        if path.exists():
            return path
    except Exception:
        pass
    return None


def _rewrite_plugin_for_file_export(cfg: dict, extras: set[str] | None) -> dict:
    """导出 zip 时重写 plugin.yaml：把内联 mcpServers/llm 改为文件引用。

    策略：
    - 若 extras 包含 'mcp' → 删除 cfg.mcpServers，改为 cfg.mcp_file = 'mcp.yaml'
    - 若 extras 包含 'llm' → 删除 cfg.llm（内联 provider 列表），改为 cfg.llm_file = 'llm.yaml'
    - 若 extras 包含 'keys' → 增加 cfg.keys_file = 'keys.yaml'（若 plugin.keys 非空）
    - skills 保持引用列表（不内联），本地 skill 目录已单独打包到 skills/ 下
    """
    import copy
    out = copy.deepcopy(cfg)
    if extras is None:
        return out
    if "mcp" in extras and out.get("mcpServers"):
        # 保留 mcpServers 名称列表作为引用（便于 plugin.yaml 表达依赖了哪些 MCP）
        out["mcp_servers_ref"] = list(out.get("mcpServers", {}).keys())
        out["mcp_file"] = "mcp.yaml"
        del out["mcpServers"]
    if "llm" in extras and out.get("llm"):
        # 保留 provider 名称列表作为引用
        llm_list = out.get("llm", [])
        if isinstance(llm_list, list):
            out["llm_ref"] = [
                (item.get("provider") if isinstance(item, dict) else str(item))
                for item in llm_list if item
            ]
        out["llm_file"] = "llm.yaml"
        del out["llm"]
    if "keys" in extras and out.get("keys"):
        out["keys_file"] = "keys.yaml"
    return out


def _add_plugin_extras_to_zip(zf: zipfile.ZipFile, cfg: dict, seen: set[str] | None = None,
                             key_mode: str = "plain", extras: set[str] | None = None) -> None:
    """将 plugin 关联的 llm/subagents/rules/commands/hooks 打包到 zip。

    Args:
        seen: 多插件导出时传入的去重集合，避免 llm.yaml / subagents.yaml 等
              同名文件重复写入 zip。单插件导出不传（None）时跳过去重。
        key_mode:
          - plain: 原样导出 llm.yaml（含 api_key），不导出 keys.yaml
          - vault: 明文替换为 ${KEY} 引用 + keys.yaml（含被引用密钥的明文值）
          - redacted: 脱敏 llm.yaml（api_key 置空）+ keys.yaml（仅结构与描述）
        extras: 选择性导出哪些配置文件，集合元素为 'llm'/'mcp'/'subagents'/'rules'/'commands'/'hooks'/'keys'。
                None 表示全部导出（向后兼容）。
    """
    def _should_write(name: str) -> bool:
        if seen is None:
            return True
        if name in seen:
            return False
        seen.add(name)
        return True

    def _extra_on(key: str) -> bool:
        return extras is None or key in extras

    # vault 模式下构建明文→key名 反向映射（供 mcpServers 替换用）
    value_map = _build_value_to_key_map() if key_mode == "vault" else {}

    # llm.yaml
    if _extra_on("llm"):
        llm_yaml_str = _collect_plugin_llm(cfg, key_mode)
        if llm_yaml_str and _should_write("llm.yaml"):
            zf.writestr("llm.yaml", llm_yaml_str)
    else:
        llm_yaml_str = ""

    # mcp.yaml（选择性导出：把 plugin 声明的 mcpServers 单独打包为 mcp.yaml）
    mcp_text = ""
    if _extra_on("mcp"):
        mcp_servers = cfg.get("mcpServers", {}) or {}
        if mcp_servers and isinstance(mcp_servers, dict):
            mcp_to_export = mcp_servers
            if key_mode == "vault" and value_map:
                mcp_to_export = _replace_plaintext_with_refs(mcp_servers, value_map)
            elif key_mode == "redacted":
                mcp_to_export = _strip_api_keys_deep(mcp_servers)
            import yaml as _yaml_mcp
            mcp_text = _yaml_mcp.dump({"mcpServers": mcp_to_export},
                                      allow_unicode=True, default_flow_style=False, sort_keys=False)
            if mcp_text and _should_write("mcp.yaml"):
                zf.writestr("mcp.yaml", mcp_text)

    # subagents.yaml
    if _extra_on("subagents"):
        sa_yaml_str = _collect_plugin_subagents(cfg)
        if sa_yaml_str and _should_write("subagents.yaml"):
            zf.writestr("subagents.yaml", sa_yaml_str)

    # rules/*.md
    if _extra_on("rules"):
        for rel, rule_path in _collect_plugin_rules(cfg):
            arc = f"rules/{rel}"
            if _should_write(arc):
                zf.write(rule_path, arcname=arc)

    # commands.yaml
    if _extra_on("commands"):
        cmd_yaml_str = _collect_plugin_commands(cfg)
        if cmd_yaml_str and _should_write("commands.yaml"):
            zf.writestr("commands.yaml", cmd_yaml_str)

    # hooks/hooks.json
    if _extra_on("hooks"):
        hooks_path = _collect_plugin_hooks(cfg)
        if hooks_path and _should_write("hooks/hooks.json"):
            zf.write(hooks_path, arcname="hooks/hooks.json")

    # 密钥库 keys.yaml：vault / redacted 模式下导出被引用的密钥
    if key_mode in ("vault", "redacted") and _extra_on("keys"):
        # 收集引用：llm.yaml + mcp.yaml/mcpServers + plugin.yaml 显式声明的 keys 字段
        refs = _find_referenced_keys(llm_yaml_str or "", mcp_text)
        # plugin.yaml 的 keys 字段（构建页显式选择的密钥名）
        declared_keys = cfg.get("keys", []) or []
        if isinstance(declared_keys, list):
            for k in declared_keys:
                if isinstance(k, str) and k.strip():
                    refs.add(k.strip())
        keys_yaml_str = _build_keys_yaml_for_export(refs, include_values=(key_mode == "vault"))
        if keys_yaml_str and _should_write("keys.yaml"):
            zf.writestr("keys.yaml", keys_yaml_str)


@app.route("/api/plugins", methods=["GET"])
def list_plugins():
    from lib.plugins import read_installed_plugins
    installed_names = set(read_installed_plugins(PROJECT_ROOT))
    plugins = []
    seen_files = set()  # 按文件名去重（config/plugins/ 优先覆盖 template/plugins/）
    # 合并扫描 config/plugins/ + template/plugins/
    for plugins_dir in _plugin_search_dirs():
        if not plugins_dir.exists():
            continue
        files = []
        for pat in ("*.plugin.yaml", "*.plugin.yml", "*.plugin.json"):
            files.extend(plugins_dir.glob(pat))
        for f in sorted(files):
            if f.name in seen_files:
                continue
            seen_files.add(f.name)
            try:
                cfg = load_env_config_file(f)
                if isinstance(cfg, dict) and "name" in cfg:
                    plugins.append({
                        "file": f.name,
                        "name": cfg.get("name"),
                        "version": cfg.get("version", ""),
                        "description": cfg.get("description", ""),
                        "author": cfg.get("author", ""),
                        "license": cfg.get("license", ""),
                        "keywords": cfg.get("keywords", []) or [],
                        "categories": cfg.get("categories", []) or [],
                        "homepage": cfg.get("homepage", ""),
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
    # 保留所有传入字段（标准字段 + AgentBuddy 扩展字段），避免丢弃 license/keywords/categories 等
    config: dict = {}
    # 标准字段（对齐 Claude Code / Codex CLI / VSCode）
    for k in ("$schema", "manifest_version", "name", "version", "description", "author",
              "license", "keywords", "homepage", "repository", "categories", "icon",
              "defaultEnabled", "dependencies", "userConfig", "channels",
              "interface", "apps"):
        if k in body and body[k] not in (None, "", [], {}):
            config[k] = body[k]
    # 必填字段兜底
    config["name"] = name
    config["version"] = (body.get("version", "1.0.0") or "1.0.0").strip()
    if "author" not in config:
        config["author"] = (body.get("author", "AgentBuddy") or "AgentBuddy").strip()
    # AgentBuddy 扩展字段（多 IDE 同步能力）
    for k in ("mcpServers", "skills", "llm", "subagents", "rules", "commands", "keys"):
        if k in body:
            config[k] = body[k] if body[k] is not None else ([] if k in ("skills", "llm", "subagents", "rules", "commands", "keys") else {})
    config["hooks"] = bool(body.get("hooks", False))
    # scripts 对齐 npm 生命周期（install/postinstall/preinstall/preuninstall/uninstall/postuninstall/prepare）
    scripts = body.get("scripts")
    if isinstance(scripts, dict) and scripts:
        cleaned = {k: v.strip() for k, v in scripts.items()
                   if isinstance(v, str) and v.strip()
                   and k in ("preinstall", "install", "postinstall",
                             "preuninstall", "uninstall", "postuninstall", "prepare")}
        if cleaned:
            config["scripts"] = cleaned
    # envVars（可选）
    if body.get("envVars") and isinstance(body["envVars"], dict):
        config["envVars"] = body["envVars"]
    # 安全文件名
    safe_name = "".join(c for c in name if c.isalnum() or c in ("-", "_"))
    out_path = CONFIG_PLUGINS_DIR / f"{safe_name}.plugin.yaml"
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
    path = _resolve_plugin_path(fname)
    if path is None:
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
    path = _resolve_plugin_path(fname)
    if path is None:
        return jsonify({"ok": False, "error": "文件不存在"}), 404
    try:
        path.unlink()
        return jsonify({"ok": True, "path": str(path.relative_to(PROJECT_ROOT))})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/plugin/export", methods=["GET"])
def export_plugin():
    """导出单个插件。支持两种格式：

    query:
      - file=xxx.plugin.yaml  （必填）
      - format=zip|yaml       （可选，默认 zip）

    format=zip:  返回 <plugin_name>.zip，含 plugin.yaml + skills/<name>/ 目录
    format=yaml: 返回原始 plugin.yaml 文件（不含 skills）
    """
    fname = (request.args.get("file") or "").strip()
    fmt = (request.args.get("format") or "zip").strip().lower()
    key_mode = (request.args.get("key_mode") or "plain").strip().lower()
    if key_mode not in ("plain", "vault", "redacted"):
        key_mode = "plain"
    # extras：选择性导出哪些配置文件（逗号分隔），None=全部
    extras_raw = (request.args.get("extras") or "").strip()
    extras: set[str] | None = None
    if extras_raw:
        extras = {e.strip() for e in extras_raw.split(",") if e.strip()}
    if not fname:
        return jsonify({"ok": False, "error": "缺少 file 参数"}), 400
    path = _resolve_plugin_path(fname)
    if path is None:
        return jsonify({"ok": False, "error": "文件不存在"}), 404

    # format=yaml：仅导出 plugin.yaml（向后兼容）
    if fmt == "yaml":
        try:
            buf = io.BytesIO(path.read_bytes())
            buf.seek(0)
            return send_file(buf, as_attachment=True, download_name=fname,
                             mimetype="application/yaml")
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    # format=zip（默认）：plugin.yaml + 关联 skills 目录
    try:
        cfg = load_env_config_file(path)
        plugin_name = cfg.get("name", path.stem)
        skill_dirs = _collect_plugin_skill_dirs(cfg)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            # 导出 zip 时重写 plugin.yaml：内联 mcpServers/llm 改为文件引用
            rewritten = _rewrite_plugin_for_file_export(cfg, extras)
            import yaml as _yaml_export
            plugin_yaml_str = _yaml_export.dump(rewritten, allow_unicode=True,
                                                default_flow_style=False, sort_keys=False)
            zf.writestr(fname, plugin_yaml_str)
            # skills 选择性导出
            if extras is None or "skills" in extras:
                for skill_name, skill_dir in skill_dirs:
                    _add_dir_to_zip(zf, skill_dir, arc_prefix=f"skills/{skill_name}")
            # 打包 llm/subagents/rules/commands/hooks（+ 可选 keys.yaml）
            _add_plugin_extras_to_zip(zf, cfg, key_mode=key_mode, extras=extras)

        buf.seek(0)
        safe_name = "".join(c for c in plugin_name if c.isalnum() or c in ("-", "_"))
        download = f"{safe_name or 'plugin'}.zip"
        return send_file(buf, as_attachment=True, download_name=download,
                         mimetype="application/zip")
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/plugin/export-all", methods=["GET"])
def export_all_plugins():
    """导出全部预定义插件 + 关联 skills 为 zip。

    zip 结构：
      - *.plugin.yaml  （所有插件配置）
      - skills/<skill_name>/...  （去重后的所有本地 skill）
    query:
      - key_mode=plain|vault|redacted  （可选，默认 plain）
    """
    key_mode = (request.args.get("key_mode") or "plain").strip().lower()
    if key_mode not in ("plain", "vault", "redacted"):
        key_mode = "plain"
    extras_raw = (request.args.get("extras") or "").strip()
    extras: set[str] | None = None
    if extras_raw:
        extras = {e.strip() for e in extras_raw.split(",") if e.strip()}
    buf = io.BytesIO()
    seen_skills: set[str] = set()
    seen_files: set[str] = set()
    seen_extras: set[str] = set()  # 去重 llm.yaml / subagents.yaml 等
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for plugins_dir in _plugin_search_dirs():
            if not plugins_dir.exists():
                continue
            for f in plugins_dir.glob("*.plugin.yaml"):
                if f.name in seen_files:
                    continue
                seen_files.add(f.name)
                try:
                    cfg = load_env_config_file(f)
                    # 重写 plugin.yaml（文件引用模式）
                    rewritten = _rewrite_plugin_for_file_export(cfg, extras)
                    import yaml as _yaml_all
                    zf.writestr(f.name, _yaml_all.dump(rewritten, allow_unicode=True,
                                                       default_flow_style=False, sort_keys=False))
                    if extras is None or "skills" in extras:
                        for skill_name, skill_dir in _collect_plugin_skill_dirs(cfg):
                            if skill_name in seen_skills:
                                continue
                            seen_skills.add(skill_name)
                            _add_dir_to_zip(zf, skill_dir, arc_prefix=f"skills/{skill_name}")
                    _add_plugin_extras_to_zip(zf, cfg, seen_extras, key_mode=key_mode, extras=extras)
                except Exception:
                    pass  # 单个插件解析失败不阻塞
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="plugins-export.zip",
                     mimetype="application/zip")


@app.route("/api/plugin/export-selected", methods=["GET"])
def export_selected_plugins():
    """导出选中的插件 + 关联 skills 为 zip。

    query:
      - files=a.plugin.yaml&files=b.plugin.yaml  （必填，可重复）
      - key_mode=plain|vault|redacted  （可选，默认 plain）

    zip 结构：
      - *.plugin.yaml  （选中的插件配置）
      - skills/<skill_name>/...  （去重后的所有关联 skill）
    """
    files = request.args.getlist("files")
    if not files:
        return jsonify({"ok": False, "error": "未选择任何插件"}), 400
    key_mode = (request.args.get("key_mode") or "plain").strip().lower()
    if key_mode not in ("plain", "vault", "redacted"):
        key_mode = "plain"
    extras_raw = (request.args.get("extras") or "").strip()
    extras: set[str] | None = None
    if extras_raw:
        extras = {e.strip() for e in extras_raw.split(",") if e.strip()}

    buf = io.BytesIO()
    seen_skills: set[str] = set()
    seen_extras: set[str] = set()  # 去重 llm.yaml / subagents.yaml 等
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in files:
            fname = fname.strip()
            if not fname:
                continue
            path = _resolve_plugin_path(fname)
            if path is None:
                continue  # 文件不存在，跳过
            try:
                cfg = load_env_config_file(path)
                # 重写 plugin.yaml（文件引用模式）
                rewritten = _rewrite_plugin_for_file_export(cfg, extras)
                import yaml as _yaml_sel
                zf.writestr(fname, _yaml_sel.dump(rewritten, allow_unicode=True,
                                                   default_flow_style=False, sort_keys=False))
                if extras is None or "skills" in extras:
                    for skill_name, skill_dir in _collect_plugin_skill_dirs(cfg):
                        if skill_name in seen_skills:
                            continue
                        seen_skills.add(skill_name)
                        _add_dir_to_zip(zf, skill_dir, arc_prefix=f"skills/{skill_name}")
                _add_plugin_extras_to_zip(zf, cfg, seen_extras, key_mode=key_mode, extras=extras)
            except Exception:
                pass  # 单个插件解析失败不阻塞
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="plugins-selected.zip",
                     mimetype="application/zip")


def _import_plugin_zip(buf: io.BytesIO, overwrite: bool) -> tuple:
    """从 zip 导入插件配置 + skills + llm/subagents/rules/commands/hooks。

    zip 结构（由 export_plugin / export_all_plugins 生成）：
      - *.plugin.yaml    → 写入 config/plugins/
      - skills/<name>/... → 复制到 config/skills/<name>/
      - llm.yaml          → 合并到 config/llm/llm.yaml（按 provider 合并）
      - subagents.yaml    → 合并到 config/subagent/subagent.yaml
      - rules/<path>.md   → 写入 config/rules/
      - commands.yaml     → 合并到 config/cmd/cmd.yaml
      - hooks/hooks.json  → 写入 config/hooks/hooks.json

    Returns:
        (response_dict, http_status)
    """
    imported_plugins: list[dict] = []
    imported_skills: list[str] = []
    imported_extras: list[str] = []
    skipped: list[dict] = []

    with zipfile.ZipFile(buf, "r") as zf:
        plugin_entries: list[tuple[str, bytes]] = []
        skill_entries: dict[str, list[str]] = {}
        llm_content: bytes | None = None
        mcp_content: bytes | None = None
        subagent_content: bytes | None = None
        rules_entries: list[tuple[str, bytes]] = []  # (rel_path, content)
        commands_content: bytes | None = None
        hooks_content: bytes | None = None
        keys_content: bytes | None = None

        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            if "__MACOSX" in name or Path(name).name.startswith("."):
                continue
            if name.endswith(".plugin.yaml") or name.endswith(".plugin.yml"):
                plugin_entries.append((name, zf.read(name)))
            elif name.startswith("skills/"):
                parts = Path(name).parts
                if len(parts) >= 2:
                    skill_name = parts[1]
                    skill_entries.setdefault(skill_name, []).append(name)
            elif name == "llm.yaml":
                llm_content = zf.read(name)
            elif name == "mcp.yaml":
                mcp_content = zf.read(name)
            elif name == "subagents.yaml":
                subagent_content = zf.read(name)
            elif name == "commands.yaml":
                commands_content = zf.read(name)
            elif name.startswith("rules/") and name.endswith(".md"):
                rel = name[len("rules/"):]
                rules_entries.append((rel, zf.read(name)))
            elif name == "hooks/hooks.json":
                hooks_content = zf.read(name)
            elif name in ("keys/keys.yaml", "keys.yaml"):
                keys_content = zf.read(name)

        # 导入 plugin yaml
        # 同时收集所有插件的 envVars，统一合并到 keys.yaml（仅初始化未存在的变量）
        plugin_envvars_list: list[dict] = []
        for arc, content in plugin_entries:
            fname = Path(arc).name
            try:
                data = yaml.safe_load(content.decode("utf-8"))
            except (yaml.YAMLError, UnicodeDecodeError):
                skipped.append({"file": fname, "reason": "YAML 解析失败"})
                continue
            if not isinstance(data, dict) or not data.get("name"):
                skipped.append({"file": fname, "reason": "无效插件配置（缺少 name）"})
                continue
            out_path = CONFIG_PLUGINS_DIR / fname
            if out_path.exists() and not overwrite:
                skipped.append({"file": fname, "reason": "已存在"})
                continue
            CONFIG_PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(content)
            imported_plugins.append({"file": fname, "name": data["name"]})
            # 收集 envVars（dict 类型，含 default/description/required 等元信息）
            ev = data.get("envVars")
            if isinstance(ev, dict) and ev:
                plugin_envvars_list.append(ev)

        # 将插件 envVars 初始化到 keys.yaml.mcp（不覆盖已有值）
        if plugin_envvars_list:
            try:
                keys_path = _ensure_keys_file()
                existing_keys = load_env_config_file(keys_path) or {}
                if not isinstance(existing_keys, dict):
                    existing_keys = {}
                if not isinstance(existing_keys.get("mcp"), dict):
                    existing_keys["mcp"] = {}
                env_updated = False
                for ev in plugin_envvars_list:
                    for var_name, var_info in ev.items():
                        if var_name in existing_keys["mcp"]:
                            continue  # 保留用户已配置的值，幂等
                        if isinstance(var_info, dict):
                            default_val = var_info.get("default", "")
                            # default 必须是字符串/数字等标量，否则落空字符串
                            if not isinstance(default_val, (str, int, float, bool)):
                                default_val = ""
                            existing_keys["mcp"][var_name] = default_val
                        else:
                            existing_keys["mcp"][var_name] = ""
                        env_updated = True
                if env_updated:
                    save_env_config_file(keys_path, existing_keys)
                    imported_extras.append("keys.yaml (envVars)")
            except Exception as e:
                skipped.append({"file": "keys.yaml", "reason": f"envVars 初始化失败: {e}"})

        # 导入 skills 目录
        for skill_name, arc_list in skill_entries.items():
            target = PROJECT_SKILLS_DIR / skill_name
            if target.exists() and not overwrite:
                skipped.append({"skill": skill_name, "reason": "已存在"})
                continue
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            target.mkdir(parents=True, exist_ok=True)
            for arc in arc_list:
                rel_parts = Path(arc).parts[2:]
                if not rel_parts:
                    continue
                dst = target.joinpath(*rel_parts)
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(zf.read(arc))
            imported_skills.append(skill_name)

        # 导入 llm.yaml（合并到 config/llm/llm.yaml）
        if llm_content:
            try:
                imported_llm = yaml.safe_load(llm_content.decode("utf-8"))
                if isinstance(imported_llm, dict) and isinstance(imported_llm.get("llm"), dict):
                    llm_path = _ensure_llm_file()
                    existing = load_env_config_file(llm_path)
                    if not isinstance(existing, dict):
                        existing = {}
                    if not isinstance(existing.get("llm"), dict):
                        existing["llm"] = {}
                    for pname, pcfg in imported_llm["llm"].items():
                        if pname.startswith("_"):
                            if pname not in existing["llm"]:
                                existing["llm"][pname] = pcfg
                        else:
                            existing["llm"][pname] = pcfg
                    save_env_config_file(llm_path, existing)
                    imported_extras.append("llm.yaml")
            except Exception as e:
                skipped.append({"file": "llm.yaml", "reason": str(e)})

        # 导入 mcp.yaml（合并 mcpServers 到 config/mcp/mcp.yaml）
        if mcp_content:
            try:
                imported_mcp = yaml.safe_load(mcp_content.decode("utf-8"))
                if isinstance(imported_mcp, dict) and isinstance(imported_mcp.get("mcpServers"), dict):
                    full = _load_mcp_yaml_full()
                    if not isinstance(full.get("mcpServers"), dict):
                        full["mcpServers"] = {}
                    for sname, scfg in imported_mcp["mcpServers"].items():
                        full["mcpServers"][sname] = scfg  # 覆盖同名
                    _save_mcp_yaml_full(full)
                    imported_extras.append("mcp.yaml")
            except Exception as e:
                skipped.append({"file": "mcp.yaml", "reason": str(e)})

        # 导入 subagents.yaml（合并到 config/subagent/subagent.yaml）
        if subagent_content:
            try:
                imported_sa = yaml.safe_load(subagent_content.decode("utf-8"))
                if isinstance(imported_sa, dict) and isinstance(imported_sa.get("subagents"), list):
                    sa_path = _ensure_subagent_file()
                    existing = load_env_config_file(sa_path)
                    if not isinstance(existing, dict):
                        existing = {"subagents": []}
                    if not isinstance(existing.get("subagents"), list):
                        existing["subagents"] = []
                    existing_names = set(s.get("name") for s in existing["subagents"] if isinstance(s, dict))
                    for sa in imported_sa["subagents"]:
                        if isinstance(sa, dict) and sa.get("name") not in existing_names:
                            existing["subagents"].append(sa)
                            existing_names.add(sa.get("name"))
                    save_env_config_file(sa_path, existing)
                    imported_extras.append("subagents.yaml")
            except Exception as e:
                skipped.append({"file": "subagents.yaml", "reason": str(e)})

        # 导入 rules/*.md → config/rules/
        for rel, content in rules_entries:
            if ".." in Path(rel).parts:
                continue
            dst = RULES_DIR / rel
            if dst.exists() and not overwrite:
                skipped.append({"rule": rel, "reason": "已存在"})
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(content)
            imported_extras.append(f"rules/{rel}")

        # 导入 commands.yaml（合并到 config/cmd/cmd.yaml）
        if commands_content:
            try:
                imported_cmd = yaml.safe_load(commands_content.decode("utf-8"))
                if isinstance(imported_cmd, dict) and isinstance(imported_cmd.get("commands"), list):
                    cmd_path = _ensure_cmd_file()
                    existing = load_env_config_file(cmd_path)
                    if not isinstance(existing, dict):
                        existing = {"commands": []}
                    if not isinstance(existing.get("commands"), list):
                        existing["commands"] = []
                    existing_names = set(c.get("name") for c in existing["commands"] if isinstance(c, dict))
                    for cmd in imported_cmd["commands"]:
                        if isinstance(cmd, dict) and cmd.get("name") not in existing_names:
                            existing["commands"].append(cmd)
                            existing_names.add(cmd.get("name"))
                    save_env_config_file(cmd_path, existing)
                    imported_extras.append("commands.yaml")
            except Exception as e:
                skipped.append({"file": "commands.yaml", "reason": str(e)})

        # 导入 hooks/hooks.json → config/hooks/hooks.json
        if hooks_content:
            try:
                hooks_path = _ensure_hooks_file()
                hooks_path.write_bytes(hooks_content)
                imported_extras.append("hooks/hooks.json")
            except Exception as e:
                skipped.append({"file": "hooks/hooks.json", "reason": str(e)})

        # 导入 keys.yaml → 合并到 config/keys.yaml（不覆盖已有值）
        if keys_content:
            try:
                imported_keys = yaml.safe_load(keys_content.decode("utf-8"))
                if isinstance(imported_keys, dict) and isinstance(imported_keys.get("mcp"), dict):
                    full = _load_keys_full()
                    if not isinstance(full.get("mcp"), dict):
                        full["mcp"] = {}
                    added = 0
                    for k, entry in imported_keys["mcp"].items():
                        if k in full["mcp"] and isinstance(full["mcp"][k], dict) and full["mcp"][k].get("value"):
                            continue  # 保留用户已配置的值
                        full["mcp"][k] = _normalize_key_entry(entry)
                        added += 1
                    if added:
                        _save_keys_full(full)
                    imported_extras.append(f"keys.yaml (+{added})")
            except Exception as e:
                skipped.append({"file": "keys.yaml", "reason": str(e)})

    result = {
        "ok": True,
        "plugins": imported_plugins,
        "skills": imported_skills,
        "extras": imported_extras,
        "skipped": skipped,
        "plugin_count": len(imported_plugins),
        "skill_count": len(imported_skills),
        "extras_count": len(imported_extras),
    }
    return (jsonify(result), 200)


@app.route("/api/plugin/import", methods=["POST"])
def import_plugin():
    """导入插件（支持 zip 包或 yaml 文本）。

    支持两种请求格式：
    1. multipart/form-data（推荐）：上传文件（.zip 或 .yaml/.yml）
       - file: 文件字段
       - overwrite: 可选，"true" 时覆盖同名文件
       zip 包含 plugin.yaml + skills/ 目录时一并导入。
    2. application/json（向后兼容）：{filename, content, overwrite}
    """
    content_type = request.content_type or ""

    # ---- multipart/form-data：文件上传模式 ----
    if "multipart/form-data" in content_type:
        uploaded = request.files.get("file")
        if not uploaded:
            return jsonify({"ok": False, "error": "缺少 file 字段"}), 400
        fname = uploaded.filename or ""
        overwrite = request.form.get("overwrite", "").lower() in ("true", "1", "yes")

        if fname.lower().endswith(".zip"):
            try:
                buf = io.BytesIO(uploaded.read())
                return _import_plugin_zip(buf, overwrite)
            except zipfile.BadZipFile:
                return jsonify({"ok": False, "error": "无效的 zip 文件"}), 400
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 500
        elif fname.endswith((".plugin.yaml", ".plugin.yml", ".yaml", ".yml")):
            try:
                content = uploaded.read().decode("utf-8")
            except UnicodeDecodeError:
                return jsonify({"ok": False, "error": "文件编码不是 UTF-8"}), 400
        else:
            return jsonify({"ok": False, "error": "仅支持 .zip / .yaml / .yml 文件"}), 400

        # 走 yaml 文本导入流程（与 JSON 模式共用下方逻辑）
        body = {"filename": fname, "content": content, "overwrite": overwrite}
    else:
        # ---- application/json：向后兼容 ----
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
    out_path = CONFIG_PLUGINS_DIR / safe_name
    overwrite = bool(body.get("overwrite"))
    if out_path.exists() and not overwrite:
        return jsonify({"ok": False, "error": "exists",
                        "msg": f"{safe_name} 已存在，是否覆盖？"}), 409
    try:
        CONFIG_PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
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
    # 在 config/plugins/ + template/plugins/ 中查找
    plugin_file = None
    for plugins_dir in _plugin_search_dirs():
        for pat in ("*.plugin.yaml", "*.plugin.yml", "*.plugin.json"):
            for f in plugins_dir.glob(pat):
                try:
                    cfg = load_env_config_file(f)
                    if isinstance(cfg, dict) and cfg.get("name") == name:
                        plugin_file = f
                        break
                except Exception:
                    continue
            if plugin_file:
                break
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
    plugin_path = _resolve_plugin_path(fname)
    if plugin_path is None:
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

                def _skill_exists(name):
                    """检查 skill 是否已存在于 config/skills/ 或 .agents/skills/。"""
                    return (PROJECT_ROOT / "config" / "skills" / name).exists() or \
                           (DOT_AGENTS_SKILLS / name).exists()

                # Step 1: 已存在则跳过（仅单技能）
                if not is_whole_repo and _skill_exists(skill_name):
                    yield f"data: [-] Skill already exists: {skill_name}, skipping\n\n"
                    continue

                # Step 2: source 有效 → 执行 source 命令
                rc = None
                if has_explicit_source:
                    rc = yield from _stream_process_rc(cmd, cwd=PROJECT_ROOT)
                    if rc == 0:
                        # 验证（整仓库跳过目录验证）
                        if is_whole_repo or _skill_exists(skill_name):
                            yield f"data: [OK] Skill installed via source: {skill_name}\n\n"
                            continue
                        yield f"data: [!] source 命令成功但目录未找到，尝试 find-skills\n\n"
                    else:
                        yield f"data: [!] source 安装失败(rc={rc})，尝试 find-skills\n\n"

                # Step 3: find-skills 按名查找
                find_cmd = f"npx --yes skills add {skill_name} -y"
                rc = yield from _stream_process_rc(find_cmd, cwd=PROJECT_ROOT)
                if rc == 0 and (is_whole_repo or _skill_exists(skill_name)):
                    yield f"data: [OK] Skill installed from marketplace: {skill_name}\n\n"
                    continue

                # Step 4: 本地缓存（仅单技能）→ config/skills/
                # 搜索五个缓存源（优先级：项目级 → 全局 IDE 目录 → template 预置）
                if not is_whole_repo:
                    cache_dirs = [
                        PROJECT_ROOT / "config" / "skills" / skill_name,
                        DOT_AGENTS_SKILLS / skill_name,
                        PROJECT_ROOT / "template" / "skills" / skill_name,
                        Path.home() / ".zcode" / "skills" / skill_name,
                        Path.home() / ".config" / "skills" / skill_name,
                    ]
                    cache = next((d for d in cache_dirs if d.exists()), None)
                    if cache:
                        yield f"data: [-] Copying from local cache: {skill_name}\n\n"
                        try:
                            import shutil
                            target = PROJECT_ROOT / "config" / "skills" / skill_name
                            target.parent.mkdir(parents=True, exist_ok=True)
                            if target.exists():
                                shutil.rmtree(target, ignore_errors=True)
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

    Body: {ide: <IDE key>, mode: "cli" | "app", force?: bool}
    force=true：跳过系统卸载程序，直接强删目录（用于 GUI 卸载器卡死/超时/残留场景）
    """
    body = request.get_json(silent=True) or {}
    ide_key = (body.get("ide") or "").strip()
    mode = (body.get("mode") or "cli").strip()
    force = bool(body.get("force", False))
    if not ide_key:
        return jsonify({"ok": False, "error": "missing ide"}), 400
    if mode not in ("cli", "app"):
        return jsonify({"ok": False, "error": "mode must be 'cli' or 'app'"}), 400
    if ide_key not in IDE_INSTALL_META:
        return jsonify({"ok": False, "error": f"unsupported IDE: {ide_key}"}), 400
    try:
        result = uninstall_ide(ide_key, mode, force=force)
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


# ============================================================
# IDE 图标提取（macOS 从 .app 包读取真实程序图标）
# ============================================================
IDE_ICON_CACHE_DIR = PROJECT_ROOT / "tools" / "dist-ui" / "ide-icons"
# 防御：如果路径被错误地创建为文件，先删除再建目录
if IDE_ICON_CACHE_DIR.exists() and not IDE_ICON_CACHE_DIR.is_dir():
    IDE_ICON_CACHE_DIR.unlink()
IDE_ICON_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _find_app_icon_path(app_path: str) -> Path | None:
    """从 macOS .app 包内查找最佳图标文件（优先 PNG，其次 ICNS）。

    查找顺序：
    1. Info.plist 的 CFBundleIconFile 指定的文件（去掉扩展名后尝试 .icns/.png）
    2. Resources/ 目录下名为 icon.icns / app.icns / <AppName>.icns
    3. Resources/ 目录下任意 .png（取文件名含 icon/logo 的）
    """
    import plistlib
    app_p = Path(app_path)
    if not app_p.exists() or not app_path.endswith(".app"):
        return None
    resources_dir = app_p / "Contents" / "Resources"
    if not resources_dir.exists():
        return None

    # 1. 解析 Info.plist 的 CFBundleIconFile
    info_plist = app_p / "Contents" / "Info.plist"
    if info_plist.exists():
        try:
            with open(info_plist, "rb") as f:
                plist = plistlib.load(f)
            icon_name = plist.get("CFBundleIconFile", "") or plist.get("CFBundleIcons", {}).get("CFBundlePrimaryIcon", {}).get("CFBundleIconFile", "")
            if icon_name:
                # 去掉扩展名后尝试 .icns / .png
                base = icon_name.rsplit(".", 1)[0] if "." in icon_name else icon_name
                for ext in (".icns", ".png"):
                    for cand in (resources_dir / (icon_name + ext if not icon_name.endswith(ext) else icon_name),
                                 resources_dir / (base + ext)):
                        if cand.exists():
                            return cand
                # 直接用 icon_name
                direct = resources_dir / icon_name
                if direct.exists():
                    return direct
        except Exception:
            pass

    # 2. 常见命名
    common_names = ["icon.icns", "app.icns", "App.icns", "Icon.icns"]
    app_stem = app_p.stem  # 如 "Trae CN"
    common_names += [f"{app_stem}.icns", f"{app_stem}.png", "icon.png", "app.png"]
    for name in common_names:
        cand = resources_dir / name
        if cand.exists():
            return cand

    # 3. 任意 .icns / .png（优先含 icon/logo 的）
    candidates = []
    for p in resources_dir.iterdir():
        if p.suffix.lower() in (".icns", ".png"):
            score = 0
            low = p.name.lower()
            if "icon" in low: score += 3
            if "logo" in low: score += 2
            if "app" in low: score += 1
            if p.suffix.lower() == ".png": score += 1
            candidates.append((score, p))
    if candidates:
        candidates.sort(key=lambda x: -x[0])
        return candidates[0][1]
    return None


def _icns_to_png(icns_path: Path, out_png: Path) -> bool:
    """用 macOS 自带 sips 将 .icns 转为 .png。"""
    import subprocess
    try:
        r = subprocess.run(
            ["sips", "-s", "format", "png", str(icns_path), "--out", str(out_png)],
            capture_output=True, timeout=10,
        )
        return r.returncode == 0 and out_png.exists()
    except Exception:
        return False


def _extract_windows_exe_icon(exe_path: str, out_png: Path) -> bool:
    """从 Windows .exe 提取图标并保存为 PNG。

    使用 PowerShell + System.Drawing.Icon.ExtractAssociatedIcon（.NET 内置，无需额外依赖）。
    返回 32x32 图标，对 64px 容器足够清晰。
    """
    import subprocess
    if sys.platform != "win32" or not exe_path:
        return False
    if not Path(exe_path).exists():
        return False
    # PowerShell 单引号字符串字面量，转义内部单引号
    exe_ps = exe_path.replace("'", "''")
    out_ps = str(out_png).replace("'", "''")
    ps_script = (
        f"$exe = '{exe_ps}'; "
        f"$out = '{out_ps}'; "
        "Add-Type -AssemblyName System.Drawing; "
        "$icon = [System.Drawing.Icon]::ExtractAssociatedIcon($exe); "
        "if ($null -eq $icon) { exit 2 }; "
        "$bmp = $icon.ToBitmap(); "
        "$bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png); "
        "$bmp.Dispose(); $icon.Dispose()"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True, timeout=10,
        )
        return r.returncode == 0 and out_png.exists() and out_png.stat().st_size > 0
    except Exception:
        return False


@app.route("/api/ide/icon/<ide_key>")
def api_ide_icon(ide_key: str):
    """返回 IDE 的真实程序图标（PNG）。

    - macOS：从 .app 包提取 ICNS/PNG，ICNS 用 sips 转 PNG
    - Windows：从 .exe 用 PowerShell + System.Drawing 提取图标
    - 其他平台 / 未安装：返回 404 让前端回退到字母
    缓存到 tools/dist-ui/ide-icons/<key>.png，避免重复提取。
    404 响应带 no-store，避免前端缓存"未安装"状态后无法刷新。
    """
    from flask import Response

    def _not_found(msg: str) -> Response:
        return Response(msg, status=404, mimetype="text/plain", headers={"Cache-Control": "no-store"})

    # 白名单校验
    if ide_key not in IDE_INSTALL_META:
        return _not_found("not found")

    # 防御：每次请求前确保缓存目录存在且是目录（防止被旧进程/外部误删后变成文件）
    if IDE_ICON_CACHE_DIR.exists() and not IDE_ICON_CACHE_DIR.is_dir():
        try:
            IDE_ICON_CACHE_DIR.unlink()
        except Exception:
            pass
    IDE_ICON_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    cached = IDE_ICON_CACHE_DIR / f"{ide_key}.png"
    # 缓存命中（且非 0 字节）
    if cached.exists() and cached.is_file() and cached.stat().st_size > 0:
        return send_file(cached, mimetype="image/png", max_age=86400)

    # 查找已安装 IDE 的 app 路径
    info = detect_ide(ide_key)
    app_path = info.get("app_path", "") if info.get("installed") else ""
    if not app_path:
        # 未安装时，macOS 从 uninstall_cmd_mac 解析默认 .app 路径（如 /Applications/Claude.app）
        # 这样未安装但用户之前装过的 IDE 仍能提取图标
        import re
        meta = IDE_INSTALL_META.get(ide_key, {})
        uninstall_cmd = meta.get("app_install", {}).get("uninstall_cmd_mac", "")
        m = re.search(r"(/[^\s']+\.app)", uninstall_cmd)
        if m:
            app_path = m.group(1)

    # Windows：从 .exe 提取图标
    if app_path and app_path.lower().endswith(".exe"):
        if _extract_windows_exe_icon(app_path, cached):
            return send_file(cached, mimetype="image/png", max_age=86400)
        return _not_found("extract failed")

    # macOS：从 .app 包提取图标
    if not app_path or not app_path.endswith(".app"):
        return _not_found("not installed")

    icon_file = _find_app_icon_path(app_path)
    if not icon_file:
        return _not_found("no icon")

    # PNG 直接复制；ICNS 用 sips 转换
    if icon_file.suffix.lower() == ".png":
        try:
            import shutil
            shutil.copyfile(icon_file, cached)
            return send_file(cached, mimetype="image/png", max_age=86400)
        except Exception:
            return Response("copy failed", status=500, mimetype="text/plain")
    elif icon_file.suffix.lower() == ".icns":
        if _icns_to_png(icon_file, cached):
            return send_file(cached, mimetype="image/png", max_age=86400)
        return Response("convert failed", status=500, mimetype="text/plain")
    else:
        return _not_found("unsupported format")


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
    parser = argparse.ArgumentParser(description="飞翼 Web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    _ensure_llm_file()
    _ensure_mcp_config_file()

    url = f"http://{args.host}:{args.port}"
    print(f"[Config UI] 服务启动中: {url}")
    print(f"[Config UI] 项目根: {PROJECT_ROOT}")
    print(f"[Config UI] Ctrl+C 退出")

    # 启动时校验 IDE_INSTALL_META 完整性，漏配字段会在此处报警
    meta_warnings = validate_ide_meta()
    if meta_warnings:
        print(f"[Config UI] ⚠ IDE 安装元数据校验发现 {len(meta_warnings)} 处漏配：")
        for w in meta_warnings:
            print(f"  - {w}")
    else:
        print(f"[Config UI] ✓ IDE 安装元数据校验通过（{len(IDE_INSTALL_META)} 个 IDE）")

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


# ============================================================
# Rules API（config/rules/ + template/rules/ 双目录，.md 文件 + frontmatter）
# ============================================================
# 目录名 → 岗位显示名（frontmatter 无 role 时回退）
_RULE_DIR_ROLE_MAP = {
    "backend": "后端",
    "frontend": "前端",
    "git": "Git",
    "security": "工程",
    "testing": "测试",
    "design": "设计",
    "product": "产品",
    "api": "协作",
}


def _parse_rule_frontmatter(content: str) -> dict:
    """解析规则 .md 文件的 frontmatter，返回元信息 dict。"""
    meta = {"description": "", "alwaysApply": False, "globs": "", "scene": "", "role": ""}
    if not content.startswith("---"):
        return meta
    parts = content.split("---", 2)
    if len(parts) < 3:
        return meta
    fm_text = parts[1].strip()
    for line in fm_text.split("\n"):
        line = line.strip()
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if key in ("description", "globs", "scene", "role"):
            meta[key] = val.strip('"').strip("'")
        elif key == "alwaysApply":
            meta[key] = val.lower() in ("true", "yes", "1")
    return meta


def _scan_rules_dir(base: Path, source_label: str) -> list:
    """扫描 rules 目录（含子目录），返回规则列表。"""
    rules = []
    if not base.exists():
        return rules
    for f in sorted(base.rglob("*.md")):
        if f.name.startswith(".") or f.name == "README.md":
            continue
        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            continue
        meta = _parse_rule_frontmatter(content)
        rel = f.relative_to(base)
        # category = 第一级子目录名（无子目录则为空）
        parts = rel.parts
        category = parts[0] if len(parts) > 1 else ""
        # 岗位：优先 frontmatter.role，否则用目录映射 / 目录名
        role = (meta.get("role") or "").strip()
        if not role and category:
            role = _RULE_DIR_ROLE_MAP.get(category, category)
        name = f.stem  # 文件名（不含 .md）
        rules.append({
            "name": name,
            "path": str(rel),
            "category": category,
            "role": role,
            "description": meta["description"],
            "alwaysApply": meta["alwaysApply"],
            "globs": meta["globs"],
            "scene": meta["scene"],
            "source": source_label,
            "size": f.stat().st_size,
        })
    return rules


def _rules_search_dirs() -> list:
    """返回 rules 搜索目录列表（config/rules/ 优先，template/rules/ 其次）。"""
    dirs = []
    if RULES_DIR.exists():
        dirs.append((RULES_DIR, "config"))
    if RULES_TEMPLATE_DIR.exists():
        dirs.append((RULES_TEMPLATE_DIR, "template"))
    return dirs


def _resolve_rule_path(rel_path: str) -> Path | None:
    """在 config/rules/ 和 template/rules/ 中查找规则文件。"""
    for base, _ in _rules_search_dirs():
        p = (base / rel_path).resolve()
        try:
            p.relative_to(base.resolve())
        except ValueError:
            continue
        if p.exists() and p.is_file():
            return p
    return None


@app.route("/api/rules", methods=["GET"])
def list_rules():
    """列出所有规则（合并 config/rules/ + template/rules/，按 path 去重，config 优先）。"""
    all_rules = []
    seen_paths = set()
    for base, label in _rules_search_dirs():
        for r in _scan_rules_dir(base, label):
            if r["path"] in seen_paths:
                continue
            seen_paths.add(r["path"])
            all_rules.append(r)
    return jsonify({"ok": True, "data": all_rules, "count": len(all_rules)})


@app.route("/api/rules/content", methods=["GET"])
def get_rule_content():
    """获取规则文件原始内容。Query: path=relative/path.md"""
    rel = (request.args.get("path") or "").strip()
    if not rel:
        return jsonify({"ok": False, "error": "缺少 path 参数"}), 400
    path = _resolve_rule_path(rel)
    if path is None:
        return jsonify({"ok": False, "error": "文件不存在"}), 404
    try:
        content = path.read_text(encoding="utf-8")
        return jsonify({"ok": True, "content": content, "path": rel,
                        "writable": RULES_DIR in path.parents or path.parent == RULES_DIR})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/rules/save", methods=["POST"])
def save_rule():
    """保存规则文件。Body: {path, content}。写入 config/rules/。"""
    body = request.get_json(force=True)
    rel = (body.get("path") or "").strip()
    content = body.get("content") or ""
    if not rel:
        return jsonify({"ok": False, "error": "缺少 path 参数"}), 400
    # 安全：路径不能含 ..
    if ".." in Path(rel).parts:
        return jsonify({"ok": False, "error": "非法路径"}), 400
    out_path = (RULES_DIR / rel).resolve()
    try:
        out_path.relative_to(RULES_DIR.resolve())
    except ValueError:
        return jsonify({"ok": False, "error": "非法路径"}), 400
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        return jsonify({"ok": True, "path": rel})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/rules", methods=["DELETE"])
def delete_rule():
    """删除规则文件（仅 config/rules/ 中的可删）。Query: path=xxx"""
    rel = (request.args.get("path") or "").strip()
    if not rel:
        return jsonify({"ok": False, "error": "缺少 path 参数"}), 400
    if ".." in Path(rel).parts:
        return jsonify({"ok": False, "error": "非法路径"}), 400
    target = (RULES_DIR / rel).resolve()
    try:
        target.relative_to(RULES_DIR.resolve())
    except ValueError:
        return jsonify({"ok": False, "error": "非法路径"}), 400
    if not target.exists():
        return jsonify({"ok": False, "error": "文件不存在（可能是 template 预置规则，不可删除）"}), 404
    try:
        target.unlink()
        return jsonify({"ok": True, "path": rel})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/rules/sync", methods=["POST"])
def sync_rules():
    """同步 rules 到所有 IDE 的 rules 目录。

    各 IDE 目标目录：
    - TraeCN: ~/.trae-cn/rules/
    - ZCode: ~/.zcode/rules/
    - OpenCode: ~/.config/opencode/rules/
    - Claude: .claude/rules/
    - Cursor: .cursor/rules/
    - Codex: .codex/rules/
    - OpenClaw: .openclaw/rules/
    - WorkBuddy: .workbuddy/rules/
    """
    from pathlib import Path as _Path
    try:
        # 收集所有规则文件（config 优先 + template 补充）
        all_files: dict[str, Path] = {}  # rel_path -> Path
        for base, _ in _rules_search_dirs():
            for f in sorted(base.rglob("*.md")):
                if f.name.startswith(".") or f.name == "README.md":
                    continue
                rel = str(f.relative_to(base))
                if rel not in all_files:
                    all_files[rel] = f

        if not all_files:
            return jsonify({"ok": False, "error": "没有规则文件可同步"}), 400

        import shutil
        targets = [
            ("TraeCN", _Path.home() / ".trae-cn" / "rules"),
            ("ZCode", _Path.home() / ".zcode" / "rules"),
            ("OpenCode", _Path.home() / ".config" / "opencode" / "rules"),
            ("Claude", PROJECT_ROOT / ".claude" / "rules"),
            ("Cursor", PROJECT_ROOT / ".cursor" / "rules"),
            ("Codex", PROJECT_ROOT / ".codex" / "rules"),
            ("OpenClaw", PROJECT_ROOT / ".openclaw" / "rules"),
            ("WorkBuddy", PROJECT_ROOT / ".workbuddy" / "rules"),
        ]
        results = {}
        for ide_name, rules_dir in targets:
            rules_dir.mkdir(parents=True, exist_ok=True)
            # 清空旧规则（force 模式）
            for old in rules_dir.glob("*.md"):
                old.unlink()
            # 复制所有规则文件，保留子目录结构
            count = 0
            for rel, src in all_files.items():
                dst = rules_dir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src), str(dst))
                count += 1
            results[ide_name] = count
        total_ides = len([v for v in results.values() if v > 0])
        return jsonify({
            "ok": True,
            "count": len(all_files),
            "results": results,
            "message": f"已同步 {len(all_files)} 个规则到 {total_ides} 个 IDE",
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/rules/export", methods=["GET"])
def export_rules():
    """导出所有规则为 zip。"""
    import io, zipfile
    buf = io.BytesIO()
    seen = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for base, _ in _rules_search_dirs():
            for f in base.rglob("*.md"):
                if f.name.startswith(".") or f.name == "README.md":
                    continue
                rel = str(f.relative_to(base))
                if rel in seen:
                    continue
                seen.add(rel)
                zf.write(f, arcname=rel)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="rules-export.zip",
                     mimetype="application/zip")


@app.route("/api/rules/import", methods=["POST"])
def import_rules():
    """导入规则 zip 或单个 .md 文件。multipart/form-data，file 字段。"""
    from pathlib import Path as _Path
    import shutil
    uploaded = request.files.get("file")
    if not uploaded:
        return jsonify({"ok": False, "error": "缺少 file 字段"}), 400
    fname = uploaded.filename or ""
    overwrite = request.form.get("overwrite", "").lower() in ("true", "1", "yes")

    if fname.lower().endswith(".zip"):
        try:
            buf = io.BytesIO(uploaded.read())
            with zipfile.ZipFile(buf, "r") as zf:
                imported = []
                skipped = []
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    name = info.filename
                    if "__MACOSX" in name or Path(name).name.startswith("."):
                        continue
                    if not name.endswith(".md"):
                        continue
                    dst = RULES_DIR / name
                    if dst.exists() and not overwrite:
                        skipped.append(name)
                        continue
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    dst.write_bytes(zf.read(name))
                    imported.append(name)
            return jsonify({"ok": True, "imported": imported, "skipped": skipped,
                            "count": len(imported)})
        except zipfile.BadZipFile:
            return jsonify({"ok": False, "error": "无效的 zip 文件"}), 400
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
    elif fname.endswith(".md"):
        try:
            content = uploaded.read().decode("utf-8")
        except UnicodeDecodeError:
            return jsonify({"ok": False, "error": "文件编码不是 UTF-8"}), 400
        dst = RULES_DIR / fname
        if dst.exists() and not overwrite:
            return jsonify({"ok": False, "error": "exists",
                            "msg": f"{fname} 已存在，是否覆盖？"}), 409
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(content, encoding="utf-8")
        return jsonify({"ok": True, "imported": [fname], "count": 1})
    else:
        return jsonify({"ok": False, "error": "仅支持 .zip 或 .md 文件"}), 400


# ============================================================
# Hooks API（config/hooks/hooks.json 单文件，JSON 格式）
# ============================================================
def _ensure_hooks_file() -> Path:
    """确保 config/hooks/hooks.json 存在，不存在则从模板复制。"""
    if HOOKS_FILE.exists():
        return HOOKS_FILE
    HOOKS_DIR.mkdir(parents=True, exist_ok=True)
    if HOOKS_EXAMPLE.exists():
        import shutil
        shutil.copy2(HOOKS_EXAMPLE, HOOKS_FILE)
    else:
        HOOKS_FILE.write_text(
            json.dumps({"description": "AgentBuddy Hooks 配置", "hooks": {}}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return HOOKS_FILE


@app.route("/api/hooks", methods=["GET"])
def get_hooks():
    """获取 hooks.json 配置。"""
    path = _ensure_hooks_file()
    try:
        data = load_env_config_file(path)
        return jsonify({"ok": True, "data": data, "path": str(path.relative_to(PROJECT_ROOT))})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/hooks", methods=["POST"])
def save_hooks():
    """保存 hooks.json 配置。Body: {data: {...}}"""
    body = request.get_json(force=True)
    data = body.get("data")
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "data 必须是对象"}), 400
    try:
        path = _ensure_hooks_file()
        save_env_config_file(path, data)
        return jsonify({"ok": True, "path": str(path.relative_to(PROJECT_ROOT))})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/hooks/sync", methods=["POST"])
def sync_hooks():
    """同步 hooks.json 到各 IDE 的 hooks 目录。

    各 IDE 目标：
    - TraeCN: ~/.trae-cn/hooks/hooks.json
    - ZCode: ~/.zcode/hooks/hooks.json
    - OpenCode: ~/.config/opencode/hooks/hooks.json
    - Claude: .claude/hooks/hooks.json
    - Cursor: .cursor/hooks/hooks.json
    """
    from pathlib import Path as _Path
    import shutil
    try:
        path = _ensure_hooks_file()
        # 各 IDE 的 hooks 目录
        targets = [
            ("TraeCN", _Path.home() / ".trae-cn" / "hooks"),
            ("ZCode", _Path.home() / ".zcode" / "hooks"),
            ("OpenCode", _Path.home() / ".config" / "opencode" / "hooks"),
            ("Claude", PROJECT_ROOT / ".claude" / "hooks"),
            ("Cursor", PROJECT_ROOT / ".cursor" / "hooks"),
        ]
        results = {}
        for ide_name, hooks_dir in targets:
            hooks_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(path), str(hooks_dir / "hooks.json"))
            results[ide_name] = 1
        total_ides = len(results)
        return jsonify({
            "ok": True,
            "results": results,
            "message": f"已同步 hooks.json 到 {total_ides} 个 IDE",
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/hooks/export", methods=["GET"])
def export_hooks():
    """导出 hooks.json。"""
    path = _ensure_hooks_file()
    return send_file(path, as_attachment=True, download_name="hooks.json",
                     mimetype="application/json")


@app.route("/api/hooks/import", methods=["POST"])
def import_hooks():
    """导入 hooks.json。Body: {content: '...'}"""
    body = request.get_json(force=True)
    content = body.get("content", "")
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return jsonify({"ok": False, "error": f"JSON 解析失败: {e}"}), 400
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "JSON 顶层应为 dict"}), 400
    try:
        path = _ensure_hooks_file()
        save_env_config_file(path, data)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


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
@app.route("/api/llm/env-vars", methods=["GET"])
def list_llm_env_vars():
    """返回系统中可用的环境变量名（仅含 KEY/TOKEN/SECRET 关键字），用于 api_key 引用选择。"""
    import re as _re
    pattern = _re.compile(r"KEY|TOKEN|SECRET", _re.IGNORECASE)
    names = sorted({k for k in os.environ.keys() if pattern.search(k)})
    return jsonify({"ok": True, "names": names, "count": len(names)})


def _resolve_api_key(raw: str) -> str:
    """解析 api_key 字段：支持 env:VAR_NAME 形式从环境变量读取实际值。"""
    if not raw:
        return ""
    s = raw.strip()
    if s.startswith("env:"):
        var_name = s[4:].strip()
        if not var_name:
            return ""
        return os.environ.get(var_name, "")
    return s


@app.route("/api/llm/verify", methods=["POST"])
def verify_llm():
    """验证 LLM api_key 是否可用，并返回可用 model 列表。

    Body: {base_url, api_key, protocol?}
    调 base_url + /models（OpenAI 兼容），成功返回 model 列表。
    api_key 支持 env:VAR_NAME 引用形式。
    """
    body = request.get_json(force=True)
    base_url = (body.get("base_url") or "").rstrip("/")
    api_key_raw = body.get("api_key", "")
    api_key = _resolve_api_key(api_key_raw)
    protocol = (body.get("protocol") or "openai").lower()
    if not base_url:
        return jsonify({"ok": False, "error": "base_url 必填"}), 400
    if not api_key:
        hint = "（api_key 为 env: 引用但环境变量未设置）" if api_key_raw.startswith("env:") else ""
        return jsonify({"ok": False, "error": f"api_key 无效{hint}"}), 400
    try:
        import requests as _req
        # 统一拼接 /models：兼容 base_url 已含 /v1、/api/v3 或其他路径的情况
        url = base_url
        if not url.endswith("/models"):
            url = url + "/models"
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
    - ZCode:    ~/.zcode/commands/*.md
    - TraeCN:   ~/.trae-cn/commands/*.md
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
            ("ZCode", _Path.home() / ".zcode" / "commands"),
            ("TraeCN", _Path.home() / ".trae-cn" / "commands"),
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
    - OpenCode: ~/.config/opencode/agents/<name>.md（frontmatter + body）
    - ZCode: ~/.zcode/agents/<name>.md（frontmatter + body）
    - Trae/TraeCN/TraeSoloCN: ~/.trae-cn/agents/<name>.md（Trae frontmatter 格式）
    """
    import json as _json
    from pathlib import Path as _Path
    try:
        sa_path = _ensure_subagent_file()
        data = load_env_config_file(sa_path)
        subagents = data.get("subagents", []) if isinstance(data, dict) else []
        results = {}

        def _build_description(sa: dict) -> str:
            """desc + role 拼为 description。"""
            description = sa.get("desc", "").strip()
            role = sa.get("role", "").strip()
            if role and description:
                return f"{description}（角色: {role}）"
            elif role:
                return f"角色: {role}"
            return description

        def _write_agent_md(agents_dir: _Path, sa: dict, fmt: str = "zcode") -> bool:
            """将一个 subagent 写为 <name>.md（frontmatter + body），成功返回 True。

            fmt:
              - "zcode": ZCode 格式（name + color + tools 列表）
              - "opencode": OpenCode 格式（description + mode + permission，无 name/tools 列表）
              - "trae": Trae 格式（name + tools 逗号分隔字符串，无 color）
            """
            name = sa.get("name", "").strip()
            if not name:
                return False
            safe_name = "".join(c for c in name if c.isalnum() or c in "-_")
            if not safe_name:
                return False
            description = _build_description(sa)
            prompt = sa.get("prompt", "").strip()

            if fmt == "opencode":
                # OpenCode: 无 name（文件名即名称），无 tools 列表，用 permission
                # 参考 https://opencode.ai/docs/agents
                lines = [
                    "---",
                    f'description: "{description}"',
                    "mode: subagent",
                    "permission:",
                    "  edit: allow",
                    "  bash: allow",
                    "  read: allow",
                    "  glob: allow",
                    "  grep: allow",
                    "  list: allow",
                    "  webfetch: allow",
                    "  websearch: allow",
                    "  todowrite: allow",
                    "---",
                    "",
                    prompt,
                    "",
                ]
            elif fmt == "trae":
                # Trae: 无 color，tools 为逗号分隔字符串
                lines = [
                    "---",
                    f'name: "{safe_name}"',
                    f'description: "{description}"',
                    f'tools: "Read, Grep, Glob, Bash, Edit, Write, WebFetch, WebSearch, TodoWrite"',
                    "---",
                    "",
                    prompt,
                    "",
                ]
            else:
                # ZCode: 有 color，tools 为列表
                category = sa.get("category", "").strip()
                color_map = {"开发": "yellow", "产品": "blue", "通用": "green"}
                color = color_map.get(category, "yellow")
                lines = [
                    "---",
                    f'name: "{safe_name}"',
                    f'description: "{description}"',
                    f'color: {color}',
                    "tools:",
                    "  - Read",
                    "  - Grep",
                    "  - Glob",
                    "  - Bash",
                    "  - Edit",
                    "  - Write",
                    "  - WebFetch",
                    "  - WebSearch",
                    "  - TodoWrite",
                    "---",
                    "",
                    prompt,
                    "",
                ]
            agents_dir.mkdir(parents=True, exist_ok=True)
            (agents_dir / f"{safe_name}.md").write_text("\n".join(lines), encoding="utf-8")
            return True

        # OpenCode: ~/.config/opencode/agents/<name>.md（OpenCode 专用格式）
        oc_agents_dir = _Path.home() / ".config" / "opencode" / "agents"
        oc_count = sum(1 for sa in subagents if _write_agent_md(oc_agents_dir, sa, fmt="opencode"))
        results["OpenCode"] = oc_count

        # ZCode: ~/.zcode/agents/<name>.md
        zcode_agents_dir = _Path.home() / ".zcode" / "agents"
        zcode_count = sum(1 for sa in subagents if _write_agent_md(zcode_agents_dir, sa, fmt="zcode"))
        results["ZCode"] = zcode_count

        # Trae 系列: ~/.trae-cn/agents/<name>.md（Trae frontmatter 格式）
        # Trae / TraeCN / TraeSoloCN 共享 .trae-cn 全局目录
        trae_agents_dir = _Path.home() / ".trae-cn" / "agents"
        trae_count = sum(1 for sa in subagents if _write_agent_md(trae_agents_dir, sa, fmt="trae"))
        results["TraeCN"] = trae_count

        return jsonify({"ok": True, "count": len(subagents), "results": results,
                        "message": f"已同步到 {', '.join(f'{k}({v})' for k,v in results.items())}"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# 自建插件市场（Blueprint：server/marketplace/）
# ============================================================
# 将市场逻辑迁移到独立模块 server/marketplace/，通过依赖注入复用 config_server 的辅助函数
sys.path.insert(0, str(PROJECT_ROOT / "server"))
from marketplace import create_marketplace_bp

marketplace_bp = create_marketplace_bp(
    marketplace_dir=MARKETPLACE_DIR,
    resolve_plugin_path=_resolve_plugin_path,
    load_env_config_file=load_env_config_file,
    collect_plugin_skill_dirs=_collect_plugin_skill_dirs,
    add_plugin_extras_to_zip=_add_plugin_extras_to_zip,
    import_plugin_zip=_import_plugin_zip,
    add_dir_to_zip=_add_dir_to_zip,
)
app.register_blueprint(marketplace_bp, url_prefix="/api/marketplace")


# ============================================================
# 内嵌终端服务（ttyd）
# ============================================================
_ttyd_proc: subprocess.Popen | None = None
TTYD_PORT = 7681


def _find_ttyd() -> str | None:
    """查找 ttyd 可执行文件。

    macOS 打包后子进程 PATH 可能不含 /opt/homebrew/bin、/usr/local/bin，
    shutil.which 会找不到 brew 安装的 ttyd，需手动扩展查找路径。
    """
    found = shutil.which("ttyd")
    if found:
        return found
    extra_dirs = ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"]
    for d in extra_dirs:
        p = os.path.join(d, "ttyd")
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def _port_in_use(host: str, port: int) -> bool:
    """检测端口是否被占用。"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((host, port)) == 0


@app.route("/api/terminal/start", methods=["POST"])
def terminal_start():
    """启动 ttyd 终端服务，返回访问 URL。"""
    global _ttyd_proc
    if _ttyd_proc and _ttyd_proc.poll() is None and _port_in_use("127.0.0.1", TTYD_PORT):
        # 已在运行
        return jsonify({"ok": True, "port": TTYD_PORT,
                        "url": f"http://127.0.0.1:{TTYD_PORT}"})
    ttyd = _find_ttyd()
    if not ttyd:
        hint = "brew install ttyd" if sys.platform == "darwin" else "winget install ttyd"
        return jsonify({"ok": False,
                        "error": f"未安装 ttyd，请执行: {hint}"}), 400
    # 端口预检：被其他进程占用时给出明确错误（而不是 ttyd 静默退出）
    if _port_in_use("127.0.0.1", TTYD_PORT):
        return jsonify({"ok": False,
                        "error": f"端口 {TTYD_PORT} 已被占用，请释放后重试"}), 400
    # 选择 ttyd 启动的 shell：Windows 用 cmd.exe，其他平台用绝对路径 /bin/bash
    # （避免打包后 PATH 不含 /bin 导致 bash 找不到）
    if sys.platform == "win32":
        shell_cmd = ["cmd.exe"]
    else:
        shell_cmd = ["/bin/bash"]
    try:
        # 捕获 stderr 以便 ttyd 启动失败时返回真实错误原因
        _ttyd_proc = subprocess.Popen(
            [ttyd, "--port", str(TTYD_PORT), "--writable",
             "--interface", "127.0.0.1"] + shell_cmd,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        # 等待端口就绪或进程退出
        import time
        while True:
            rc = _ttyd_proc.poll()
            if rc is not None:
                # 进程已退出，读取 stderr 获取错误原因
                err = ""
                if _ttyd_proc.stderr:
                    try:
                        err = _ttyd_proc.stderr.read().decode(errors="replace").strip()
                    except Exception:
                        pass
                msg = f"ttyd 启动失败 (exit={rc})"
                if err:
                    msg += f": {err}"
                return jsonify({"ok": False, "error": msg}), 500
            if _port_in_use("127.0.0.1", TTYD_PORT):
                break
            time.sleep(0.1)
        return jsonify({"ok": True, "port": TTYD_PORT,
                        "url": f"http://127.0.0.1:{TTYD_PORT}"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/terminal/stop", methods=["POST"])
def terminal_stop():
    """关闭 ttyd 终端服务。"""
    global _ttyd_proc
    if _ttyd_proc and _ttyd_proc.poll() is None:
        _ttyd_proc.terminate()
        try:
            _ttyd_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _ttyd_proc.kill()
    _ttyd_proc = None
    return jsonify({"ok": True})


@app.route("/api/terminal/status", methods=["GET"])
def terminal_status():
    """查询 ttyd 运行状态。"""
    running = _ttyd_proc is not None and _ttyd_proc.poll() is None
    return jsonify({"ok": True, "running": running,
                    "port": TTYD_PORT if running else None,
                    "url": f"http://127.0.0.1:{TTYD_PORT}" if running else None})


# ============================================================
# AI 插件生成（server/ai_generator/）
# ============================================================
@app.route("/api/ai/generate", methods=["GET"])
def ai_generate():
    """AI 生成插件配置。SSE 流式输出。

    Query: prompt=<用户需求描述>
    """
    prompt = (request.args.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"ok": False, "error": "缺少 prompt 参数"}), 400
    model = (request.args.get("model") or "").strip()
    level = (request.args.get("level") or "").strip()

    def generate():
        from ai_generator.generator import generate_plugin
        for chunk in generate_plugin(prompt, PROJECT_ROOT, preferred_model=model, level=level):
            # SSE data: 行不能含换行符，多行内容需逐行发送
            for line in chunk.split("\n"):
                yield f"data: {line}\n\n"

    return Response(stream_with_context(generate()),
                    mimetype="text/event-stream")


@app.route("/api/ai/save", methods=["POST"])
def ai_save():
    """保存 AI 生成的插件配置。Body: {content: <yaml字符串>}"""
    body = request.get_json(force=True)
    content = (body.get("content") or "").strip()
    if not content:
        return jsonify({"ok": False, "error": "缺少 content"}), 400
    try:
        data = yaml.safe_load(content)
        if not isinstance(data, dict) or not data.get("name"):
            return jsonify({"ok": False, "error": "无效的 plugin.yaml（缺少 name）"}), 400
        safe_name = "".join(c for c in data["name"] if c.isalnum() or c in ("-", "_"))
        out_path = CONFIG_PLUGINS_DIR / f"{safe_name}.plugin.yaml"
        CONFIG_PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        return jsonify({"ok": True, "path": str(out_path.relative_to(PROJECT_ROOT)),
                        "name": data["name"]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/ai/chat", methods=["POST"])
def ai_chat():
    """AI 多轮对话生成插件。SSE 流式输出。

    Body: {session_id?, message, level?, model?}
    - 首次对话不传 session_id，后端创建新会话
    - 后续对话传 session_id 继续会话
    """
    body = request.get_json(force=True)
    message = (body.get("message") or "").strip()
    if not message:
        return jsonify({"ok": False, "error": "缺少 message"}), 400

    session_id = (body.get("session_id") or "").strip()
    level = (body.get("level") or "").strip()
    model = (body.get("model") or "").strip() or "glm-5-2-260617"

    from ai_generator.generator import (
        create_session, generate_plugin_chat, clear_session, get_session_config
    )

    # 创建或复用会话
    if not session_id or not get_session_config and session_id:
        session_id = create_session(level=level)
    else:
        # 检查会话是否存在
        from ai_generator.generator import get_session
        if not get_session(session_id):
            session_id = create_session(level=level)

    def generate():
        for chunk in generate_plugin_chat(session_id, message, PROJECT_ROOT, preferred_model=model):
            for line in chunk.split("\n"):
                yield f"data: {line}\n\n"

    # 在第一个 data 之前发送 session_id
    def generate_with_session():
        yield f"data: [SESSION] {session_id}\n\n"
        yield from generate()

    return Response(stream_with_context(generate_with_session()),
                    mimetype="text/event-stream")


@app.route("/api/ai/session/<session_id>/config", methods=["GET"])
def ai_session_config(session_id: str):
    """获取会话中最新的生成配置。"""
    from ai_generator.generator import get_session_config
    config = get_session_config(session_id)
    if config:
        return jsonify({"ok": True, "content": config})
    return jsonify({"ok": False, "error": "会话中暂无配置"}), 404


@app.route("/api/ai/session/<session_id>", methods=["DELETE"])
def ai_session_clear(session_id: str):
    """清除会话。"""
    from ai_generator.generator import clear_session
    if clear_session(session_id):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "会话不存在"}), 404


if __name__ == "__main__":
    main()

