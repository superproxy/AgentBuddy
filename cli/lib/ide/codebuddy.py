"""CodeBuddy IDE 分发器。

腾讯云 CodeBuddy（AI 代码编辑器）分发器：
- init_mcp：复制 mcp.json 到 ~/.codebuddy/mcp.json（标准 mcpServers 格式）
- init_llm：生成 ~/.codebuddy/models.json（官方 TokenHub 格式 {"models":[...]}）

CodeBuddy models.json 官方格式（腾讯云 TokenHub 文档 product/1823/130068）：
    {"models": [{"id", "name", "vendor", "apiKey", "url"}, ...]}
配置文件位于用户级目录 ~/.codebuddy/（macOS/Linux）或 C:\\Users\\<用户>\\.codebuddy\\（Windows）。
"""
import json
from pathlib import Path

from lib.logging import COLOR_YELLOW, COLOR_GREEN, COLOR_RESET
from lib.mcp import copy_file_safe
from lib.skills import copy_skills_safe, write_skills_index
from lib.llm import load_split_env_config
from .base import IdeTarget


def _completions_url(base_url: str, protocol_name: str) -> str:
    """CodeBuddy/WorkBuddy 官方要求 url 为完整端点（以 /chat/completions 结尾）。

    - OpenAI 兼容协议：base_url 若不以 /chat/completions 结尾则补全
    - anthropic 协议：保留 base_url 原样
    """
    if protocol_name in ("openaiv1", "openai", "responses"):
        if base_url.endswith("/chat/completions"):
            return base_url
        return base_url.rstrip("/") + "/chat/completions"
    return base_url


def generate_codebuddy_models(env_config: dict | None, target_file: Path, force: bool,
                              ide_protocols: list[str] | None = None) -> None:
    """从 llm.yaml 的 llm 配置生成 ~/.codebuddy/models.json（CodeBuddy 官方格式）。

    遍历 llm.<provider>.<protocol>.models，展开为 CodeBuddy 所需的模型数组。
    - 跳过 _ 前缀键（元数据）和 proxy 段
    - 跳过 ~ 前缀 model id（禁用标记）
    - api_key 为空的协议自动剪枝
    - 同一 model_id 去重（优先 active provider 的配置，避免 openai/anthropic 协议重复）
    - ide_protocols 指定时只同步这些协议的模型
    """
    if not env_config:
        print(f"{COLOR_YELLOW}[!] llm.yaml not found, skip models.json{COLOR_RESET}")
        return

    if target_file.exists() and not force:
        print(f"{COLOR_YELLOW}[!] {target_file.name} exists, use --force to overwrite{COLOR_RESET}")
        return

    llm_section = env_config.get("llm", {})
    if not isinstance(llm_section, dict):
        print(f"{COLOR_YELLOW}[!] llm section invalid, skip models.json{COLOR_RESET}")
        return

    active_provider = llm_section.get("_active_provider", "")

    # 第一遍：先收集 active provider 的模型，保证去重时优先
    models_list = []
    seen = set()
    providers_order = sorted(
        (p for p in llm_section if not p.startswith("_") and p != "proxy"),
        key=lambda p: (p != active_provider),  # active provider 排最前
    )
    # 协议优先级：openaiv1/openai > responses > anthropic（优先使用 OpenAI 兼容协议）
    _PROTO_PRIORITY = {"openaiv1": 0, "openai": 0, "responses": 1, "anthropic": 2}
    for provider_name in providers_order:
        provider_value = llm_section[provider_name]
        if not isinstance(provider_value, dict):
            continue
        # 跳过被禁用的 provider（_enabled === false），与 flatten_env_config 保持一致
        if provider_value.get("_enabled") is False:
            continue
        protocol_items = sorted(
            (p for p in provider_value.items()
             if not p[0].startswith("_") and isinstance(p[1], dict)),
            key=lambda item: _PROTO_PRIORITY.get(item[0], 9),
        )
        for protocol_name, protocol_value in protocol_items:
            # 兼容旧协议名 openai → openaiv1（llm.yaml 常写 openai，ide_protocols 用 openaiv1）
            proto_check = "openaiv1" if protocol_name == "openai" else protocol_name
            # IDE 协议过滤
            if ide_protocols is not None and proto_check not in ide_protocols:
                continue
            base_url = str(protocol_value.get("base_url", "")).strip()
            api_key = str(protocol_value.get("api_key", "")).strip()
            if not base_url or not api_key:
                continue
            models_dict = protocol_value.get("models", {})
            if not isinstance(models_dict, dict):
                continue
            for model_id, model_meta in models_dict.items():
                if model_id.startswith("~"):
                    continue
                if model_id in seen:
                    continue
                seen.add(model_id)
                if isinstance(model_meta, dict):
                    model_name = str(model_meta.get("name", "")).strip() or model_id
                else:
                    model_name = str(model_meta).strip() or model_id
                models_list.append({
                    "id": model_id,
                    "name": model_name,
                    "vendor": provider_name,
                    "apiKey": api_key,
                    "url": _completions_url(base_url, protocol_name),
                })

    target_file.parent.mkdir(parents=True, exist_ok=True)
    with open(target_file, "w", encoding="utf-8") as f:
        json.dump({"models": models_list}, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"{COLOR_GREEN}[OK] {target_file} ({len(models_list)} models){COLOR_RESET}")


class CodeBuddyTarget(IdeTarget):
    name = "CodeBuddy"

    def init_rules(self, source_rules: Path):
        # CodeBuddy rules 同步到用户级 ~/.codebuddy/rules/
        cb_rules_dir = Path.home() / ".codebuddy" / "rules"
        cb_rules_dir.parent.mkdir(parents=True, exist_ok=True)
        if source_rules.exists():
            from lib.mcp import copy_dir_safe
            copy_dir_safe(source_rules, cb_rules_dir, "~/.codebuddy/rules/", self.force)
        else:
            print(f"{COLOR_YELLOW}[!] Source rules/ not found, skipping{COLOR_RESET}")

    def init_mcp(self, source_mcp_file: Path):
        cb_dir = Path.home() / ".codebuddy"
        cb_dir.mkdir(parents=True, exist_ok=True)
        copy_file_safe(source_mcp_file, cb_dir / "mcp.json",
                       "~/.codebuddy/mcp.json", self.force)

    def init_llm(self, source_rules_dirs):
        # 生成 CodeBuddy 特有的 LLM 模型列表（~/.codebuddy/models.json，官方 TokenHub 格式）
        first = source_rules_dirs[0] if isinstance(source_rules_dirs, list) else source_rules_dirs
        source_dir = first.parent.parent
        env_config = load_split_env_config(source_dir, silent=True)
        generate_codebuddy_models(env_config, Path.home() / ".codebuddy" / "models.json",
                                  self.force, ide_protocols=self.ide_protocols)

    def init_skills(self, source_skills_dir: Path):
        # 同步到全局目录（~/.codebuddy/skills/）
        cb_skills_dir = Path.home() / ".codebuddy" / "skills"
        copy_skills_safe(source_skills_dir, cb_skills_dir, "~/.codebuddy/skills/",
                         self.force, self.include_skills, link=self.link_skills)
        write_skills_index(source_skills_dir, cb_skills_dir / "README.md",
                           "CodeBuddy", self.force, self.include_skills)
