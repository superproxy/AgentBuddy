"""WorkBuddy IDE 分发器。

迁移自 scripts/init-ide.py 的 init_workbuddy() 和 generate_workbuddy_models()。
生成 .workbuddy/models.json（从 llm.yaml 展开模型列表）。
"""
import json
from pathlib import Path

from lib.logging import COLOR_YELLOW, COLOR_GREEN, COLOR_RESET
from lib.mcp import copy_dir_safe, copy_file_safe
from lib.skills import copy_skills_safe, write_skills_index
from lib.llm import load_split_env_config
from .base import IdeTarget


def generate_workbuddy_models(env_config: dict | None, target_file: Path, force: bool) -> None:
    """从 llm.yaml 的 llm 配置生成 .workbuddy/models.json (WorkBuddy 模型列表)。

    遍历 llm.<provider>.<protocol>.models，展开为 WorkBuddy 所需的模型数组。
    - 跳过 _ 前缀键（元数据）和 proxy 段
    - 跳过 ~ 前缀 model id（禁用标记）
    - api_key 为空的协议自动剪枝
    - 同 (model_id, url) 去重
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

    models_list = []
    seen = set()
    for provider_name, provider_value in llm_section.items():
        if provider_name.startswith("_") or provider_name == "proxy":
            continue
        if not isinstance(provider_value, dict):
            continue
        for protocol_name, protocol_value in provider_value.items():
            if protocol_name.startswith("_") or not isinstance(protocol_value, dict):
                continue
            base_url = str(protocol_value.get("base_url", "")).strip()
            api_key = str(protocol_value.get("api_key", "")).strip()
            if not api_key:
                continue
            models_dict = protocol_value.get("models", {})
            if not isinstance(models_dict, dict):
                continue
            for model_id, model_meta in models_dict.items():
                if model_id.startswith("~"):
                    continue
                if isinstance(model_meta, dict):
                    model_name = str(model_meta.get("name", "")).strip() or model_id
                else:
                    model_name = str(model_meta).strip() or model_id
                dedup_key = (model_id, base_url)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                models_list.append({
                    "id": model_id,
                    "name": model_name,
                    "vendor": provider_name,
                    "url": base_url,
                    "apiKey": api_key,
                    "supportsToolCall": True,
                    "supportsImages": False,
                    "supportsReasoning": False,
                    "useCustomProtocol": False,
                })

    target_file.parent.mkdir(parents=True, exist_ok=True)
    with open(target_file, "w", encoding="utf-8") as f:
        json.dump(models_list, f, indent=2, ensure_ascii=False)
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

    def init_llm(self, source_rules_dir: Path):
        # 生成 WorkBuddy 特有的 LLM 模型列表
        source_dir = source_rules_dir.parent.parent
        env_config = load_split_env_config(source_dir, silent=True)
        generate_workbuddy_models(env_config, self.root / ".workbuddy" / "models.json",
                                  self.force)

    def init_skills(self, source_skills_dir: Path):
        # 同步到全局目录（~/.workbuddy/skills/）
        wb_skills_dir = Path.home() / ".workbuddy" / "skills"
        copy_skills_safe(source_skills_dir, wb_skills_dir, "~/.workbuddy/skills/",
                         self.force, self.include_skills, link=self.link_skills)
        write_skills_index(source_skills_dir, wb_skills_dir / "README.md",
                           "WorkBuddy", self.force, self.include_skills)
