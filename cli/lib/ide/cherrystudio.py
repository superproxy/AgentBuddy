"""Cherry Studio 分发器。

Cherry Studio 是一个 AI 桌面客户端（支持多模型、MCP、Skills）。
数据目录（Data/）下：
  - Skills/  : 每个 skill 一个目录（<name>/SKILL.md），SKILL.md 格式与 AgentBuddy 完全兼容
  - agents.db: SQLite，skills 表记录 skill 元数据（id/name/description/folder_name/content_hash/is_enabled）

本分发器同步 Skills：
  1. 把 AgentBuddy skills（SKILL.md）复制到 CherryStudio Data/Skills/
  2. 解析每个 SKILL.md 的 frontmatter（name/description），计算 content_hash，
     写入 agents.db 的 skills 表（folder_name 唯一，UPSERT）
"""
import hashlib
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

from ..logging import COLOR_YELLOW, COLOR_GREEN, COLOR_RED, COLOR_RESET
from ..skills import copy_skills_safe
from .base import IdeTarget


def cherry_data_dir() -> Path:
    """定位 Cherry Studio 数据目录（Data/）。"""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "CherryStudio"
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / "CherryStudio"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "CherryStudio"
    return base / "Data"


def _parse_skill_frontmatter(skill_md: Path) -> dict:
    """解析 SKILL.md 的 YAML frontmatter（name/description）。"""
    meta = {"name": "", "description": ""}
    try:
        text = skill_md.read_text(encoding="utf-8")
    except Exception:
        return meta
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    if not m:
        return meta
    body = m.group(1)
    for key in ("name", "description"):
        km = re.search(rf"^{key}:\s*(.+)$", body, re.M)
        if km:
            meta[key] = km.group(1).strip().strip('"').strip("'")
    return meta


def _skill_content_hash(skill_md: Path) -> str:
    """计算 SKILL.md 内容的 SHA-256（触发内容变更时更新）。"""
    try:
        data = skill_md.read_bytes()
    except Exception:
        data = b""
    return hashlib.sha256(data).hexdigest()


def _sync_skills_db(skills_root: Path, db_path: Path, source: str = "local") -> int:
    """把 Skills/ 目录下的 skill 元数据写入 agents.db 的 skills 表（UPSERT）。返回写入数。"""
    if not skills_root.is_dir():
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        now = int(__import__("time").time() * 1000)
        count = 0
        for skill_dir in sorted(skills_root.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.is_file():
                continue
            meta = _parse_skill_frontmatter(skill_md)
            name = meta["name"] or skill_dir.name
            desc = meta["description"]
            chash = _skill_content_hash(skill_md)
            # 显式 UPSERT（不依赖数据库唯一索引）：folder_name 存在则更新，否则插入
            row = conn.execute(
                "SELECT id FROM skills WHERE folder_name = ?", (skill_dir.name,)
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE skills SET name=?, description=?, source=?,
                        content_hash=?, is_enabled=1, updated_at=?
                    WHERE folder_name=?
                    """,
                    (name, desc, source, chash, now, skill_dir.name),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO skills
                        (id, name, description, folder_name, source, content_hash,
                         is_enabled, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (str(__import__("uuid").uuid4()), name, desc, skill_dir.name,
                     source, chash, now, now),
                )
            count += 1
        conn.commit()
        return count
    finally:
        conn.close()


class CherryStudioTarget(IdeTarget):
    name = "CherryStudio"

    def init_rules(self, source_rules):
        # Cherry Studio 无 rules 概念，跳过
        pass

    def init_mcp(self, source_mcp_file: Path):
        # Cherry Studio 的 MCP 配置存于数据库/LocalStorage，无法安全文件同步，跳过
        pass

    def init_llm(self, source_rules_dirs):
        """同步 LLM 配置到 Cherry Studio。

        Cherry Studio 的模型服务商由 GUI 管理（provider 存于 IndexedDB，无法文件级注入），
        因此这里从 config/llm/llm.yaml 读取 provider/protocol/model，
        生成一个 Cherry Studio 可导入的 provider JSON（config/ide/cherrystudio/providers.json），
        并给出导入指引。
        """
        from ..config_io import load_env_config_file
        first = source_rules_dirs[0] if isinstance(source_rules_dirs, list) else source_rules_dirs
        project_root = first.parent.parent
        llm_yaml = project_root / "config" / "llm" / "llm.yaml"
        if not llm_yaml.exists():
            return
        try:
            llm_data = load_env_config_file(llm_yaml)
        except Exception:
            return
        llm = llm_data.get("llm", {}) if isinstance(llm_data, dict) else {}

        providers = []
        for provider_name, provider_value in llm.items():
            if provider_name.startswith("_") or provider_name == "proxy":
                continue
            if not isinstance(provider_value, dict):
                continue
            # 跳过被禁用的 provider（_enabled === false），与 flatten_env_config 保持一致
            if provider_value.get("_enabled") is False:
                continue
            for protocol, cfg in provider_value.items():
                if not isinstance(cfg, dict) or protocol.startswith("_"):
                    continue
                # 兼容旧协议名 openai → openaiv1（与 llm.flatten_env_config 一致）
                proto_key = "openaiv1" if protocol == "openai" else protocol
                if self.ide_protocols is not None and proto_key not in self.ide_protocols:
                    continue
                api_key = cfg.get("api_key", "") or ""
                if not api_key:
                    continue
                pid = f"custom-{provider_name}-{protocol}"
                # Cherry Studio Provider 结构：type 决定兼容协议
                ptype = "anthropic" if protocol == "anthropic" else "openai"
                models = []
                for model_id, model_cfg in (cfg.get("models") or {}).items():
                    m_name = (model_cfg.get("name") if isinstance(model_cfg, dict) else None) or model_id
                    models.append({
                        "id": model_id,
                        "name": m_name,
                        "type": "text",
                    })
                providers.append({
                    "id": pid,
                    "name": f"{provider_name} ({protocol})",
                    "type": ptype,
                    "apiKey": api_key,
                    "baseUrl": cfg.get("base_url", ""),
                    "models": models,
                    "enabled": provider_value.get("_enabled", False) or provider_name == "openrouter",
                })
        if not providers:
            return

        out_path = project_root / "config" / "ide" / "cherrystudio" / "providers.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(providers, f, indent=2, ensure_ascii=False)
            f.write("\n")
        rel = out_path.relative_to(project_root)
        print(f"{COLOR_GREEN}[OK] Cherry Studio providers.json 已生成: {rel} ({len(providers)} providers){COLOR_RESET}")
        print(f"{COLOR_YELLOW}   Cherry Studio 模型服务商由 GUI 管理，请手动导入:")
        print(f"   设置 → 模型服务商 → 添加自定义服务商 → 导入 providers.json{COLOR_RESET}")

    def init_skills(self, source_skills_dir: Path):
        data_dir = cherry_data_dir()
        skills_root = data_dir / "Skills"
        db_path = data_dir / "agents.db"
        # 1. 复制 SKILL.md 到 Data/Skills/
        copy_skills_safe(source_skills_dir, skills_root,
                         "~CherryStudio/Data/Skills/", self.force,
                         include_skills=self.include_skills, link=False)
        # 2. 写 agents.db skills 表
        if db_path.exists():
            try:
                n = _sync_skills_db(skills_root, db_path)
                print(f"{COLOR_GREEN}[OK] Cherry Studio skills db: {n} records{COLOR_RESET}")
            except Exception as e:
                print(f"{COLOR_RED}[!] Cherry Studio skills db 同步失败: {e}{COLOR_RESET}")
        else:
            print(f"{COLOR_YELLOW}[!] Cherry Studio agents.db 不存在: {db_path}{COLOR_RESET}")
