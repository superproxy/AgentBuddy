""".agents 公共 IDE 规范目录分发器。

定位：把全部配置（rules/mcp/skills/subagents/AGENTS.md）同步到 .agents/ 目录，
作为公共 IDE 规范源，默认不在 UI 显示（hidden=True）。
各 IDE 可共享读取此目录，用软链接避免重复占用磁盘。

.agents/ 同时也是 skill 安装落地处（.agents/skills/），sync 时 skills 子目录
源与目标相同，init_skills 会跳过自我复制（由 copy_skills_safe 内 seen 机制保证）。
"""
import shutil
from pathlib import Path

from lib.logging import COLOR_GREEN, COLOR_RED, COLOR_RESET
from lib.mcp import copy_file_safe, copy_dir_safe
from lib.skills import copy_skills_safe, write_skills_index
from .base import IdeTarget


class AgentsTarget(IdeTarget):
    name = "Agents"
    # .agents/ 目录作为公共 IDE 规范，默认不显示
    # hidden 标记在 install.py 的 IDE_INFO 中已设为 True

    @property
    def agent_dir(self) -> Path:
        """公共 .agents/ 目录。"""
        return self.root / ".agents"

    def init_rules(self, source_rules):
        """同步 rules 到 .agent/rules/（支持多源合并，前者优先）。

        source_rules 可为 Path 或 list[Path]（如 [config/rules, template/rules]），
        多源时按顺序合并，同名条目前者优先，后者跳过。
        """
        srcs = source_rules if isinstance(source_rules, list) else [source_rules]
        srcs = [Path(s) for s in srcs if s and Path(s).exists()]
        if not srcs:
            return
        dst = self.agent_dir / "rules"
        dst.mkdir(parents=True, exist_ok=True)
        seen = set()
        copied = 0
        for src_dir in srcs:
            for item in sorted(src_dir.iterdir()):
                if item.name in seen:
                    continue
                target = dst / item.name
                if target.exists() or target.is_symlink():
                    if not self.force:
                        seen.add(item.name)
                        continue
                    try:
                        if target.is_dir() and not target.is_symlink():
                            shutil.rmtree(str(target), ignore_errors=True)
                        else:
                            target.unlink(missing_ok=True)
                    except Exception:
                        seen.add(item.name)
                        continue
                try:
                    if item.is_dir():
                        shutil.copytree(str(item), str(target),
                                        ignore=shutil.ignore_patterns('.git'))
                    else:
                        shutil.copy2(str(item), str(target))
                    seen.add(item.name)
                    copied += 1
                except Exception as e:
                    print(f"{COLOR_RED}[!] Failed to copy rule {item.name}: {e}{COLOR_RESET}")
        if copied:
            print(f"{COLOR_GREEN}[OK] .agents/rules/: {copied} files copied{COLOR_RESET}")

    def init_mcp(self, source_mcp_file: Path):
        """同步 mcp 配置到 .agents/mcp/。"""
        if not source_mcp_file or not Path(source_mcp_file).exists():
            return
        dst_dir = self.agent_dir / "mcp"
        dst_dir.mkdir(parents=True, exist_ok=True)
        copy_file_safe(source_mcp_file, dst_dir / Path(source_mcp_file).name,
                       f".agents/mcp/{Path(source_mcp_file).name}", self.force)

    def init_skills(self, source_skills_dir: Path):
        """同步 skills 到 .agents/skills/（软链接方式）。

        .agents/skills/ 同时是安装落地处和 sync 源之一。为避免源=目标时
        copy_skills_safe 在 force 模式下 rmtree 目标导致源被删，这里先解析出
        目标绝对路径，从源列表中剔除与目标相同的源（自我复制无意义）。
        """
        agents_skills_dir = (self.agent_dir / "skills").resolve()
        # 归一化源列表，剔除与目标重叠的源（避免 force 模式下自删）
        if isinstance(source_skills_dir, list):
            srcs = [s for s in source_skills_dir if s and s.exists() and s.resolve() != agents_skills_dir]
        elif source_skills_dir and source_skills_dir.exists() and source_skills_dir.resolve() != agents_skills_dir:
            srcs = [source_skills_dir]
        else:
            srcs = []

        if srcs:
            copy_skills_safe(srcs, agents_skills_dir, ".agents/skills/",
                             self.force, self.include_skills, link=self.link_skills)
            write_skills_index(srcs, agents_skills_dir / "README.md",
                               "Agents", self.force, self.include_skills)
        else:
            # 源与目标完全重叠（或无源）：仅生成索引
            write_skills_index(agents_skills_dir, agents_skills_dir / "README.md",
                               "Agents", self.force, self.include_skills)

        # 统计 .agents/skills/ 下的 skill 数（含安装落地 + 其他源同步进来的）
        if agents_skills_dir.exists():
            def _safe_is_dir(d):
                try:
                    return d.is_dir() and not d.is_symlink()
                except OSError:
                    return False
            skill_count = sum(1 for d in agents_skills_dir.iterdir() if _safe_is_dir(d))
            print(f"{COLOR_GREEN}[OK] {skill_count} skills available in .agents/skills/{COLOR_RESET}")

    def init_manifest(self, source_agents_md: Path):
        """同步 AGENTS.md 到 .agents/AGENTS.md。"""
        if not source_agents_md or not Path(source_agents_md).exists():
            return
        copy_file_safe(source_agents_md, self.agent_dir / "AGENTS.md",
                       ".agents/AGENTS.md", self.force)

    def init_llm(self, source_rules_dir: Path):
        """同步 subagents 到 .agents/subagents/。"""
        subagents_src = self.root / "config" / "subagents"
        if subagents_src.exists():
            dst = self.agent_dir / "subagents"
            copy_dir_safe(subagents_src, dst, ".agents/subagents/", self.force)

    def run(self, source_rules: Path, source_mcp_file: Path,
            source_skills_dir: Path, source_agents_md: Path) -> str:
        """Agents 始终同步全部内容到 .agents/，不受 scope 限制。"""
        from lib.logging import COLOR_MAGENTA, COLOR_RESET
        print(f"\n{COLOR_MAGENTA}--- {self.name} (.agents/) ---{COLOR_RESET}")
        self.init_rules(source_rules)
        self.init_mcp(source_mcp_file)
        self.init_skills(source_skills_dir)
        self.init_llm(source_rules)
        self.init_manifest(source_agents_md)
        return self.name
