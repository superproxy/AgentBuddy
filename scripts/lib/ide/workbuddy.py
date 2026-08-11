"""WorkBuddy IDE 分发器。

迁移自 scripts/init-ide.py 的 init_workbuddy() 和 generate_workbuddy_models()。
生成 ~/.workbuddy/models.json（从 llm.yaml 展开模型列表）。

WorkBuddy models.json 官方格式（腾讯云文档 product/1749/116119）：
    {"models": [{"id", "name", "vendor", "apiKey", "url", ...}], "availableModels": [...]}
- 顶层必须是 {"models": [...]} 对象，而非裸数组
- url 必须是完整端点，以 /chat/completions 结尾（OpenAI 兼容协议）
- 配置文件位于用户级目录 ~/.workbuddy/（macOS/Linux）
"""
import json
from pathlib import Path

from lib.logging import COLOR_YELLOW, COLOR_GREEN, COLOR_RESET
from lib.mcp import copy_dir_safe, copy_file_safe
from lib.skills import copy_skills_safe, write_skills_index
from lib.llm import load_split_env_config
from .base import IdeTarget


def _completions_url(base_url: str, protocol_name: str) -> str:
    """WorkBuddy/CodeBuddy 官方要求 url 为完整端点（以 /chat/completions 结尾）。

    - OpenAI 兼容协议：base_url 若不以 /chat/completions 结尾则补全
      （如 https://api.example.com/v1 → https://api.example.com/v1/chat/completions）
    - anthropic 协议：保留 base_url 原样（官方 models.json 仅声明 OpenAI 格式，
      anthropic 端点由 WorkBuddy 内部处理）
    """
    if protocol_name in ("openaiv1", "openai", "responses"):
        if base_url.endswith("/chat/completions"):
            return base_url
        return base_url.rstrip("/") + "/chat/completions"
    return base_url


def generate_workbuddy_models(env_config: dict | None, target_file: Path, force: bool,
                              ide_protocols: list[str] | None = None) -> None:
    """从 llm.yaml 的 llm 配置生成 ~/.workbuddy/models.json (WorkBuddy 模型列表)。

    遍历 llm.<provider>.<protocol>.models，展开为 WorkBuddy 官方格式 {"models": [...]}。
    - 跳过 _ 前缀键（元数据）和 proxy 段
    - 跳过 _enabled === false 的 provider（未启用）
    - 跳过 ~ 前缀 model id（禁用标记）
    - api_key 为空的协议自动剪枝
    - 同一 model_id 去重
    - ide_protocols 指定时只同步这些协议的模型
    - OpenAI 兼容协议 url 补全 /chat/completions 完整端点
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
    # 协议优先级：openaiv1/openai > responses > anthropic（优先使用 OpenAI 兼容协议）
    _PROTO_PRIORITY = {"openaiv1": 0, "openai": 0, "responses": 1, "anthropic": 2}
    models_list = []
    seen = set()
    providers_order = sorted(
        (p for p in llm_section if not p.startswith("_") and p != "proxy"),
        key=lambda p: (p != active_provider),  # active provider 排最前
    )
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
                # 按 model_id 去重（优先 active provider / 优先 openai 协议），避免重复
                if model_id in seen:
                    continue
                seen.add(model_id)
                if isinstance(model_meta, dict):
                    model_name = str(model_meta.get("name", "")).strip() or model_id
                else:
                    model_name = str(model_meta).strip() or model_id
                model_entry = {
                    "id": model_id,
                    "name": model_name,
                    "vendor": provider_name,
                    "apiKey": api_key,
                    "url": _completions_url(base_url, protocol_name),
                    "supportsToolCall": True,
                    "supportsImages": False,
                    "supportsReasoning": False,
                }
                if isinstance(model_meta, dict):
                    for token_key in ("maxInputTokens", "maxOutputTokens"):
                        token_val = model_meta.get(token_key)
                        if token_val is not None:
                            model_entry[token_key] = token_val
                models_list.append(model_entry)

    target_file.parent.mkdir(parents=True, exist_ok=True)
    with open(target_file, "w", encoding="utf-8") as f:
        json.dump({"models": models_list}, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"{COLOR_GREEN}[OK] {target_file} ({len(models_list)} models){COLOR_RESET}")


class WorkBuddyTarget(IdeTarget):
    name = "WorkBuddy"

    def init_rules(self, source_rules: Path):
        wb_rules_dir = self.root / ".workbuddy" / "rules"
        wb_rules_dir.parent.mkdir(parents=True, exist_ok=True)
        if source_rules.exists():
            copy_dir_safe(source_rules, wb_rules_dir, ".workbuddy/rules/", self.force)
        else:
            print(f"{COLOR_YELLOW}[!] Source rules/ not found, skipping{COLOR_RESET}")

    def init_mcp(self, source_mcp_file: Path):
        wb_dir = self.root / ".workbuddy"
        wb_dir.mkdir(parents=True, exist_ok=True)
        copy_file_safe(source_mcp_file, wb_dir / "mcp.json",
                       ".workbuddy/mcp.json", self.force)

    def init_llm(self, source_rules_dirs):
        # 生成 WorkBuddy 特有的 LLM 模型列表（用户级 ~/.workbuddy/models.json，与 CodeBuddy 一致）
        first = source_rules_dirs[0] if isinstance(source_rules_dirs, list) else source_rules_dirs
        source_dir = first.parent.parent
        env_config = load_split_env_config(source_dir, silent=True)
        generate_workbuddy_models(env_config, Path.home() / ".workbuddy" / "models.json",
                                  self.force, ide_protocols=self.ide_protocols)

    def init_skills(self, source_skills_dir: Path):
        # 同步到全局目录（~/.workbuddy/skills/）
        wb_skills_dir = Path.home() / ".workbuddy" / "skills"
        copy_skills_safe(source_skills_dir, wb_skills_dir, "~/.workbuddy/skills/",
                         self.force, self.include_skills, link=self.link_skills)
        write_skills_index(source_skills_dir, wb_skills_dir / "README.md",
                           "WorkBuddy", self.force, self.include_skills)
