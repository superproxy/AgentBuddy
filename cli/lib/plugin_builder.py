"""插件构建引擎 — 三场景共享的底层能力。

场景一: agentctl plugin build/publish (命令行)
场景二: 桌面端 /api/plugin/analyze + 一键构建 UI
场景三: server/PluginMarketWorker.py 定时抓取 worker

核心流程: analyze_source → download_skills → generate_yaml → package → publish
"""
from __future__ import annotations

import copy
import io
import json
import re
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from .config_io import load_env_config_file, save_env_config_file
from .logging import info, warn, error, hint, header, COLOR_GREEN, COLOR_CYAN, COLOR_RESET

# 字数限制（名称/描述，三场景统一；对齐 plugin.schema.yaml 的 name kebab-case 约束）
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 500
NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# 分析结果 TTL 缓存（秒）：同一来源短时间复用，避免「分析→构建」重复消耗 GitHub API 配额
ANALYZE_CACHE_TTL = 600
_ANALYZE_CACHE: dict[tuple[str, bool], tuple[float, "PluginMeta"]] = {}


def sanitize_name(raw: str) -> str:
    """清洗插件名：kebab-case、小写、截断到 MAX_NAME_LENGTH。"""
    name = _slugify((raw or "").strip())[:MAX_NAME_LENGTH].strip("-")
    return name or "plugin"


def truncate_description(raw: str, max_len: int = MAX_DESCRIPTION_LENGTH) -> str:
    """描述截断：压平空白后截到 max_len，不在半个词中间断（尽量按词/句边界收尾）。"""
    # 剔除控制字符（\x00-\x08 等），避免混入 JSON 响应导致前端严格解析失败
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", (raw or ""))
    text = re.sub(r"\s+", " ", text.strip())
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    # 优先在最后一个句号/问号/感叹号处收尾，其次最后一个空格
    for sep in ("。", "！", "？", ".", "!", "?"):
        idx = cut.rfind(sep)
        if idx >= max_len // 2:
            return cut[: idx + 1].strip()
    idx = cut.rfind(" ")
    if idx > 0:
        cut = cut[:idx]
    cut = cut.strip()
    return cut if len(cut) <= max_len else cut[: max_len - 1].rstrip() + "…"


# ============================================================
# 数据结构
# ============================================================

@dataclass
class SkillInfo:
    name: str
    description: str = ""
    source: str = ""
    requires_key: bool = False


@dataclass
class PluginMeta:
    """从来源分析得到的插件元数据。"""
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    license: str = ""
    homepage: str = ""
    repository: str = ""
    skills: list[SkillInfo] = field(default_factory=list)
    mcp_servers: dict[str, dict] = field(default_factory=dict)
    env_vars: dict[str, dict] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    source_type: str = ""  # github / url / local
    source_url: str = ""


# ============================================================
# PluginBuilder 引擎
# ============================================================

class PluginBuilder:
    """插件构建引擎，三场景共享。"""

    # Skill 搜索目录优先级（与 config_server.py 的常量对齐）
    SKILL_DIRS = [
        Path("config/skills"),
        Path(".agents/skills"),
        Path("template/skills"),
    ]

    def __init__(self, project_root: Path, server_url: str | None = None):
        self.project_root = project_root
        # 可选：AI 分析模式调用 server 端 /api/ai/generate（SSE）。
        # 未配置时 _analyze_url_with_ai 降级到简单分析，避免反向依赖 server 包。
        self.server_url = (server_url or "").strip().rstrip("/") or None

    # ----------------------------------------------------------
    # 1. 分析来源
    # ----------------------------------------------------------

    def analyze_source(self, source: str, ai: bool = False) -> PluginMeta:
        """从来源分析插件元数据。

        source 可以是:
        - GitHub 仓库简写 (owner/repo)
        - GitHub URL (https://github.com/owner/repo)
        - 文章 URL (https://mp.weixin.qq.com/s/xxx)  — 需要 ai=True
        - 本地目录路径 (./my-plugin/ 或 /abs/path)
        """
        source = source.strip()
        if not source:
            raise ValueError("来源不能为空")

        # TTL 缓存：同一来源的分析结果短期复用。
        # 背景：GitHub 匿名 API 限流 60 次/小时，UI「分析 → 构建」流程会让 build 把
        # 刚分析过的源从头再调一遍 API（repo info + git tree + N 个 SKILL.md），
        # 几次操作就耗光配额，之后所有分析/构建全部报错或挂起。
        cache_key = (source, bool(ai))
        now = time.time()
        hit = _ANALYZE_CACHE.get(cache_key)
        if hit and now - hit[0] < ANALYZE_CACHE_TTL:
            # 返回浅拷贝，调用方对 meta 的修改（参数覆盖）不污染缓存
            cached = hit[1]
            return PluginMeta(
                name=cached.name, version=cached.version,
                description=cached.description, author=cached.author,
                license=cached.license, homepage=cached.homepage,
                repository=cached.repository,
                skills=[SkillInfo(**vars(s)) for s in cached.skills],
                mcp_servers=json.loads(json.dumps(cached.mcp_servers)),
                env_vars=json.loads(json.dumps(cached.env_vars)),
                tags=list(cached.tags),
                source_type=cached.source_type, source_url=cached.source_url,
            )

        if _is_local_path(source):
            meta = self._analyze_local(source)
        elif _is_github_shorthand(source) or _is_github_url(source):
            meta = self._analyze_github(source)
        elif _is_url(source):
            if ai:
                meta = self._analyze_url_with_ai(source)
            else:
                # 非 AI 模式：尝试直接抓取页面内容提取信息
                meta = self._analyze_url_simple(source)
        else:
            raise ValueError(f"无法识别的来源: {source}")

        # 清洗 skill 描述中的控制字符（来源不可信：SKILL.md frontmatter / 网页抓取）
        ctrl_re = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
        for s in meta.skills:
            if s.description:
                s.description = ctrl_re.sub("", s.description)

        _ANALYZE_CACHE[cache_key] = (now, meta)
        return meta

    def _analyze_local(self, path: str) -> PluginMeta:
        """分析本地目录。"""
        local_path = Path(path).resolve()
        if not local_path.exists():
            raise FileNotFoundError(f"路径不存在: {local_path}")

        meta = PluginMeta(
            name=local_path.name,
            source_type="local",
            source_url=str(local_path),
        )

        # 尝试读取已有的 plugin.yaml / plugin.json
        for fname in ("plugin.yaml", "plugin.yml", "plugin.json",
                       ".plugin.yaml", ".plugin.yml"):
            p = local_path / fname
            if p.exists():
                cfg = load_env_config_file(p)
                meta.name = cfg.get("name", meta.name)
                meta.version = str(cfg.get("version", "1.0.0"))
                meta.description = cfg.get("description", "")
                meta.author = cfg.get("author", "") if isinstance(cfg.get("author"), str) else ""
                meta.license = cfg.get("license", "")
                meta.homepage = cfg.get("homepage", "")
                meta.repository = cfg.get("repository", "") if isinstance(cfg.get("repository"), str) else ""
                meta.mcp_servers = cfg.get("mcpServers", {})
                meta.env_vars = cfg.get("envVars", {})
                for s in cfg.get("skills", []):
                    if isinstance(s, dict):
                        meta.skills.append(SkillInfo(
                            name=s.get("name", ""),
                            description=s.get("description", ""),
                            source=s.get("source", ""),
                        ))
                    elif isinstance(s, str):
                        meta.skills.append(SkillInfo(name=s))
                break

        # 扫描 skill 目录
        if not meta.skills:
            for sd in (local_path / "skills", local_path / "skill", local_path):
                if not sd.is_dir():
                    continue
                for md in sorted(sd.rglob("SKILL.md")):
                    skill_name = md.parent.name
                    meta.skills.append(SkillInfo(
                        name=skill_name,
                        description=_parse_skill_description(md),
                        source=str(md.parent),
                    ))

        # 如果没找到 plugin.yaml，用目录名作为 name
        if not meta.name:
            meta.name = local_path.name
        return meta

    def _analyze_github(self, source: str) -> PluginMeta:
        """分析 GitHub 仓库（通过 GitHub API）。"""
        owner_repo = _normalize_github(source)
        if not owner_repo:
            raise ValueError(f"无法解析 GitHub 仓库: {source}")

        repo_url = f"https://github.com/{owner_repo}"
        api_base = f"https://api.github.com/repos/{owner_repo}"

        meta = PluginMeta(
            name=owner_repo.split("/")[-1],
            source_type="github",
            source_url=repo_url,
            repository=repo_url,
            homepage=repo_url,
            license="",
        )

        # 1. 获取仓库基本信息
        try:
            import requests
            headers = _github_headers()
            resp = requests.get(api_base, headers=headers, timeout=15)
            _raise_if_rate_limited(resp, "获取仓库信息")
            if resp.ok:
                data = resp.json()
                meta.description = data.get("description", "") or ""
                meta.license = (data.get("license") or {}).get("spdx_id", "") or ""
                meta.homepage = data.get("homepage", "") or repo_url
        except ValueError:
            raise
        except Exception as e:
            warn(f"获取仓库信息失败: {e}")

        # 2. 获取文件树
        try:
            import requests
            resp = requests.get(f"{api_base}/git/trees/main?recursive=1",
                                headers=_github_headers(), timeout=15)
            if not resp.ok:
                _raise_if_rate_limited(resp, "获取文件树")
                resp = requests.get(f"{api_base}/git/trees/master?recursive=1",
                                    headers=_github_headers(), timeout=15)
            _raise_if_rate_limited(resp, "获取文件树")
            if resp.ok:
                tree = resp.json().get("tree", [])
                meta = _extract_meta_from_tree(meta, tree, api_base, owner_repo)
        except ValueError:
            raise
        except Exception as e:
            warn(f"获取文件树失败: {e}")

        return meta

    def _analyze_url_simple(self, url: str) -> PluginMeta:
        """非 AI 模式：简单抓取 URL 内容。"""
        meta = PluginMeta(
            name="",
            source_type="url",
            source_url=url,
        )

        try:
            import requests
            resp = requests.get(url, timeout=20, headers={
                "User-Agent": "Mozilla/5.0 (AgentBuddy Plugin Builder)"
            })
            if resp.ok:
                text = resp.text
                # 从 HTML 提取 title
                title_match = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
                if title_match:
                    meta.name = _slugify(title_match.group(1).strip()[:60])
                meta.description = _strip_html(text)[:500]
        except Exception as e:
            warn(f"抓取 URL 失败: {e}")

        if not meta.name:
            meta.name = "url-plugin"
        return meta

    def _analyze_url_with_ai(self, url: str) -> PluginMeta:
        """AI 模式：抓取 URL 内容后用 AI 分析。

        通过 HTTP 调用 server 端 /api/ai/generate（SSE），不再直接 import server 包。
        未配置 server_url 或调用失败时，降级到简单分析结果。
        """
        meta = self._analyze_url_simple(url)

        if not self.server_url:
            hint("未配置 server_url，AI 分析不可用，使用简单分析结果")
            return meta

        import requests

        prompt = f"分析以下网页内容，生成一个插件配置。URL: {url}\n\n内容摘要: {meta.description[:1000]}"
        try:
            # SSE 流式获取，最后一个 data 行含生成的 YAML
            resp = requests.get(
                f"{self.server_url}/api/ai/generate",
                params={"prompt": prompt},
                stream=True,
                timeout=120,
                headers={"Accept": "text/event-stream"},
            )
            if resp.status_code != 200:
                warn(f"AI 分析 HTTP {resp.status_code}，使用简单分析结果")
                return meta

            last_data = ""
            for line in resp.iter_lines(decode_unicode=True):
                if line and line.startswith("data: "):
                    last_data = line[6:]
            # 尝试从最后一个 data 行解析 YAML 并回填 meta
            if last_data and not last_data.startswith("[ERROR]"):
                yaml_text = _extract_yaml_from_text(last_data)
                if yaml_text:
                    parsed = yaml.safe_load(yaml_text)
                    if isinstance(parsed, dict):
                        if parsed.get("name"):
                            meta.name = sanitize_name(str(parsed["name"]))
                        if parsed.get("description"):
                            meta.description = truncate_description(str(parsed["description"]))
                        if parsed.get("skills"):
                            meta.skills = [
                                SkillInfo(
                                    name=sanitize_name(str(s.get("name", ""))),
                                    description=str(s.get("description", ""))[:500],
                                )
                                for s in parsed["skills"]
                                if isinstance(s, dict) and s.get("name")
                            ]
                        if parsed.get("mcp_servers"):
                            meta.mcp_servers = parsed["mcp_servers"]
                        if parsed.get("env_vars"):
                            meta.env_vars = parsed["env_vars"]
        except requests.RequestException as e:
            warn(f"AI 分析请求失败: {e}，使用简单分析结果")
        except Exception as e:
            warn(f"AI 分析失败: {e}，使用简单分析结果")

        return meta

    # ----------------------------------------------------------
    # 2. 下载 skills
    # ----------------------------------------------------------

    def download_skills(self, meta: PluginMeta, selected: list[str] | None = None) -> list[tuple[str, Path]]:
        """下载/安装 skills 到 config/skills/。

        返回 [(skill_name, skill_dir_path), ...] 成功安装的 skill 列表。
        """
        from . import skills as skills_mod

        results: list[tuple[str, Path]] = []
        target_skills = selected or [s.name for s in meta.skills]

        for skill_name in target_skills:
            if not skill_name:
                continue
            # 检查是否已存在
            existing = self._find_skill_dir(skill_name)
            if existing:
                results.append((skill_name, existing))
                info(f"  [~] skill 已存在: {skill_name}")
                continue

            # 构建 skill 配置
            skill_info = next((s for s in meta.skills if s.name == skill_name), None)
            skill_config: dict = {"name": skill_name}
            if skill_info and skill_info.source:
                skill_config["source"] = skill_info.source

            # 尝试安装
            try:
                ok = skills_mod.install_skill(skill_config, self.project_root)
                if ok:
                    installed = self._find_skill_dir(skill_name)
                    if installed:
                        results.append((skill_name, installed))
                        info(f"  [OK] skill 安装成功: {skill_name}")
                    else:
                        warn(f"  [!] skill 安装完成但目录未找到: {skill_name}")
                else:
                    warn(f"  [!] skill 安装失败: {skill_name}")
            except Exception as e:
                warn(f"  [!] skill 安装异常: {skill_name}: {e}")

        return results

    # ----------------------------------------------------------
    # 3. 生成 plugin.yaml 配置
    # ----------------------------------------------------------

    def generate_yaml(
        self,
        meta: PluginMeta,
        name: str | None = None,
        version: str | None = None,
        mcp_servers: dict | None = None,
        env_vars: dict | None = None,
        skills: list[dict] | None = None,
        description: str | None = None,
        author: str | None = None,
    ) -> dict:
        """生成 plugin.yaml 配置字典（对齐 plugin.schema.yaml）。"""
        cfg: dict[str, Any] = {
            "name": sanitize_name(name or meta.name),
            "version": (version or meta.version).strip() or "1.0.0",
            "description": truncate_description(description or meta.description),
            "author": author or meta.author or "AgentBuddy",
            "defaultEnabled": True,
        }

        if meta.license:
            cfg["license"] = meta.license
        if meta.homepage:
            cfg["homepage"] = meta.homepage
        if meta.repository:
            cfg["repository"] = {"type": "git", "url": meta.repository}
        if meta.tags:
            cfg["keywords"] = meta.tags

        # MCP servers
        servers = mcp_servers if mcp_servers is not None else meta.mcp_servers
        if servers:
            cfg["mcpServers"] = servers

        # Skills
        if skills is not None:
            cfg["skills"] = skills
        elif meta.skills:
            cfg["skills"] = [
                {"name": s.name, "description": s.description}
                for s in meta.skills if s.name
            ]

        # 环境变量
        vars_decl = env_vars if env_vars is not None else meta.env_vars
        if vars_decl:
            cfg["envVars"] = vars_decl

        return cfg

    # ----------------------------------------------------------
    # 4. 打包 zip
    # ----------------------------------------------------------

    def package(
        self,
        cfg: dict,
        skill_dirs: list[tuple[str, Path]] | None = None,
        mode: str = "inline",
        output_dir: Path | None = None,
    ) -> Path:
        """将插件配置 + skills 打包为 zip。

        mode="inline": MCP servers + envVars 内联在 plugin.yaml
        mode="split":  拆分为 plugin.yaml + mcp.yaml + keys.yaml
        """
        if mode not in ("inline", "split"):
            raise ValueError(f"不支持的打包模式: {mode}")

        plugin_name = cfg.get("name", "plugin")
        safe_name = "".join(c for c in plugin_name if c.isalnum() or c in ("-", "_"))
        if not safe_name.lower().endswith("-plugin"):
            zip_name = f"{safe_name}-plugin.zip"
        else:
            zip_name = f"{safe_name}.zip"

        out_dir = output_dir or Path.cwd()
        out_dir.mkdir(parents=True, exist_ok=True)
        zip_path = out_dir / zip_name

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            if mode == "inline":
                # 内联模式：一个 plugin.yaml 包含全部
                yaml_str = yaml.dump(cfg, allow_unicode=True,
                                     default_flow_style=False, sort_keys=False)
                fname = f"{safe_name}.plugin.yaml"
                zf.writestr(fname, yaml_str)
            else:
                # 拆分模式：plugin.yaml + mcp.yaml + keys.yaml
                split_cfg = copy.deepcopy(cfg)
                mcp_servers = split_cfg.pop("mcpServers", None)
                env_vars = split_cfg.pop("envVars", None)

                if mcp_servers:
                    split_cfg["mcp_file"] = "mcp.yaml"
                    split_cfg["mcp_servers_ref"] = list(mcp_servers.keys())
                    mcp_yaml = yaml.dump({"mcpServers": mcp_servers},
                                         allow_unicode=True, default_flow_style=False,
                                         sort_keys=False)
                    zf.writestr("mcp.yaml", mcp_yaml)

                if env_vars:
                    split_cfg["keys_file"] = "keys.yaml"
                    keys_data = {
                        "mcp": {
                            k: {"value": "", "description": v.get("description", "")}
                            for k, v in env_vars.items()
                        }
                    }
                    keys_yaml = yaml.dump(keys_data, allow_unicode=True,
                                          default_flow_style=False, sort_keys=False)
                    zf.writestr("keys.yaml", keys_yaml)

                yaml_str = yaml.dump(split_cfg, allow_unicode=True,
                                     default_flow_style=False, sort_keys=False)
                fname = f"{safe_name}.plugin.yaml"
                zf.writestr(fname, yaml_str)

            # 打包 skill 目录
            if skill_dirs:
                for skill_name, skill_dir in skill_dirs:
                    if not skill_dir.exists():
                        warn(f"  skill 目录不存在: {skill_dir}")
                        continue
                    count = _add_dir_to_zip(zf, skill_dir, f"skills/{skill_name}")
                    info(f"  [OK] skill 打包: {skill_name} ({count} files)")

        buf.seek(0)
        zip_path.write_bytes(buf.read())
        return zip_path

    # ----------------------------------------------------------
    # 5. 发布到市场
    # ----------------------------------------------------------

    def publish(
        self,
        zip_path: Path,
        server_url: str,
        token: str,
        tags: list[str] | None = None,
        scope: str = "public",
        team_id: int | None = None,
    ) -> dict:
        """发布 zip 到市场。"""
        import requests

        url = f"{server_url.rstrip('/')}/api/marketplace/publish"
        headers = {"Authorization": f"Bearer {token}"}
        files = {"file": (zip_path.name, open(zip_path, "rb"), "application/zip")}
        data = {
            "tags": json.dumps(tags or []),
            "scope": scope,
        }
        if scope == "team" and team_id:
            data["team_id"] = str(team_id)

        resp = requests.post(url, files=files, data=data, headers=headers, timeout=30)
        result = resp.json()
        if not result.get("ok"):
            raise RuntimeError(f"发布失败: {result.get('error', resp.status_code)}")
        return result.get("data", {})

    # ----------------------------------------------------------
    # 辅助方法
    # ----------------------------------------------------------

    def _find_skill_dir(self, skill_name: str) -> Path | None:
        """在三个 skill 目录中查找已存在的 skill。"""
        for base in self.SKILL_DIRS:
            full = self.project_root / base / skill_name
            if full.is_dir() and (full / "SKILL.md").exists():
                return full
        return None


# ============================================================
# 模块级辅助函数
# ============================================================

def _is_local_path(s: str) -> bool:
    return (s.startswith("./") or s.startswith("/") or s.startswith("~/")
            or (Path(s).exists() and not _is_url(s)))


def _is_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


def _is_github_shorthand(s: str) -> bool:
    return bool(re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", s)) and "/" in s


def _is_github_url(s: str) -> bool:
    return "github.com/" in s and _is_url(s)


def _normalize_github(source: str) -> str | None:
    """将各种 GitHub 来源格式统一为 owner/repo。"""
    if _is_github_shorthand(source):
        return source
    if _is_github_url(source):
        parsed = urlparse(source)
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 2:
            repo = parts[1].removesuffix(".git")
            return f"{parts[0]}/{repo}"
    return None


def _github_headers() -> dict:
    import os
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _raise_if_rate_limited(resp, where: str) -> None:
    """GitHub 匿名限流（60 次/小时/IP）时给出明确错误，而不是静默返回空数据。

    限流表现：HTTP 403 + X-RateLimit-Remaining: 0。静默吞掉会导致分析返回
    空 skills/mcpServers、构建莫名报错，且难以定位。
    """
    if resp.status_code == 403 and resp.headers.get("X-RateLimit-Remaining") == "0":
        raise ValueError(
            f"GitHub API 限流（{where}）：匿名额度 60 次/小时已用完，"
            f"请整点重置后重试，或设置 GITHUB_TOKEN 环境变量（5000 次/小时）"
        )


def _extract_meta_from_tree(
    meta: PluginMeta, tree: list[dict], api_base: str, owner_repo: str
) -> PluginMeta:
    """从 GitHub 文件树中提取 skills、MCP 配置等。"""
    import requests

    skill_paths: list[str] = []
    mcp_json_paths: list[str] = []
    plugin_json_paths: list[str] = []
    skill_md_paths: list[str] = []

    for item in tree:
        p = item.get("path", "")
        if not p or item.get("type") != "blob":
            continue
        if p.endswith("SKILL.md"):
            skill_md_paths.append(p)
        if p.endswith(".mcp.json"):
            mcp_json_paths.append(p)
        if p.endswith("plugin.json") and ".claude-plugin" in p:
            plugin_json_paths.append(p)

    # 提取 MCP servers（从 .mcp.json 文件）
    for mcp_path in mcp_json_paths:
        try:
            raw_url = f"https://raw.githubusercontent.com/{owner_repo}/main/{mcp_path}"
            resp = requests.get(raw_url, headers=_github_headers(), timeout=15)
            if resp.ok:
                data = resp.json()
                servers = data.get("mcpServers", {})
                for name, config in servers.items():
                    meta.mcp_servers[name] = config
        except Exception:
            pass

    # 提取 plugin 元数据（从 .claude-plugin/plugin.json）
    for pjp in plugin_json_paths:
        try:
            raw_url = f"https://raw.githubusercontent.com/{owner_repo}/main/{pjp}"
            resp = requests.get(raw_url, headers=_github_headers(), timeout=15)
            if resp.ok:
                data = resp.json()
                if data.get("name"):
                    meta.name = data["name"]
                if data.get("version"):
                    meta.version = str(data["version"])
                if data.get("description"):
                    meta.description = data["description"]
                if data.get("author"):
                    meta.author = data["author"] if isinstance(data["author"], str) else data["author"].get("name", "")
                # 合并 MCP servers
                for name, config in data.get("mcpServers", {}).items():
                    if name not in meta.mcp_servers:
                        meta.mcp_servers[name] = config
                break
        except Exception:
            pass

    # 提取 skills（SKILL.md frontmatter 的 name 为权威名，路径推导仅兜底）
    seen_skills: set[str] = set()
    for smd in skill_md_paths:
        # 尝试读取 SKILL.md 内容获取权威 name + description
        skill_name, desc = "", ""
        try:
            raw_url = f"https://raw.githubusercontent.com/{owner_repo}/main/{smd}"
            resp = requests.get(raw_url, headers=_github_headers(), timeout=15)
            if resp.ok:
                skill_name = _parse_skill_name_text(resp.text)
                desc = _parse_skill_description_text(resp.text)
        except Exception:
            pass

        # 兜底：从路径推导。
        # 布局一: src/capabilities/api/skill/SKILL.md → 父目录就叫 skill，取祖父（capability 名）
        # 布局二: skills/<name>/SKILL.md → 取直接父目录
        if not skill_name:
            parts = smd.split("/")
            dirs = parts[:-1] if parts and parts[-1] == "SKILL.md" else parts
            if dirs and dirs[-1].lower() in ("skill", "skills") and len(dirs) >= 2:
                skill_name = dirs[-2]
            elif dirs:
                skill_name = dirs[-1]

        if skill_name and skill_name.lower() not in ("skill", "skills", "src", "capabilities") \
                and skill_name not in seen_skills:
            seen_skills.add(skill_name)
            meta.skills.append(SkillInfo(
                name=skill_name,
                description=desc,
                source=f"{owner_repo}",
            ))

    return meta


def _parse_skill_description(skill_md_path: Path) -> str:
    """从 SKILL.md 的 YAML frontmatter 提取 description。"""
    try:
        return _parse_skill_description_text(skill_md_path.read_text(encoding="utf-8"))
    except Exception:
        return ""


def _frontmatter_line(fm_text: str, key: str) -> str:
    """yaml 解析失败时的兜底：按行取 frontmatter 顶层 `key: value`。"""
    m = re.search(rf"^{re.escape(key)}:\s*(.+)$", fm_text, re.M)
    if not m:
        return ""
    return m.group(1).strip().strip('"').strip("'")


def _parse_skill_name_text(text: str) -> str:
    """从 SKILL.md 的 YAML frontmatter 提取权威 skill name。"""
    match = re.search(r"^---\s*\n(.*?)\n---", text, re.S)
    if match:
        fm_text = match.group(1)
        try:
            fm = yaml.safe_load(fm_text)
            if isinstance(fm, dict) and fm.get("name"):
                name = fm["name"]
                return name.strip().strip('"').strip("'") if isinstance(name, str) else str(name)
        except Exception:
            # 未加引号的 plain scalar 含 ": " 等非法字符时 yaml 会失败，降级逐行解析
            return _frontmatter_line(fm_text, "name")
    return ""


def _parse_skill_description_text(text: str) -> str:
    """从 SKILL.md 文本提取 description。"""
    # YAML frontmatter
    match = re.search(r"^---\s*\n(.*?)\n---", text, re.S)
    if match:
        fm_text = match.group(1)
        try:
            fm = yaml.safe_load(fm_text)
            if isinstance(fm, dict) and fm.get("description"):
                desc = fm["description"]
                return desc.strip().strip('"').strip("'") if isinstance(desc, str) else str(desc)
        except Exception:
            return _frontmatter_line(fm_text, "description")
    # fallback: 第一行非标题文本
    for line in text.split("\n"):
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("---"):
            return line[:200]
    return ""


def _add_dir_to_zip(zf: zipfile.ZipFile, src_dir: Path, arc_prefix: str) -> int:
    """将目录递归写入 zip，跳过 .git。"""
    count = 0
    for f in src_dir.rglob("*"):
        if not f.is_file():
            continue
        if ".git" in f.parts:
            continue
        rel = f.relative_to(src_dir)
        arc = str(Path(arc_prefix) / rel)
        zf.write(f, arcname=arc)
        count += 1
    return count


def _strip_html(text: str) -> str:
    """简单 HTML 标签清理。"""
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.S | re.I)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _slugify(s: str) -> str:
    """转 kebab-case（/、_、空格都变 -，其他非 [a-z0-9-] 字符移除）。"""
    s = (s or "").lower()
    s = re.sub(r"[/\s_]+", "-", s)
    s = re.sub(r"[^a-z0-9-]", "", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "plugin"


def _extract_yaml_from_text(text: str) -> str:
    """从 LLM 输出文本中提取 YAML 配置。

    与 server/ai_generator/generator.py 的 _extract_yaml 保持一致行为。
    """
    # 1. 优先提取 ```yaml ... ``` 代码块
    match = re.search(r'```ya?ml?\n([\s\S]*?)```', text)
    if match:
        return match.group(1).strip()
    # 2. 找 name: 开头的 YAML
    lines = text.split("\n")
    filtered = [l for l in lines if not l.startswith("[") and not l.startswith("#")]
    for i, line in enumerate(filtered):
        if line.strip().startswith("name:"):
            end = len(filtered)
            for j in range(i + 1, len(filtered)):
                trimmed = filtered[j].strip()
                if trimmed and not filtered[j].startswith(" ") and not filtered[j].startswith("\t") and not filtered[j].startswith("-"):
                    if not re.match(r'^[a-zA-Z_]+:', trimmed):
                        end = j
                        break
            return "\n".join(filtered[i:end]).strip()
    return ""


# ============================================================
# CLI 辅助函数：解析 --mcp / --env 参数
# ============================================================

def parse_mcp_arg(raw: str) -> tuple[str, dict]:
    """解析 --mcp 参数。

    格式: 名称:command:arg1:arg2:...
    返回: (server_name, {command, args})

    示例:
      'qwen-core:uvx:--from:qwen-mm-plugins[core]:qwen-mm-plugins-core'
      → ('qwen-core', {'command': 'uvx', 'args': ['--from', 'qwen-mm-plugins[core]', 'qwen-mm-plugins-core']})
    """
    parts = raw.split(":")
    if len(parts) < 2:
        raise ValueError(f"--mcp 格式错误: {raw}（至少需要 名称:command）")
    name = parts[0]
    command = parts[1]
    args = parts[2:] if len(parts) > 2 else []
    return name, {"command": command, "args": args, "disabled": False}


def parse_env_arg(raw: str) -> tuple[str, dict]:
    """解析 --env 参数。

    格式: KEY:description:default:required
    返回: (key, {description, default, required})

    示例:
      'DASHSCOPE_API_KEY:阿里百炼Key::false'
      → ('DASHSCOPE_API_KEY', {'description': '阿里百炼Key', 'default': '', 'required': False})
    """
    parts = raw.split(":")
    if len(parts) < 2:
        raise ValueError(f"--env 格式错误: {raw}（至少需要 KEY:description）")
    key = parts[0]
    description = parts[1]
    default = parts[2] if len(parts) > 2 else ""
    required = parts[3].lower() in ("true", "1", "yes") if len(parts) > 3 else False
    return key, {"description": description, "default": default, "required": required}
