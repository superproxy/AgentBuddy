"""OpenWorker 分发器。

OpenWorker（吴恩达 Andrew Ng 开源桌面 AI 智能体，仅桌面 App）：
- App：OpenWork.app（bundle id com.differentai.openwork）
- 官方配置目录（state dir，见 andrewyng/openworker）：
    $COWORKER_STATE_DIR 或 ~/.config/coworker/（macOS/Linux）、%APPDATA%\\coworker\\（Windows）
- LLM 配置（官方格式）：
    secrets.json  SecretStore profile 结构，键形如 "provider:openai"，
                  字段 api_key / base_url（OpenAI 兼容网关）/ model
    config.toml   model = "<默认模型>" 指定会话默认模型
- MCP/Skills 同步到 state dir，供 OpenWorker 读取（SKILL.md 目录格式与 AgentBuddy 兼容）。
"""
import json
import os
import re
import sys
from pathlib import Path

from lib.logging import COLOR_YELLOW, COLOR_GREEN, COLOR_RED, COLOR_RESET
from lib.mcp import copy_file_safe
from lib.skills import copy_skills_safe, write_skills_index
from .base import IdeTarget


def openworker_state_dir() -> Path:
    """OpenWorker 官方状态目录（state dir）。

    优先级：$COWORKER_STATE_DIR > %APPDATA%\\coworker（Windows）> ~/.config/coworker（macOS/Linux）。
    """
    env = os.environ.get("COWORKER_STATE_DIR")
    if env:
        return Path(env)
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", str(Path.home()))) / "coworker"
    return Path.home() / ".config" / "coworker"


def _first_model(models) -> str:
    """取 models dict 的第一个可用 model id（跳过 ~ 前缀禁用标记）。"""
    if not isinstance(models, dict):
        return ""
    for mid in models:
        if str(mid).startswith("~"):
            continue
        return str(mid)
    return ""


def _set_toml_model(toml_file: Path, model: str) -> None:
    """在 config.toml 中设置/更新 model 字段（保留其他键）。"""
    text = toml_file.read_text(encoding="utf-8") if toml_file.exists() else ""
    lines = text.splitlines()
    out = []
    replaced = False
    for line in lines:
        if re.match(r"^\s*model\s*=", line):
            out.append(f'model = "{model}"')
            replaced = True
        else:
            out.append(line)
    if not replaced:
        if out and out[-1].strip():
            out.append("")
        out.append(f'model = "{model}"')
    toml_file.write_text("\n".join(out) + "\n", encoding="utf-8")


class OpenWorkerTarget(IdeTarget):
    name = "OpenWorker"

    def init_rules(self, source_rules: Path):
        # OpenWorker 无 rules 概念，跳过
        pass

    def init_mcp(self, source_mcp_file: Path):
        ow_dir = openworker_state_dir()
        ow_dir.mkdir(parents=True, exist_ok=True)
        copy_file_safe(source_mcp_file, ow_dir / "mcp.json",
                       "~/.config/coworker/mcp.json", self.force)

    def init_llm(self, source_rules_dirs):
        """同步 LLM 配置到 OpenWorker（官方 secrets.json + config.toml）。

        OpenWorker（andrewyng/openworker）官方配置方式：
        - secrets.json：SecretStore profile 结构，键形如 "provider:openai"，
          字段 api_key / base_url / model；base_url 由 profile 提供，
          支持自定义 OpenAI 兼容端点/网关（无需 GUI 重复配置）。
        - config.toml：model = "<默认模型>" 指定会话默认模型。
        """
        from lib.llm import load_split_env_config
        ow_dir = openworker_state_dir()
        ow_dir.mkdir(parents=True, exist_ok=True)

        env_config = load_split_env_config(self.root, silent=True)
        llm = env_config.get("llm", {}) if isinstance(env_config, dict) else {}
        if not isinstance(llm, dict):
            return

        active_provider = str(llm.get("_active_provider", "") or "")
        active_model = str(llm.get("_active_model", "") or "")

        # 协议优先级：优先 OpenAI 兼容协议（支持 base_url 网关）
        _PROTO_PRIORITY = {"openaiv1": 0, "openai": 0, "responses": 1, "anthropic": 2}

        profiles = {}
        providers_order = sorted(
            (p for p in llm if not p.startswith("_") and p != "proxy"),
            key=lambda p: (p != active_provider),  # active provider 排最前
        )
        for provider_name in providers_order:
            pv = llm[provider_name]
            if not isinstance(pv, dict):
                continue
            # 跳过被禁用的 provider（_enabled === false），与 flatten_env_config 保持一致
            if pv.get("_enabled") is False:
                continue
            protocols = sorted(
                (k for k, v in pv.items()
                 if not k.startswith("_") and isinstance(v, dict)),
                key=lambda k: _PROTO_PRIORITY.get(k, 9),
            )
            for proto_name in protocols:
                cfg = pv[proto_name]
                if not isinstance(cfg, dict):
                    continue
                api_key = str(cfg.get("api_key", "") or "").strip()
                if not api_key:
                    continue
                base_url = str(cfg.get("base_url", "") or "").strip()
                model = active_model or _first_model(cfg.get("models"))
                # OpenAI 兼容协议统一映射到 provider:openai；anthropic 走 provider:anthropic
                if proto_name in ("openaiv1", "openai", "responses"):
                    slot = "openai"
                elif proto_name == "anthropic":
                    slot = "anthropic"
                else:
                    slot = proto_name
                profile_key = f"provider:{slot}"
                if profile_key in profiles:
                    continue
                profile = {"type": proto_name, "api_key": api_key}
                # anthropic provider 官方不支持 base_url（仅走官方 API），不写网关地址
                if base_url and proto_name != "anthropic":
                    profile["base_url"] = base_url
                if model:
                    profile["model"] = model
                profiles[profile_key] = profile

        if not profiles:
            print(f"{COLOR_YELLOW}[!] OpenWorker: llm.yaml 无带 api_key 的协议，跳过 secrets 同步{COLOR_RESET}")
            return

        # secrets.json：合并已有（保留 GUI 手动配置的其他 profile）
        secrets_file = ow_dir / "secrets.json"
        existing = {}
        if secrets_file.exists():
            try:
                existing = json.loads(secrets_file.read_text(encoding="utf-8"))
            except Exception:
                existing = {}
        existing.update(profiles)
        secrets_file.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
                                encoding="utf-8")
        if sys.platform != "win32":
            try:
                os.chmod(secrets_file, 0o600)
            except OSError:
                pass

        # config.toml：model = active_model
        if active_model:
            _set_toml_model(ow_dir / "config.toml", active_model)

        shown = ", ".join(f"{k} ({v.get('base_url') or 'official'})"
                          for k, v in profiles.items())
        print(f"{COLOR_GREEN}[OK] OpenWorker llm synced to ~/.config/coworker/secrets.json "
              f"({shown}){COLOR_RESET}")

    def init_skills(self, source_skills_dir: Path):
        ow_skills_dir = openworker_state_dir() / "skills"
        copy_skills_safe(source_skills_dir, ow_skills_dir, "~/.config/coworker/skills/",
                         self.force, self.include_skills, link=self.link_skills)
        write_skills_index(source_skills_dir, ow_skills_dir / "README.md",
                           "OpenWorker", self.force, self.include_skills)
        print(f"{COLOR_GREEN}[OK] OpenWorker skills synced to ~/.config/coworker/skills/{COLOR_RESET}")
