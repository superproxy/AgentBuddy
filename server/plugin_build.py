"""服务端插件智能生成、构建与直连发布能力。

服务端不依赖 agentctl。桌面端只负责本地资源组装和调用服务端 API。
"""
from __future__ import annotations

import html
import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

SERVER_DIR = Path(__file__).resolve().parent
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 500


@dataclass
class SkillInfo:
    name: str
    description: str = ""
    source: str = ""
    version: str = "1.0.0"
    requires_key: bool = False
    body: str = ""  # 技能操作说明（生成 skills/<name>/SKILL.md 正文）


@dataclass
class PluginMeta:
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    author: str = "AgentBuddy"
    license: str = ""
    homepage: str = ""
    repository: str = ""
    skills: list[SkillInfo] = field(default_factory=list)
    mcp_servers: dict[str, dict] = field(default_factory=dict)
    env_vars: dict[str, dict] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    source_type: str = ""
    source_url: str = ""


def sanitize_name(raw: str) -> str:
    name = _slugify(str(raw or "").strip())[:MAX_NAME_LENGTH].strip("-")
    return name or "plugin"


def truncate_description(raw: str, max_len: int = MAX_DESCRIPTION_LENGTH) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(raw or ""))
    text = re.sub(r"\s+", " ", text.strip())
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    for sep in ("。", "！", "？", ".", "!", "?"):
        idx = cut.rfind(sep)
        if idx >= max_len // 2:
            return cut[: idx + 1].strip()
    idx = cut.rfind(" ")
    if idx > 0:
        cut = cut[:idx]
    cut = cut.strip()
    return cut if len(cut) <= max_len else cut[: max_len - 1].rstrip() + "…"


def meta_to_response(meta: PluginMeta) -> dict[str, Any]:
    return {
        "name": sanitize_name(meta.name),
        "version": meta.version,
        "description": truncate_description(meta.description),
        "author": meta.author,
        "license": meta.license,
        "homepage": meta.homepage,
        "repository": meta.repository,
        "source_type": meta.source_type,
        "source_url": meta.source_url,
        "tags": meta.tags,
        "skills": [
            {
                "name": s.name,
                "description": s.description,
                "source": s.source,
                "version": s.version,
                "requires_key": s.requires_key,
            }
            for s in meta.skills
        ],
        "mcpServers": meta.mcp_servers,
        "envVars": meta.env_vars,
    }


def meta_from_config(data: dict, source_type: str = "", source_url: str = "") -> PluginMeta:
    if not isinstance(data, dict):
        raise ValueError("plugin.yaml 必须是对象")

    repo = data.get("repository", "")
    if isinstance(repo, dict):
        repo = repo.get("url", "") or ""
    elif not isinstance(repo, str):
        repo = ""

    tags = data.get("keywords", data.get("tags", []))
    if not isinstance(tags, list):
        tags = []

    meta = PluginMeta(
        name=str(data.get("name") or "plugin"),
        version=str(data.get("version") or "1.0.0"),
        description=str(data.get("description") or ""),
        author=str(data.get("author") or "AgentBuddy"),
        license=str(data.get("license") or ""),
        homepage=str(data.get("homepage") or ""),
        repository=repo,
        mcp_servers=data.get("mcpServers") if isinstance(data.get("mcpServers"), dict) else {},
        env_vars=data.get("envVars") if isinstance(data.get("envVars"), dict) else {},
        tags=[str(t) for t in tags if t],
        source_type=source_type,
        source_url=source_url,
    )

    for item in data.get("skills", []) or []:
        if isinstance(item, dict):
            name = item.get("name") or item.get("skill") or ""
            if not name:
                continue
            meta.skills.append(SkillInfo(
                name=str(name),
                description=str(item.get("description") or ""),
                source=str(item.get("source") or item.get("url") or ""),
                version=str(item.get("version") or "1.0.0"),
                requires_key=bool(item.get("requires_key") or item.get("requiresKey")),
                body=str(item.get("body") or ""),
            ))
        elif isinstance(item, str) and item.strip():
            meta.skills.append(SkillInfo(name=item.strip()))
    return meta


def analyze_source(
    project_root: Path,
    source: str,
    ai: bool = False,
    llm_config: dict[str, Any] | None = None,
) -> PluginMeta:
    source = (source or "").strip()
    if not source:
        raise ValueError("来源不能为空")
    if _is_github_shorthand(source) or _is_github_url(source):
        base_meta = analyze_github(source)
    elif _is_url(source):
        base_meta = analyze_url_simple(source)
    else:
        raise ValueError("服务端只支持 GitHub 仓库或 URL 来源；本地目录请走本地组装")
    return analyze_with_ai(project_root, source, base_meta, llm_config=llm_config) if ai else base_meta


def analyze_github(source: str) -> PluginMeta:
    owner_repo = _normalize_github(source)
    if not owner_repo:
        raise ValueError(f"无法解析 GitHub 仓库: {source}")
    repo_url = f"https://github.com/{owner_repo}"
    meta = PluginMeta(
        name=owner_repo.split("/")[-1],
        description="",
        homepage=repo_url,
        repository=repo_url,
        source_type="github",
        source_url=repo_url,
    )
    default_branch = "main"
    data = _http_get_json(f"https://api.github.com/repos/{owner_repo}", timeout=15)
    if isinstance(data, dict):
        meta.description = str(data.get("description") or "")
        meta.license = str((data.get("license") or {}).get("spdx_id") or "")
        meta.homepage = str(data.get("homepage") or "") or repo_url
        default_branch = str(data.get("default_branch") or default_branch)
    meta.skills = discover_github_skills(owner_repo, default_branch=default_branch, repo_description=meta.description)
    return meta


def discover_github_skills(owner_repo: str, default_branch: str = "main", repo_description: str = "") -> list[SkillInfo]:
    """扫描 GitHub 仓库内所有 SKILL.md，返回权威 skill 元数据。"""
    skills: list[SkillInfo] = []
    seen: set[str] = set()
    tree = _github_tree(owner_repo, default_branch)
    if not tree and default_branch != "master":
        tree = _github_tree(owner_repo, "master")
    for item in tree:
        path = str(item.get("path") or "")
        if not path or path.split("/")[-1].lower() != "skill.md":
            continue
        text = ""
        branch = default_branch or "main"
        raw_url = f"https://raw.githubusercontent.com/{owner_repo}/{branch}/{path}"
        text = _http_get_text(raw_url, timeout=15)
        if not text and branch != "master":
            raw_url = f"https://raw.githubusercontent.com/{owner_repo}/master/{path}"
            text = _http_get_text(raw_url, timeout=15)
        frontmatter = _parse_skill_frontmatter(text)
        name = str(frontmatter.get("name") or "").strip() or _infer_skill_name_from_path(path)
        name = sanitize_name(name)
        if not name or name in seen:
            continue
        seen.add(name)
        description = str(frontmatter.get("description") or "").strip() or repo_description
        version = str(frontmatter.get("version") or "1.0.0").strip() or "1.0.0"
        skills.append(SkillInfo(
            name=name,
            version=version,
            description=truncate_description(description, 180),
            source=f"{owner_repo}@{name}",
        ))
    return skills


def _github_tree(owner_repo: str, branch: str) -> list[dict]:
    data = _http_get_json(f"https://api.github.com/repos/{owner_repo}/git/trees/{branch}?recursive=1", timeout=20)
    if not isinstance(data, dict):
        return []
    tree = data.get("tree", [])
    return tree if isinstance(tree, list) else []


def analyze_url_simple(url: str) -> PluginMeta:
    meta = PluginMeta(source_type="url", source_url=url, homepage=url)
    text = _http_get_text(url, timeout=20)
    if _looks_like_wechat_block_page(text):
        mobile_text = _http_get_text(url, timeout=20, headers=_wechat_headers())
        if mobile_text:
            text = mobile_text
    if text:
        wechat_title, wechat_description = _extract_wechat_cgi_data(text)
        title = (
            _extract_meta_content(text, "og:title")
            or _extract_meta_content(text, "twitter:title")
            or wechat_title
            or _extract_js_string(text, "title")
            or _extract_window_assignment(text, "msg_title")
        )
        if not title:
            title_match = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
            title = _strip_html(title_match.group(1)) if title_match else ""
        title = _decode_web_text(title)
        if title:
            meta.name = _slugify(title[:60])

        description = (
            _extract_meta_content(text, "og:description")
            or _extract_meta_content(text, "twitter:description")
            or _extract_meta_content(text, "description")
            or wechat_description
            or _extract_js_string(text, "desc")
            or _strip_html(text)
        )
        meta.description = truncate_description(_decode_web_text(description))
        repos = _extract_github_repos(text)
        if repos:
            meta.repository = f"https://github.com/{repos[0]}"
            meta.skills = _discover_skills_from_repos(repos, meta.description)
    if not meta.name:
        host = urlparse(url).netloc.split(":", 1)[0]
        meta.name = _slugify(host or "url-plugin")
    return meta


def analyze_with_ai(
    project_root: Path,
    source: str,
    base_meta: PluginMeta,
    llm_config: dict[str, Any] | None = None,
) -> PluginMeta:
    prompt = (
        "请根据以下来源生成完整 plugin.yaml。\n"
        "你是在 AgentBuddy 服务端 crawler 中分析文章/网页并生成可安装插件。\n"
        "如果基础分析已经发现真实 skills，请保留它们；如果没有发现 SKILL.md 或 GitHub 仓库链接，"
        "可以根据文章标题和摘要生成候选 skills。\n"
        "要求：\n"
        "- name 使用 kebab-case，description 不超过 500 字。\n"
        "- skills 至少 1 个，最多 10 个；每个 skill 必须有 name、description、version。\n"
        "- 对根据文章摘要推断出的 skill，source 写 ai-extracted:<来源 URL>。\n"
        "- 不要编造 GitHub repository URL；没有可靠仓库时 repository 留空。\n"
        "- 只输出 plugin.yaml，不要解释。\n\n"
        f"来源: {source}\n"
        f"基础分析名称: {base_meta.name}\n"
        f"基础描述摘要: {base_meta.description[:2000]}\n"
        f"已发现 skills: {[s.name for s in base_meta.skills]}\n"
    )

    if llm_config:
        ai_text = generate_plugin_with_direct_llm(prompt, llm_config)
    else:
        from ai_generator.generator import generate_plugin

        chunks: list[str] = []
        errors: list[str] = []
        for chunk in generate_plugin(prompt, project_root):
            if chunk.startswith("[ERROR]"):
                errors.append(chunk.replace("[ERROR]", "", 1).strip())
            if chunk != "[DONE]":
                chunks.append(chunk)
        if errors:
            raise ValueError(errors[-1] or "AI 生成失败")
        ai_text = "\n".join(chunks)

    yaml_text = extract_yaml_from_ai(ai_text)
    if not yaml_text:
        raise ValueError("AI 未生成有效 plugin.yaml")
    meta = meta_from_config(yaml.safe_load(yaml_text), base_meta.source_type, source)
    if not meta.description:
        meta.description = base_meta.description
    if not meta.homepage:
        meta.homepage = base_meta.homepage
    if not meta.repository:
        meta.repository = base_meta.repository
    return meta


def generate_plugin_with_direct_llm(prompt: str, llm_config: dict[str, Any]) -> str:
    """crawler 直配 LLM 调用：不读 config/llm/llm.yaml，直接用源的 base_url/api_key/model。

    llm_config 约定（来自 plugin-sources.yaml 的 source.llm）:
      - base_url / url: OpenAI-compatible 接口地址
      - api_key / key:  密钥
      - model:          模型名
    """
    base_url = str(llm_config.get("base_url") or llm_config.get("url") or "").strip()
    api_key = str(llm_config.get("api_key") or llm_config.get("key") or "").strip()
    model = str(llm_config.get("model") or "").strip()
    if not base_url or not api_key or not model:
        raise ValueError("crawler AI 需要在源配置中设置 llm.base_url、llm.api_key、llm.model")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ValueError("openai SDK 未安装，请先安装 openai") from exc

    system_prompt = (
        "你是 AgentBuddy 服务端 crawler 的插件分析器。"
        "只输出可被 yaml.safe_load 解析的 plugin.yaml，不要输出解释、Markdown 或代码围栏。"
    )
    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )
    return response.choices[0].message.content or ""


def apply_config_override(meta: PluginMeta, config_yaml: str) -> PluginMeta:
    if not config_yaml:
        return meta
    override = yaml.safe_load(config_yaml)
    generated = meta_from_config(override, meta.source_type, meta.source_url)
    meta.name = generated.name or meta.name
    meta.version = generated.version or meta.version
    meta.description = generated.description or meta.description
    meta.author = generated.author or meta.author
    meta.license = generated.license or meta.license
    meta.homepage = generated.homepage or meta.homepage
    meta.repository = generated.repository or meta.repository
    meta.tags = generated.tags or meta.tags
    if generated.skills:
        meta.skills = generated.skills
    if generated.mcp_servers:
        meta.mcp_servers = generated.mcp_servers
    if generated.env_vars:
        meta.env_vars = generated.env_vars
    return meta


def build_plugin(project_root: Path, data: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    source = str(data.get("source") or "").strip()
    config_yaml = data.get("config_yaml") if isinstance(data.get("config_yaml"), str) else ""
    if not source and not config_yaml:
        raise ValueError("来源不能为空")

    if source:
        meta = analyze_source(
            project_root,
            source,
            ai=bool(data.get("ai", False)),
            llm_config=data.get("llm") if isinstance(data.get("llm"), dict) else None,
        )
    else:
        meta = meta_from_config(yaml.safe_load(config_yaml), source_type="generated", source_url="")
    if config_yaml:
        meta = apply_config_override(meta, config_yaml)

    if data.get("name"):
        meta.name = str(data["name"])
    if data.get("version"):
        meta.version = str(data["version"])
    if data.get("description"):
        meta.description = str(data["description"])
    meta.name = sanitize_name(meta.name)
    meta.description = truncate_description(meta.description)

    selected = data.get("skills")
    if selected and isinstance(selected, list):
        selected_set = {str(x) for x in selected if x}
        meta.skills = [s for s in meta.skills if s.name in selected_set]

    cfg = generate_config(meta)
    if isinstance(data.get("mcpServers"), dict):
        cfg["mcpServers"] = data["mcpServers"]
    if isinstance(data.get("envVars"), dict):
        cfg["envVars"] = data["envVars"]

    output_dir = SERVER_DIR / "data" / "plugin-builds"
    zip_path = package_config(cfg, mode=str(data.get("mode") or "inline"), output_dir=output_dir)
    return zip_path, cfg


def generate_config(meta: PluginMeta) -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "name": sanitize_name(meta.name),
        "version": str(meta.version or "1.0.0"),
        "description": truncate_description(meta.description),
        "author": meta.author or "AgentBuddy",
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
    if meta.mcp_servers:
        cfg["mcpServers"] = meta.mcp_servers
    if meta.skills:
        cfg["skills"] = [
            {
                "name": s.name,
                "description": s.description,
                "version": s.version,
                **({"source": s.source} if s.source else {}),
                **({"body": s.body} if s.body else {}),
            }
            for s in meta.skills if s.name
        ]
    if meta.env_vars:
        cfg["envVars"] = meta.env_vars
    return cfg


def package_config(cfg: dict[str, Any], mode: str, output_dir: Path) -> Path:
    if mode not in ("inline", "split"):
        raise ValueError(f"不支持的打包模式: {mode}")
    plugin_name = sanitize_name(str(cfg.get("name") or "plugin"))
    zip_name = f"{plugin_name}-plugin.zip" if not plugin_name.endswith("-plugin") else f"{plugin_name}.zip"
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / zip_name

    payload = yaml.dump(cfg, allow_unicode=True, default_flow_style=False, sort_keys=False)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if mode == "inline":
            zf.writestr(f"{plugin_name}.plugin.yaml", payload)
        else:
            split_cfg = dict(cfg)
            mcp_servers = split_cfg.pop("mcpServers", None)
            env_vars = split_cfg.pop("envVars", None)
            if mcp_servers:
                split_cfg["mcp_file"] = "mcp.yaml"
                split_cfg["mcp_servers_ref"] = list(mcp_servers.keys())
                zf.writestr("mcp.yaml", yaml.dump({"mcpServers": mcp_servers}, allow_unicode=True, sort_keys=False))
            if env_vars:
                split_cfg["keys_file"] = "keys.yaml"
                zf.writestr("keys.yaml", yaml.dump({"mcp": env_vars}, allow_unicode=True, sort_keys=False))
            zf.writestr("plugin.yaml", yaml.dump(split_cfg, allow_unicode=True, sort_keys=False))

        # 将含 body 的技能生成 skills/<name>/SKILL.md 并打包，保证可安装为真实 skill
        for skill in cfg.get("skills", []) or []:
            name = str(skill.get("name") or "").strip()
            body = str(skill.get("body") or "").strip()
            if not name or not body:
                continue
            desc = str(skill.get("description") or "").strip()
            source = str(skill.get("source") or "").strip()
            lines = [f"# {name}"]
            if desc:
                lines += ["", desc]
            if source:
                lines += ["", f"> 来源：{source}"]
            lines += ["", body]
            zf.writestr(f"skills/{name}/SKILL.md", "\n".join(lines))
    return zip_path


def ensure_service_user(username: str = "service") -> int:
    from auth import models as m
    conn = m.get_db()
    row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if row:
        uid = row["id"]
        conn.close()
        return uid
    import bcrypt
    import secrets
    hashed = bcrypt.hashpw(secrets.token_hex(16).encode(), bcrypt.gensalt()).decode()
    cur = conn.execute(
        "INSERT INTO users (username, password, email, role, created_at) VALUES (?, ?, ?, ?, ?)",
        (username, hashed, "", "member", m.now_iso()),
    )
    conn.commit()
    uid = cur.lastrowid
    conn.close()
    return uid


def publish_local(zip_path: Path, marketplace_dir: Path, tags: list | None = None,
                  scope: str = "public", team_id: int | None = None,
                  user: dict | None = None, service_username: str = "service") -> dict[str, Any]:
    from auth import models as m

    packages_dir = marketplace_dir / "packages"
    plugin_name = zip_path.stem
    version = "1.0.0"
    description = ""
    author = user.get("username") if user else service_username

    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            if name.endswith((".plugin.yaml", ".plugin.yml", "plugin.yaml", "plugin.yml")):
                try:
                    data = yaml.safe_load(zf.read(name).decode("utf-8"))
                    if isinstance(data, dict):
                        plugin_name = data.get("name", Path(name).stem)
                        version = str(data.get("version", "1.0.0")).strip() or "1.0.0"
                        description = str(data.get("description") or "").strip()
                        yaml_author = str(data.get("author") or "").strip()
                        if yaml_author:
                            author = yaml_author
                except Exception:
                    pass
                break

    safe_name = "".join(c for c in str(plugin_name) if c.isalnum() or c in ("-", "_"))
    pkg_name = f"{safe_name or 'plugin'}-{version}.zip"
    packages_dir.mkdir(parents=True, exist_ok=True)
    pkg_path = packages_dir / pkg_name
    pkg_path.write_bytes(zip_path.read_bytes())

    author_id = user.get("id") if user else ensure_service_user(service_username)
    entry = {
        "id": f"{plugin_name}-{version}",
        "name": plugin_name,
        "version": version,
        "description": description[:500],
        "author": author,
        "author_id": author_id,
        "file": f"packages/{pkg_name}",
        "size": pkg_path.stat().st_size,
        "published_at": m.now_iso(),
        "tags": tags if isinstance(tags, list) else [],
        "downloads": 0,
        "likes": 0,
        "scope": scope,
        "team_id": team_id if scope == "team" else None,
    }
    m.plugin_save(entry)
    return entry


def extract_yaml_from_ai(text: str) -> str:
    match = re.search(r"```ya?ml?\n([\s\S]*?)```", text)
    if match:
        return match.group(1).strip()
    lines = text.split("\n")
    filtered = [l for l in lines if not l.startswith("[") and not l.startswith("#")]
    for i, line in enumerate(filtered):
        if line.strip().startswith("name:"):
            end = len(filtered)
            for j in range(i + 1, len(filtered)):
                trimmed = filtered[j].strip()
                if trimmed and not filtered[j].startswith((" ", "\t", "-")):
                    if not re.match(r"^[a-zA-Z_]+:", trimmed):
                        end = j
                        break
            return "\n".join(filtered[i:end]).strip()
    return ""


def _is_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


def _is_github_shorthand(s: str) -> bool:
    return bool(re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", s))


def _is_github_url(s: str) -> bool:
    return "github.com" in s and _normalize_github(s) is not None


def _normalize_github(source: str) -> str | None:
    if _is_github_shorthand(source):
        return source.strip().rstrip("/")
    parsed = urlparse(source)
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if parsed.netloc.lower().endswith("github.com") and len(parts) >= 2:
        return f"{parts[0]}/{parts[1].replace('.git', '')}"
    return None


def _strip_html(text: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.S | re.I)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_meta_content(html: str, name: str) -> str:
    escaped_name = re.escape(name)
    quote = r"[\"']"
    patterns = [
        rf"<meta[^>]+property={quote}{escaped_name}{quote}[^>]+content={quote}([^\"']*){quote}",
        rf"<meta[^>]+name={quote}{escaped_name}{quote}[^>]+content={quote}([^\"']*){quote}",
        rf"<meta[^>]+content={quote}([^\"']*){quote}[^>]+property={quote}{escaped_name}{quote}",
        rf"<meta[^>]+content={quote}([^\"']*){quote}[^>]+name={quote}{escaped_name}{quote}",
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.I | re.S)
        if match:
            return _decode_web_text(match.group(1))
    return ""


def _wechat_headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.50 "
            "NetType/WIFI Language/zh_CN"
        ),
        "Referer": "https://mp.weixin.qq.com/",
    }


def _looks_like_wechat_block_page(text: str) -> bool:
    body = str(text or "")
    markers = (
        "环境异常",
        "完成验证后即可继续访问",
        "微信扫一扫可打开此内容",
        "Scan with Weixin",
        "WeChat verification page",
    )
    return any(marker in body for marker in markers)


def _extract_js_string(text: str, name: str) -> str:
    patterns = [
        rf"(?:var|let|const)\s+{re.escape(name)}\s*=\s*(['\"])((?:\\.|(?!\1).)*)\1",
        rf"(?:window\.)?{re.escape(name)}\s*=\s*(['\"])((?:\\.|(?!\1).)*)\1",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.S)
        if match:
            return _decode_web_text(match.group(2))
    return ""


def _extract_window_assignment(text: str, name: str) -> str:
    pattern = rf"(?:window\.)?{re.escape(name)}\s*=\s*(?:window\.[A-Za-z_][A-Za-z0-9_]*\s*=\s*)?(['\"])((?:\\.|(?!\1).)*)\1"
    match = re.search(pattern, text, re.S)
    if match:
        return _decode_web_text(match.group(2))
    return ""


def _extract_wechat_cgi_data(text: str) -> tuple[str, str]:
    match = re.search(
        r"window\.cgiDataNew\s*=\s*\{[\s\S]*?title:\s*'((?:\\.|[^'])*)'[\s\S]*?desc:\s*'((?:\\.|[^'])*)'",
        text,
        re.S,
    )
    if match:
        return _decode_web_text(match.group(1)), _decode_web_text(match.group(2))
    return "", ""


def _decode_web_text(text: str) -> str:
    if not text:
        return ""
    value = html.unescape(str(text))

    def _replace_hex(match):
        try:
            return bytes([int(match.group(1), 16)]).decode("utf-8", errors="replace")
        except Exception:
            return match.group(0)

    def _replace_unicode(match):
        try:
            return chr(int(match.group(1), 16))
        except Exception:
            return match.group(0)

    value = re.sub(r"\\x([0-9a-fA-F]{2})", _replace_hex, value)
    value = re.sub(r"\\u([0-9a-fA-F]{4})", _replace_unicode, value)
    value = value.replace("\\n", "\n").replace("\\t", "\t").replace("\\'", "'").replace('\\"', '"')
    return _strip_html(value)


def _github_headers() -> dict[str, str]:
    headers = {"User-Agent": "AgentBuddy Server"}
    return headers


def _http_get_text(url: str, timeout: int = 20, headers: dict[str, str] | None = None) -> str:
    request_headers = headers or _github_headers()
    try:
        import requests
        resp = requests.get(url, timeout=timeout, headers=request_headers)
        return resp.text if resp.ok else ""
    except Exception:
        pass
    try:
        from urllib.request import Request, urlopen
        req = Request(url, headers=request_headers)
        with urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")
    except Exception:
        return ""


def _http_get_json(url: str, timeout: int = 20) -> Any:
    text = _http_get_text(url, timeout=timeout)
    if not text:
        return None
    try:
        import json
        return json.loads(text)
    except Exception:
        return None


def _extract_github_repos(text: str) -> list[str]:
    repos: list[str] = []
    seen: set[str] = set()
    for owner, repo in re.findall(r"github\.com[/:]([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", text):
        repo = repo.removesuffix(".git")
        key = f"{owner}/{repo}".strip("/")
        if key not in seen:
            seen.add(key)
            repos.append(key)
    return repos[:20]


def _discover_skills_from_repos(repos: list[str], repo_description: str = "") -> list[SkillInfo]:
    skills: list[SkillInfo] = []
    seen: set[str] = set()
    for repo in repos:
        repo_meta = analyze_github(repo)
        for skill in repo_meta.skills:
            if skill.name in seen:
                continue
            seen.add(skill.name)
            if not skill.description:
                skill.description = repo_meta.description or repo_description
            skills.append(skill)
    return skills


def _parse_skill_frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---"):
        return {}
    match = re.match(r"^---\s*\n([\s\S]*?)\n---", text)
    if not match:
        return {}
    try:
        data = yaml.safe_load(match.group(1)) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        result: dict[str, str] = {}
        for line in match.group(1).splitlines():
            m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.+?)\s*$", line)
            if m:
                result[m.group(1)] = m.group(2).strip().strip('"\'')
        return result


def _infer_skill_name_from_path(path: str) -> str:
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2:
        parent = parts[-2]
        if parent.lower() not in {"skill", "skills", "src", "capabilities"}:
            return parent
    if len(parts) >= 3:
        return parts[-3]
    return Path(path).stem or "skill"


def _slugify(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[/\s_]+", "-", s)
    s = re.sub(r"[^a-z0-9-]", "", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "plugin"
