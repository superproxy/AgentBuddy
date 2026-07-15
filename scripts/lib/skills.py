"""技能安装与同步。

迁移自 scripts/init-ide.py（copy_skills_safe / write_skills_index，含白名单过滤）+
scripts/plugin-manager.py（parse_shorthand / build_install_command / install_skill）。
保持函数签名与行为不变。

INCLUDE_SKILLS 全局变量改为函数参数 include_skills，避免模块级状态。
"""
import csv
import re
import shutil
import subprocess
import sys
from pathlib import Path

from lib.logging import (
    COLOR_CYAN, COLOR_GREEN, COLOR_YELLOW, COLOR_RED, COLOR_DARKGRAY, COLOR_MAGENTA, COLOR_RESET,
)
from lib.config_io import load_env_config_file, save_env_config_file

H1 = "## "
H2 = "### "
H3 = "#### "


# ============================================================
# skill.yaml 读写（启用清单管理）
# ============================================================

def load_skill_yaml(skill_yaml_path: Path) -> dict:
    """读取 skill.yaml，返回 {enabled: [name, ...]}。"""
    if not skill_yaml_path.exists():
        return {"enabled": []}
    try:
        data = load_env_config_file(skill_yaml_path)
        if not isinstance(data, dict):
            return {"enabled": []}
        if "enabled" not in data:
            data["enabled"] = []
        return data
    except Exception:
        return {"enabled": []}


def save_skill_yaml(skill_yaml_path: Path, data: dict) -> None:
    """保存 skill.yaml。"""
    save_env_config_file(skill_yaml_path, data)


def get_enabled_skills(skill_yaml_path: Path) -> set:
    """获取启用的技能名集合。"""
    data = load_skill_yaml(skill_yaml_path)
    return set(data.get("enabled", []))


def enable_skill(skill_yaml_path: Path, skill_name: str) -> bool:
    """启用技能，返回是否新增。"""
    data = load_skill_yaml(skill_yaml_path)
    enabled = data.get("enabled", [])
    if skill_name in enabled:
        return False
    enabled.append(skill_name)
    data["enabled"] = enabled
    save_skill_yaml(skill_yaml_path, data)
    return True


def disable_skill(skill_yaml_path: Path, skill_name: str) -> bool:
    """禁用技能，返回是否移除。"""
    data = load_skill_yaml(skill_yaml_path)
    enabled = data.get("enabled", [])
    if skill_name not in enabled:
        return False
    enabled.remove(skill_name)
    data["enabled"] = enabled
    save_skill_yaml(skill_yaml_path, data)
    return True


def scan_local_skills(project_root: Path) -> list:
    """扫描本地所有技能（template/skills + config/skills + .agents/skills），返回去重的技能名列表。"""
    seen = set()
    for d in (project_root / "template" / "skills", project_root / "config" / "skills", project_root / ".agents" / "skills"):
        if not d.exists():
            continue
        for skill_dir in sorted(d.iterdir()):
            if skill_dir.is_dir() and skill_dir.name not in seen:
                seen.add(skill_dir.name)
    return sorted(seen)


# ============================================================
# Skill 同步（含白名单过滤）
# ============================================================

def _normalize_skill_sources(src) -> list:
    """归一化 skill 源：接受 Path 或 list[Path]，返回存在的 Path 列表。"""
    if isinstance(src, list):
        return [s for s in src if s.exists()]
    if isinstance(src, Path) and src.exists():
        return [src]
    return []


def copy_skills_safe(src, dst: Path, label: str, force: bool,
                     include_skills=None) -> None:
    """复制技能目录到 IDE skills 目录。

    Args:
        src: 源目录，支持 Path 或 list[Path]（多源时前者优先，后者补充同名以外的 skill）。
        include_skills: 白名单集合，仅复制名称在此集合内的技能；
                        None 表示复制全部。
    """
    srcs = _normalize_skill_sources(src)
    if not srcs:
        if isinstance(src, list):
            print(f"{COLOR_YELLOW}[!] No skills source dirs found: {src}{COLOR_RESET}")
        else:
            print(f"{COLOR_YELLOW}[!] Skills source dir not found: {src}{COLOR_RESET}")
        return

    dst.parent.mkdir(parents=True, exist_ok=True)

    copied = 0
    skipped = 0
    seen = set()  # 已处理的 skill 名（前源优先，后源跳过同名）

    for src_dir in srcs:
        for skill_dir in sorted(src_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            if skill_dir.name in seen:
                continue  # 前一个源已处理，跳过同名
            seen.add(skill_dir.name)
            # 按白名单过滤
            if include_skills is not None and skill_dir.name not in include_skills:
                continue
            skill_dst = dst / skill_dir.name
            if skill_dst.exists():
                if force:
                    shutil.rmtree(str(skill_dst), ignore_errors=True)
                else:
                    skipped += 1
                    continue
            try:
                shutil.copytree(str(skill_dir), str(skill_dst), ignore=shutil.ignore_patterns('.git'))
                copied += 1
            except Exception as e:
                print(f"{COLOR_RED}[!] Failed to copy skill {skill_dir.name}: {e}{COLOR_RESET}")

    if copied > 0:
        print(f"{COLOR_GREEN}[OK] {label}: {copied} skills copied{COLOR_RESET}")
    if skipped > 0:
        print(f"{COLOR_DARKGRAY}[~] {label}: {skipped} skills skipped (already exist){COLOR_RESET}")


def load_skill_mapping(csv_path: Path) -> dict:
    """Load skill-to-role mapping from CSV file."""
    mapping = {}
    if not csv_path.exists():
        return mapping
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("skill_name", "").strip()
            if name:
                mapping[name] = {
                    "category": row.get("category", "").strip(),
                    "role": row.get("role", "").strip(),
                    "description": row.get("description", "").strip(),
                    "trigger_keywords": row.get("trigger_keywords", "").strip(),
                    "installable": row.get("installable", "false").strip().lower() == "true",
                }
    return mapping


def build_role_mapping_table(mapping: dict) -> list:
    """Build role-to-skills mapping table lines from CSV data."""
    role_skills: dict = {}
    installable_skills: list = []
    for skill_name, info in mapping.items():
        if info.get("installable"):
            installable_skills.append(skill_name)
            continue
        roles = [r.strip() for r in info["role"].split("|") if r.strip()]
        for role in roles:
            if role not in role_skills:
                role_skills[role] = []
            role_skills[role].append(skill_name)

    lines = []
    lines.append(f"{H2}Skill to Role Mapping")
    lines.append("")
    lines.append("| Role | Recommended Skills |")
    lines.append("|------|-------------------|")
    for role in sorted(role_skills.keys()):
        skills = ", ".join(role_skills[role])
        lines.append(f"| {role} | {skills} |")

    if installable_skills:
        lines.append("")
        lines.append(f"{H2}Installable Skills (通用)")
        lines.append("")
        lines.append("> 以下技能为通用技能，需通过 `find-skills` 安装后使用。")
        lines.append("")
        lines.append("| Skill | Category | Description |")
        lines.append("|-------|----------|-------------|")
        for skill_name in sorted(installable_skills):
            info = mapping[skill_name]
            lines.append(f"| `{skill_name}` | {info['category']} | {info['description']} |")
    return lines


def write_skills_index(skills_source_dir: Path, target_file: Path, ide_name: str, force: bool,
                       include_skills=None) -> None:
    """生成技能索引 README.md。

    Args:
        skills_source_dir: 源目录，支持 Path 或 list[Path]（多源合并索引，前者优先）。
        include_skills: 白名单集合，仅索引名称在此集合内的技能；
                        None 表示索引全部。
    """
    srcs = _normalize_skill_sources(skills_source_dir)
    if not srcs:
        if isinstance(skills_source_dir, list):
            print(f"{COLOR_YELLOW}[!] No skills source dirs found: {skills_source_dir}{COLOR_RESET}")
        else:
            print(f"{COLOR_YELLOW}[!] Skills source dir not found: {skills_source_dir}{COLOR_RESET}")
        return

    if target_file.exists() and not force:
        print(f"{COLOR_YELLOW}[!] Skills index exists, use --force to overwrite{COLOR_RESET}")
        return

    target_file.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append(f"{H1}{ide_name} Skills Index")
    lines.append("")
    lines.append("Auto-generated by agentctl. Lists all available AI skills.")
    lines.append("")

    if ide_name == "Cursor":
        lines.append("> Cursor IDE does not natively support a Skills directory. Use `@file-path` to reference SKILL.md in conversations.")
    elif ide_name == "Agents":
        lines.append("> `config/skills/` 是项目级 AI 智能体技能目录，可作为多项目通用技能源。")
    elif ide_name == "Codex":
        lines.append("> Codex IDE supports Skills via `.codex/skills/` directory.")
    elif ide_name == "Claude":
        lines.append("> Claude IDE supports Skills via `.claude/skills/` directory.")
    else:
        lines.append("> Trae IDE supports Skills via `.trae/skills/` directory.")
    lines.append("")

    lines.append(f"{H2}Skill List")
    lines.append("")

    seen = set()  # 前源优先，后源跳过同名
    for src_dir in srcs:
        for skill_dir in sorted(src_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            if skill_dir.name in seen:
                continue
            seen.add(skill_dir.name)
            # 按白名单过滤
            if include_skills is not None and skill_dir.name not in include_skills:
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue

            skill_content = skill_file.read_text(encoding="utf-8")
            name = skill_dir.name
            description = ""

            desc_match = re.search(r'description:\s*>-?\s*\n?\s*(.+?)(\n\w+:|$)', skill_content)
            if not desc_match:
                desc_match = re.search(r'description:\s*"(.+?)"', skill_content)
            if not desc_match:
                desc_match = re.search(r'description:\s*(.+?)(\n\w+:|$)', skill_content)
            if desc_match:
                description = desc_match.group(1).strip()
                description = re.sub(r'>\s*', ' ', description)
                description = re.sub(r'\s+', ' ', description).strip()

            try:
                relative_path = skill_file.resolve().relative_to(Path.cwd())
            except ValueError:
                relative_path = skill_file

            lines.append(f"{H3}{name}")
            lines.append("")
            lines.append(f"- **Description**: {description}")
            lines.append(f"- **Path**: {relative_path}")
            lines.append("")

    lines.append(f"{H2}Skill to Role Mapping")
    lines.append("")
    # CSV 在 template/skills/ 目录内
    csv_path = srcs[0] / "skills-index.csv"
    mapping = load_skill_mapping(csv_path)
    if mapping:
        lines.extend(build_role_mapping_table(mapping))
    else:
        lines.append("| Role | Recommended Skills |")
        lines.append("|------|-------------------|")
        lines.append("| Frontend | stitch-prototype-skill, mastergo-magic-skill, drawio-skill, mermaid-sequence-from-flow |")
        lines.append("| Backend | restful-api-design-skill, task-plan-skill, drawio-skill |")
        lines.append("| Design | stitch-prototype-skill, mastergo-magic-skill, prd-to-mastergo-interaction-skill, drawio-skill |")
        lines.append("| Product | usecase-prd-skill, task-plan-skill, weekly-report-skill, prd-to-mastergo-interaction-skill |")
        lines.append("")
        lines.append(f"{H2}Installable Skills (通用)")
        lines.append("")
        lines.append("> 以下技能为通用技能，需通过 `find-skills` 安装后使用。")
        lines.append("")
        lines.append("| Skill | Category | Description |")
        lines.append("|-------|----------|-------------|")
        lines.append("| `find-skills` | 技能发现 | 帮助发现和查找仓库中的 AI 技能 |")
        lines.append("| `personnel-recruitment` | 人力资源 | 结构化招聘（JD优化/简历筛选/面试设计/评分卡/录用建议） |")
        lines.append("| `hardware-agent-prompt-skill` | 硬件AI | 为硬件 AI 智能体生成提示词与角色设定 |")
        lines.append("| `elon-musk-perspective` | 思维模型 | 马斯克思维模型分析（第一性原理/五步算法/白痴指数/垂直整合） |")

    target_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{COLOR_GREEN}[OK] Skills index: {target_file}{COLOR_RESET}")


# ============================================================
# Skill 安装（来自 plugin-manager.py）
# ============================================================

def parse_shorthand(source_str: str) -> tuple:
    """解析 owner/repo@skill 简写格式，返回 (source, skill)。"""
    if not source_str:
        return ("", "")

    stripped = source_str.strip()

    if (stripped.startswith("http://")
            or stripped.startswith("https://")
            or stripped.startswith("git@")
            or stripped.startswith("ssh://")
            or stripped.startswith("git://")):
        return (stripped, "")

    if "/" not in stripped:
        return ("", stripped)

    last_slash_idx = stripped.rfind("/")
    after_slash = stripped[last_slash_idx + 1:]
    at_idx = after_slash.find("@")
    if at_idx >= 0:
        source = stripped[:last_slash_idx + 1 + at_idx]
        skill = after_slash[at_idx + 1:]
        return (source, skill)
    return (stripped, "")


def resolve_github_owner_repo(source_str: str) -> tuple:
    """从 owner/repo、GitHub URL、tree URL 解析 (owner, repo)，失败返回 ('', '')。"""
    raw = (source_str or "").strip()
    if not raw:
        return ("", "")
    # 去掉 @skill
    src, _ = parse_shorthand(raw)
    raw = src or raw
    m = re.match(
        r"(?:https?://github\.com/|git@github\.com:|ssh://git@github\.com/)"
        r"([^/]+)/([^/#?\s]+)",
        raw,
        re.I,
    )
    if m:
        return m.group(1), re.sub(r"\.git$", "", m.group(2))
    if re.match(r"^[^/\s]+/[^/@\s]+$", raw):
        owner, repo = raw.split("/", 1)
        return owner, repo
    return ("", "")


_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07|\r")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text or "")


def _parse_skills_cli_list(output: str) -> list:
    """解析 `npx skills add <src> -l` 的终端输出为 [{name, description}]。"""
    clean = _strip_ansi(output)
    skills = []
    # 定位 Available Skills 段
    idx = clean.find("Available Skills")
    body = clean[idx:] if idx >= 0 else clean
    lines = body.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        # 名称行：|    name   （4 空格，非 6 空格描述）
        m = re.match(r"^\|\s{4}([a-zA-Z0-9][\w.:+-]*)\s*$", line)
        if m:
            name = m.group(1)
            desc_parts = []
            j = i + 1
            while j < len(lines):
                dm = re.match(r"^\|\s{6}(.+?)\s*$", lines[j])
                if dm:
                    desc_parts.append(dm.group(1).strip())
                    j += 1
                    continue
                if re.match(r"^\|\s*$", lines[j]) or lines[j].strip() in ("|",):
                    j += 1
                    # 空行后若下一条是新名称则结束
                    if j < len(lines) and re.match(r"^\|\s{4}[a-zA-Z0-9]", lines[j]):
                        break
                    continue
                break
            skills.append({"name": name, "description": " ".join(desc_parts).strip()})
            i = j
            continue
        i += 1
    # 去重保序
    seen = set()
    out = []
    for s in skills:
        if s["name"] in seen:
            continue
        seen.add(s["name"])
        out.append(s)
    return out


def _list_skills_via_github(owner: str, repo: str, timeout: int = 20) -> list:
    """通过 GitHub Trees API 发现仓库内 SKILL.md。"""
    import os
    import requests

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "AdeBuddy/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    tree = None
    last_err = None
    for ref in ("HEAD", "main", "master"):
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{ref}"
            resp = requests.get(url, params={"recursive": "1"}, headers=headers, timeout=timeout)
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
            tree = resp.json()
            break
        except Exception as e:
            last_err = e
            continue
    if tree is None:
        raise RuntimeError(f"无法读取 GitHub 仓库树: {owner}/{repo}" + (f" ({last_err})" if last_err else ""))

    items = []
    for node in tree.get("tree") or []:
        path = node.get("path") or ""
        if node.get("type") != "blob":
            continue
        if not path.replace("\\", "/").lower().endswith("/skill.md") and path.lower() != "skill.md":
            continue
        parts = path.replace("\\", "/").split("/")
        if path.lower() == "skill.md":
            folder_name = repo
        else:
            folder_name = parts[-2] if len(parts) >= 2 else parts[0]
        items.append({
            "name": folder_name,
            "folder": folder_name,
            "description": "",
            "path": path,
        })

    # 补 name/description：优先读 frontmatter name（与 npx skills --skill 一致）
    for it in items:
        try:
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{it['path']}"
            r = requests.get(raw_url, headers={"User-Agent": "AdeBuddy/1.0"}, timeout=8)
            if r.status_code != 200:
                continue
            text = r.text[:5000]
            nm = re.search(r"(?m)^name:\s*[\"']?([^\n\"']+)", text)
            if nm:
                it["name"] = nm.group(1).strip()
            dm = re.search(r"(?m)^description:\s*[>\-|]*\s*(.+?)(?:\n\w|\n---|\Z)", text, re.S)
            if not dm:
                dm = re.search(r'(?m)^description:\s*["\'](.+?)["\']', text)
            if dm:
                desc = re.sub(r"\s+", " ", dm.group(1)).strip()
                it["description"] = desc[:240]
        except Exception:
            pass
    return items


def _list_skills_via_cli(source: str, timeout: int = 120) -> list:
    """回退：调用 npx skills add <source> -l 列出技能。"""
    cmd = [
        "npx", "--yes", "skills",
        "add", source,
        "-l", "-y",
        "--agent", "cursor",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=(sys.platform == "win32"),
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("列出技能超时，请检查网络或仓库地址")
    except FileNotFoundError:
        raise RuntimeError("未找到 npx，请先安装 Node.js")
    text = (result.stdout or "") + "\n" + (result.stderr or "")
    skills = _parse_skills_cli_list(text)
    if not skills and result.returncode != 0:
        raise RuntimeError("无法列出技能，请确认仓库地址是否正确")
    return skills


def list_remote_skills(source_str: str) -> dict:
    """预览远程源中的技能列表，供手动安装勾选。

    返回:
      {
        source, skill_filter, skills:[{name,description,path?}],
        method: 'github'|'cli'|'explicit', count
      }
    """
    raw = (source_str or "").strip()
    if not raw:
        raise ValueError("缺少 source")

    src, skill_filter = parse_shorthand(raw)
    effective = src or raw

    # 已指定 @skill → 单技能确认态
    if skill_filter:
        return {
            "source": effective,
            "skill_filter": skill_filter,
            "skills": [{"name": skill_filter, "description": f"将安装指定技能 {skill_filter}"}],
            "method": "explicit",
            "count": 1,
        }

    owner, repo = resolve_github_owner_repo(effective)
    skills = []
    method = "cli"
    err = None
    if owner and repo:
        try:
            skills = _list_skills_via_github(owner, repo)
            method = "github"
        except Exception as e:
            err = str(e)
            skills = []

    if not skills:
        try:
            skills = _list_skills_via_cli(effective)
            method = "cli"
            err = None
        except Exception as e:
            if not skills:
                raise RuntimeError(err or str(e))

    return {
        "source": effective,
        "skill_filter": "",
        "skills": skills,
        "method": method,
        "count": len(skills),
    }


def ensure_npx_yes(cmd: str) -> str:
    """确保 npx 自动确认包安装，避免交互提示：
    Need to install the following packages:
    skills@x.y.z
    """
    cmd = (cmd or "").strip()
    if not cmd:
        return cmd
    # 已有 npx -y / npx --yes（紧跟 npx 的参数，不是末尾 skills CLI 的 -y）
    if re.match(r"^npx\s+(-y|--yes)\b", cmd):
        return cmd
    if re.match(r"^npx\b", cmd):
        return re.sub(r"^npx\b", "npx --yes", cmd, count=1)
    return cmd


def build_install_command(skill_config, use_symlink: bool = False) -> tuple:
    """构建安装命令，返回 (skill_name, install_command)。

    use_symlink 参数保留以兼容调用方，但不再生成 --copy/symlink 标志
    （统一使用 npx skills add 默认行为）。
    """
    skill_name = ""

    if isinstance(skill_config, dict):
        explicit_skill = skill_config.get("skill", "")
        skill_name = explicit_skill or skill_config.get("name", "")
        source = skill_config.get("source", "")
        url = skill_config.get("url", "")

        if url:
            install_command = f"npx --yes skills add {url} --skill {skill_name} -y".strip()
        elif source:
            parsed_source, parsed_skill = parse_shorthand(source)
            # source 是 "owner/repo@skill" 格式 → parsed_source 和 parsed_skill 都有值
            if parsed_source and parsed_skill:
                effective_source = parsed_source
                effective_skill = parsed_skill
                skill_name = effective_skill
            # source 是 "owner/repo" 格式 → 只有 parsed_source 有值，安装整个仓库
            elif parsed_source and "/" in parsed_source:
                effective_source = parsed_source
                effective_skill = explicit_skill  # 仅当显式指定 skill 字段才加 --skill
            # source 是单纯技能名（无 /）→ 直接按名安装，不加 --skill
            else:
                effective_source = source
                effective_skill = ""

            if effective_skill:
                install_command = f"npx --yes skills add {effective_source} --skill {effective_skill} -y".strip()
            else:
                install_command = f"npx --yes skills add {effective_source} -y".strip()
        else:
            install_command = f"npx --yes skills add {skill_name} -y".strip()
    elif isinstance(skill_config, str):
        if skill_config.startswith("npx"):
            install_command = skill_config
            match = re.search(r'--skill\s+([^\s]+)', install_command)
            if match:
                skill_name = match.group(1)
            else:
                match = re.search(r'add\s+([^\s]+)', install_command)
                if match:
                    raw_source = match.group(1)
                    _, parsed_skill = parse_shorthand(raw_source)
                    skill_name = parsed_skill or raw_source
        else:
            parsed_source, parsed_skill = parse_shorthand(skill_config)
            if parsed_source and parsed_skill:
                skill_name = parsed_skill
                install_command = f"npx --yes skills add {parsed_source} --skill {parsed_skill} -y".strip()
            elif parsed_source:
                skill_name = parsed_source
                install_command = f"npx --yes skills add {parsed_source} -y".strip()
            else:
                skill_name = parsed_skill
                install_command = f"npx --yes skills add {parsed_skill} -y".strip()
    else:
        skill_name = str(skill_config)
        install_command = f"npx --yes skills add {skill_name} -y".strip()

    install_command = ensure_npx_yes(re.sub(r'\s+', ' ', install_command).strip())
    return skill_name, install_command


def install_skill(skill_config, source_dir: Path = None, use_symlink: bool = False) -> bool:
    """安装技能：source 有效则先用 source；否则 find-skills 按名查找；再找本地缓存；都不行则失败。

    流程：
      1. 已存在于 config/skills/ 或 .agents/skills/ → 跳过（成功）
      2. source 有效（owner/repo 或 url）→ npx skills add <source> [--skill <name>]
         - 有 --skill → 安装指定技能，按 <name> 验证
         - 无 --skill（整个仓库）→ returncode==0 即视为成功
      3. find-skills 按名查找：npx skills add <name> -y（市场搜索）
      4. 本地缓存 template/skills/<name> → 复制到 config/skills/
      5. 仍未成功 → 返回 False（失败）

    Returns:
        True 安装成功（含跳过），False 安装失败。
    """
    skill_name, source_command = build_install_command(skill_config, use_symlink=use_symlink)
    # 判断 source 是否有效（含 owner/repo 或 url）
    has_explicit_source = bool(source_command) and (
        '--skill' in source_command
        or source_command.startswith('http')
        or ' add ' in source_command and '/' in source_command.split(' add ', 1)[1].split(' ', 1)[0]
    )
    # 是否安装整个仓库（无 --skill）→ 不能按 <name> 目录验证
    is_whole_repo = has_explicit_source and '--skill' not in source_command

    if not skill_name:
        print(f"{COLOR_RED}[!] Could not determine skill name, skipping{COLOR_RESET}")
        return False

    install_cwd = source_dir if source_dir else None

    def _skill_exists(name):
        """检查 skill 是否已存在于 config/skills/ 或 .agents/skills/。"""
        if source_dir:
            if (source_dir / "config" / "skills" / name).exists():
                return True
            if (source_dir / ".agents" / "skills" / name).exists():
                return True
        return False

    # Step 1: 已存在于 config/skills/ 或 .agents/skills/ → 跳过（仅对单技能安装有效）
    if source_dir and not is_whole_repo:
        if _skill_exists(skill_name):
            print(f"{COLOR_DARKGRAY}[-] Skill already exists: {skill_name}, skipping update{COLOR_RESET}")
            return True

    def _verify_installed():
        """检查技能是否已落到 config/skills/、.agents/skills/ 或全局目录。

        整个仓库安装时跳过此检查（returncode==0 即视为成功）。
        """
        if is_whole_repo:
            return True
        if source_dir:
            expected = source_dir / "config" / "skills" / skill_name
            if expected.exists():
                return True
            agents_skill = source_dir / ".agents" / "skills" / skill_name
            if agents_skill.exists():
                print(f"{COLOR_YELLOW}[!] Skill installed to .agents/skills: {agents_skill}{COLOR_RESET}")
                return True
            home_skill = Path.home() / ".config" / "skills" / skill_name
            if home_skill.exists():
                print(f"{COLOR_YELLOW}[!] Skill installed to global dir: {home_skill}{COLOR_RESET}")
                print(f"    期望位置: {expected}")
                return True
        return False

    # Step 2: source 有效 → 用 source 安装
    if has_explicit_source:
        print(f"{COLOR_MAGENTA}[-] Installing skill via source: {source_command}{COLOR_RESET}")
        try:
            result = subprocess.run(
                source_command,
                shell=True,
                capture_output=False,
                text=True,
                encoding='utf-8',
                errors='ignore',
                cwd=install_cwd
            )
            if result.returncode == 0 and _verify_installed():
                print(f"{COLOR_GREEN}[OK] Skill installed via source: {skill_name}{COLOR_RESET}")
                return True
            print(f"{COLOR_YELLOW}[!] source 安装未成功，尝试 find-skills 按名查找{COLOR_RESET}")
        except Exception as e:
            print(f"{COLOR_YELLOW}[!] source 安装错误: {e}，尝试 find-skills 按名查找{COLOR_RESET}")

    # Step 3: find-skills 按名查找（市场搜索，忽略可能无效的 source）
    find_command = f"npx --yes skills add {skill_name} -y"
    print(f"{COLOR_MAGENTA}[-] find-skills 查找: {find_command}{COLOR_RESET}")
    try:
        result = subprocess.run(
            find_command,
            shell=True,
            capture_output=False,
            text=True,
            encoding='utf-8',
            errors='ignore',
            cwd=install_cwd
        )
        if result.returncode == 0 and _verify_installed():
            print(f"{COLOR_GREEN}[OK] Skill installed from marketplace: {skill_name}{COLOR_RESET}")
            return True
        print(f"{COLOR_YELLOW}[!] find-skills 未找到 {skill_name}，尝试本地缓存{COLOR_RESET}")
    except Exception as e:
        print(f"{COLOR_YELLOW}[!] find-skills 错误: {e}，尝试本地缓存{COLOR_RESET}")

    # Step 4: 本地缓存 → 复制到 config/skills/（仅对单技能安装有效）
    # 搜索五个缓存源（优先级：项目级 → 全局 IDE 目录 → template 预置）
    if source_dir and not is_whole_repo:
        cache_dirs = [
            source_dir / "config" / "skills" / skill_name,
            source_dir / ".agents" / "skills" / skill_name,
            source_dir / "template" / "skills" / skill_name,
            Path.home() / ".zcode" / "skills" / skill_name,
            Path.home() / ".config" / "skills" / skill_name,
        ]
        cache_skill_dir = next((d for d in cache_dirs if d.exists()), None)
        if cache_skill_dir:
            print(f"{COLOR_MAGENTA}[-] Installing skill from local cache: {skill_name}{COLOR_RESET}")
            print(f"    缓存源: {cache_skill_dir}{COLOR_RESET}")
            try:
                target_skills_dir = source_dir / "config" / "skills"
                target_skills_dir.mkdir(parents=True, exist_ok=True)
                target_skill_dir = target_skills_dir / skill_name
                # 如果目标已存在（可能来自 .agents/skills/），先删除再复制
                if target_skill_dir.exists():
                    shutil.rmtree(target_skill_dir, ignore_errors=True)
                shutil.copytree(cache_skill_dir, target_skill_dir, ignore=shutil.ignore_patterns('.git'))
                print(f"{COLOR_GREEN}[OK] Skill copied from local cache: {skill_name}{COLOR_RESET}")
                return True
            except Exception as e:
                print(f"{COLOR_RED}[!] Local cache copy failed: {e}{COLOR_RESET}")

    # Step 5: 都不行 → 失败
    print(f"{COLOR_RED}[✗] Skill install failed (not via source/marketplace/local): {skill_name}{COLOR_RESET}")
    return False
