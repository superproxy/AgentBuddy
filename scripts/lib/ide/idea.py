"""IntelliJ IDEA (JetBrains) 分发器。

迁移自 scripts/init-ide.py 的 init_idea() 和 _deploy_acp_to_jetbrains()。
部署 acp.json 到 JetBrains IDE 配置目录（跨平台）。
"""
import os
import re
import shutil
import sys
from pathlib import Path

from lib.logging import COLOR_YELLOW, COLOR_GREEN, COLOR_RED, COLOR_DARKGRAY, COLOR_RESET
from lib.skills import copy_skills_safe, write_skills_index
from .base import IdeTarget


def _deploy_acp_to_jetbrains(acp_src: Path, force: bool) -> int:
    """部署 acp.json 到 JetBrains IDE 配置目录。

    Windows: 遍历 %APPDATA%/JetBrains/<IDE>/ 目录
    macOS/Linux: 单一全局 ~/.jetbrains/acp.json
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", "")) / "JetBrains"
        if not base.exists():
            print(f"{COLOR_YELLOW}[!] JetBrains config dir not found: {base}{COLOR_RESET}")
            return 0

        ide_pattern = re.compile(
            r"^(IntelliJIdea|WebStorm|PyCharm|PhpStorm|GoLand|Rider|CLion|"
            r"DataGrip|RubyMine|AppCode|DataSpell|Fleet|Aqua|RustRover|Writerside)",
            re.IGNORECASE,
        )

        copied = 0
        for ide_dir in sorted(base.iterdir()):
            if not ide_dir.is_dir():
                continue
            if not ide_pattern.match(ide_dir.name):
                continue

            target = ide_dir / "acp.json"
            if target.exists() and not force:
                print(f"{COLOR_DARKGRAY}[~] {ide_dir.name}: acp.json exists, skipping{COLOR_RESET}")
                continue

            try:
                shutil.copy2(str(acp_src), str(target))
                print(f"{COLOR_GREEN}[OK] {ide_dir.name} -> {target}{COLOR_RESET}")
                copied += 1
            except Exception as e:
                print(f"{COLOR_RED}[!] {ide_dir.name}: {e}{COLOR_RESET}")

        return copied
    else:
        # macOS / Linux: single global ~/.jetbrains/acp.json
        target = Path.home() / ".jetbrains" / "acp.json"
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists() and not force:
            print(f"{COLOR_DARKGRAY}[~] ~/.jetbrains/acp.json exists, skipping{COLOR_RESET}")
            return 0

        try:
            shutil.copy2(str(acp_src), str(target))
            print(f"{COLOR_GREEN}[OK] -> {target}{COLOR_RESET}")
            return 1
        except Exception as e:
            print(f"{COLOR_RED}[!] ~/.jetbrains/acp.json: {e}{COLOR_RESET}")
            return 0


class IdeATarget(IdeTarget):
    name = "IDEA"

    def init_rules(self, source_rules: Path):
        # IDEA 无 rules 目录配置
        pass

    def init_mcp(self, source_mcp_file: Path):
        source_dir = self.root
        acp_src = source_dir / "ide" / "idea" / "acp.json"

        if not acp_src.exists():
            print(f"{COLOR_YELLOW}[!] acp.json source not found: {acp_src}{COLOR_RESET}")
            return

        copied = _deploy_acp_to_jetbrains(acp_src, self.force)

        if copied == 0:
            print(f"{COLOR_YELLOW}[!] No JetBrains IDE config dirs found or all skipped{COLOR_RESET}")
        else:
            print(f"{COLOR_GREEN}[OK] Deployed acp.json to {copied} JetBrains IDE(s){COLOR_RESET}")

    def init_skills(self, source_skills_dir: Path):
        idea_skills_dir = self.root / ".idea" / "skills"
        copy_skills_safe(source_skills_dir, idea_skills_dir, ".idea/skills/",
                         self.force, self.include_skills)
        write_skills_index(source_skills_dir, idea_skills_dir / "README.md",
                           "IDEA", self.force, self.include_skills)
