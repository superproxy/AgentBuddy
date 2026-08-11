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
import os
import re
import sqlite3
import sys
from pathlib import Path

from lib.logging import COLOR_YELLOW, COLOR_GREEN, COLOR_RED, COLOR_RESET
from lib.skills import copy_skills_safe
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
        # Cherry Studio 模型服务商由 GUI 管理，跳过
        pass

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
