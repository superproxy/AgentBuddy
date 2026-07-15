"""Skills 市场多源聚合搜索。

数据源：
  - modelscope  ModelScope OpenAPI（国内，与 MCP 共用生态）
  - skillssh    skills.sh（Vercel 官方目录，npx skills add）
  - skillsmp    SkillsMP（大规模 GitHub SKILL.md 索引，匿名可搜）
  - smithery    Smithery Skills（GET /skills，与 MCP 同源平台）
  - clawhub     ClawHub / OpenClaw 技能注册表（向量语义搜索）
  - github      GitHub 仓库搜索（可选 GITHUB_TOKEN 启用 code search）
  - anthropics  anthropics/skills 官方预置库（GitHub Contents）

说明：MCP 市场的 registry / pulsemcp / glama 是 MCP Server 目录，
不可直接复用为 Agent Skills 源；ModelScope 与 Smithery 同时提供 Skills API。

search 并行 fan-out；按 SOURCE_PRIORITY 合并；按 owner/repo@skill 跨源去重。
"""
from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

HTTP_TIMEOUT = 12
USER_AGENT = "AdeBuddy/1.0"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}

MODELSCOPE_SKILLS_API = "https://www.modelscope.cn/openapi/v1/skills"
SKILLS_SH_API = "https://skills.sh/api/search"
SKILLSMP_API = "https://skillsmp.com/api/v1/skills/search"
SMITHERY_SKILLS_API = "https://api.smithery.ai/skills"
CLAWHUB_API = "https://clawhub.ai/api/v1/search"
GITHUB_REPO_API = "https://api.github.com/search/repositories"
GITHUB_CODE_API = "https://api.github.com/search/code"
ANTHROPICS_CONTENTS = "https://api.github.com/repos/anthropics/skills/contents/skills"

SOURCE_PRIORITY = (
    "skillssh", "smithery", "modelscope", "skillsmp",
    "clawhub", "anthropics", "github",
)
SOURCE_LABELS = {
    "skillssh": "skills.sh",
    "smithery": "Smithery",
    "modelscope": "ModelScope",
    "skillsmp": "SkillsMP",
    "clawhub": "ClawHub",
    "anthropics": "Anthropic",
    "github": "GitHub",
}

# anthropics 目录缓存（进程内）
_ANTHROPICS_CACHE: Optional[List[Dict[str, Any]]] = None


def _safe(fn: Callable[[], Any], default: Any) -> Any:
    try:
        return fn()
    except Exception:
        return default


def _item(
    *,
    source: str,
    name: str,
    description: str = "",
    install_command: str = "",
    install_count: int = 0,
    author: str = "",
    license: str = "",
    url: str = "",
    raw: Any = None,
) -> Dict[str, Any]:
    return {
        "source": source,
        "source_label": SOURCE_LABELS.get(source, source),
        "name": name or "",
        "description": description or "",
        "install_command": install_command or "",
        "install_count": install_count or 0,
        "author": author or "",
        "license": license or "",
        "url": url or "",
        "raw": raw,
    }


def _skills_add_cmd(spec: str) -> str:
    spec = (spec or "").strip()
    if not spec:
        return ""
    return f"npx --yes skills add {spec} --copy -y"


def _github_tree_to_spec(url: str, skill_name: str = "") -> str:
    """https://github.com/owner/repo/tree/branch/path/skill -> owner/repo@skill"""
    m = re.match(
        r"https?://github\.com/([^/]+)/([^/]+)(?:/tree/[^/]+(?:/(.+))?)?",
        (url or "").strip(),
    )
    if not m:
        return ""
    owner, repo, path = m.group(1), m.group(2), (m.group(3) or "").strip("/")
    skill = skill_name or (path.split("/")[-1] if path else "")
    if skill and skill != repo:
        return f"{owner}/{repo}@{skill}"
    return f"{owner}/{repo}"


def _dedupe_key(it: Dict[str, Any]) -> str:
    cmd = (it.get("install_command") or "").lower()
    m = re.search(r"skills add\s+([^\s]+)", cmd)
    if m:
        return m.group(1).lower()
    author = (it.get("author") or "").lower()
    name = (it.get("name") or "").lower()
    if author and name:
        return f"{author}/{name}"
    return f"{it.get('source','')}:{name}"


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------

class ModelScopeSkillsClient:
    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        resp = requests.get(
            MODELSCOPE_SKILLS_API,
            params={"page_number": 1, "page_size": min(limit, 50), "search": query},
            timeout=HTTP_TIMEOUT,
            headers={**HEADERS, "Content-Type": "application/json"},
        )
        resp.raise_for_status()
        payload = resp.json()
        data = payload.get("data") or payload
        items = data.get("skills") or data.get("list") or []
        out: List[Dict[str, Any]] = []
        for it in items[:limit]:
            if not isinstance(it, dict):
                continue
            name = it.get("name") or it.get("skill_name") or it.get("display_name") or ""
            cmd = (it.get("install_command") or "").strip()
            if not cmd:
                src_url = it.get("source_url") or ""
                spec = _github_tree_to_spec(src_url, name)
                if not spec:
                    owner = it.get("owner") or it.get("developer") or it.get("author") or ""
                    if owner and name:
                        spec = f"{owner}/{name}" if "/" not in str(owner) else f"{owner}@{name}"
                cmd = _skills_add_cmd(spec) if spec else ""
            elif cmd.startswith("npx") and "--copy" not in cmd:
                cmd = cmd.replace(" -y", "").rstrip() + " --copy -y"
            out.append(_item(
                source="modelscope",
                name=name,
                description=it.get("description") or it.get("chinese_description") or "",
                install_command=cmd,
                install_count=int(it.get("install_count") or it.get("download_count") or 0),
                author=it.get("owner") or it.get("developer") or it.get("author") or "",
                license=it.get("license") or "",
                url=it.get("source_url") or "",
                raw=it,
            ))
        return out


class SkillsShClient:
    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        resp = requests.get(
            SKILLS_SH_API,
            params={"q": query},
            timeout=HTTP_TIMEOUT,
            headers=HEADERS,
        )
        resp.raise_for_status()
        payload = resp.json()
        items = payload.get("skills") or payload.get("data") or []
        if isinstance(items, dict):
            items = list(items.values())
        out: List[Dict[str, Any]] = []
        for it in items[:limit]:
            if not isinstance(it, dict):
                continue
            name = it.get("name") or it.get("skillId") or it.get("title") or ""
            source_repo = (it.get("source") or "").strip()
            skill_id = (it.get("skillId") or name or "").strip()
            if source_repo and skill_id and f"/{skill_id}" not in f"/{source_repo}":
                spec = f"{source_repo}@{skill_id}"
            else:
                spec = source_repo or skill_id
            out.append(_item(
                source="skillssh",
                name=name,
                description=it.get("description") or "",
                install_command=_skills_add_cmd(spec),
                install_count=int(it.get("installs") or it.get("install_count") or 0),
                author=(source_repo.split("/")[0] if "/" in source_repo else source_repo),
                url=f"https://skills.sh/{source_repo}/{skill_id}" if source_repo and skill_id else "",
                raw=it,
            ))
        return out


class SkillsMpClient:
    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        headers = {**HEADERS}
        key = os.environ.get("SKILLSMP_API_KEY", "").strip()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        resp = requests.get(
            SKILLSMP_API,
            params={"q": query, "limit": min(limit, 50), "sortBy": "stars"},
            timeout=HTTP_TIMEOUT,
            headers=headers,
        )
        resp.raise_for_status()
        payload = resp.json()
        data = payload.get("data") or payload
        items = data.get("skills") or []
        out: List[Dict[str, Any]] = []
        for it in items[:limit]:
            if not isinstance(it, dict):
                continue
            name = it.get("name") or ""
            gh = it.get("githubUrl") or it.get("github_url") or ""
            spec = _github_tree_to_spec(gh, name)
            out.append(_item(
                source="skillsmp",
                name=name,
                description=it.get("description") or "",
                install_command=_skills_add_cmd(spec) if spec else _skills_add_cmd(gh),
                install_count=int(it.get("stars") or it.get("install_count") or 0),
                author=it.get("author") or "",
                url=it.get("skillUrl") or gh,
                raw=it,
            ))
        return out


class SmitherySkillsClient:
    """Smithery Platform Skills：GET /skills?q=（与 MCP /servers 同源 API）。

    文档：https://smithery.ai/docs/api-reference/skills/list-or-search-skills
    公开列表可不带 Key；配置 SMITHERY_API_KEY 可提高限额 / 访问私有字段。
    """

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        headers = {**HEADERS}
        key = os.environ.get("SMITHERY_API_KEY", "").strip()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        resp = requests.get(
            SMITHERY_SKILLS_API,
            params={"q": query, "pageSize": min(limit, 100), "page": 1},
            timeout=HTTP_TIMEOUT,
            headers=headers,
        )
        resp.raise_for_status()
        payload = resp.json()
        items = payload.get("skills") or []
        out: List[Dict[str, Any]] = []
        for it in items[:limit]:
            if not isinstance(it, dict):
                continue
            name = it.get("displayName") or it.get("slug") or ""
            ns = it.get("namespace") or ""
            slug = it.get("slug") or ""
            gh = it.get("gitUrl") or ""
            spec = _github_tree_to_spec(gh, slug or name)
            if not spec and ns and slug:
                # 无 gitUrl 时退化为 namespace/slug（部分可经 skills CLI / 手动安装）
                spec = f"{ns}/{slug}"
            url = gh or (f"https://smithery.ai/skills/{ns}/{slug}" if ns and slug else "")
            out.append(_item(
                source="smithery",
                name=name,
                description=it.get("description") or "",
                install_command=_skills_add_cmd(spec) if spec else "",
                install_count=int(
                    it.get("totalActivations")
                    or it.get("externalStars")
                    or 0
                ),
                author=ns,
                url=url,
                raw=it,
            ))
        return out


class ClawHubClient:
    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        resp = requests.get(
            CLAWHUB_API,
            params={"q": query, "limit": min(limit, 40)},
            timeout=HTTP_TIMEOUT,
            headers=HEADERS,
        )
        resp.raise_for_status()
        payload = resp.json()
        items = payload.get("results") or payload.get("skills") or []
        out: List[Dict[str, Any]] = []
        for it in items[:limit]:
            if not isinstance(it, dict):
                continue
            slug = it.get("slug") or it.get("name") or ""
            owner = it.get("ownerHandle") or it.get("owner") or ""
            name = it.get("displayName") or slug
            # ClawHub 安装走 clawhub CLI；同时给出可复制的 slug 引用
            ref = f"@{owner}/{slug}" if owner and slug else slug
            cmd = f"npx -y clawhub@latest install {slug} -y" if slug else ""
            out.append(_item(
                source="clawhub",
                name=name,
                description=it.get("summary") or it.get("description") or "",
                install_command=cmd,
                install_count=0,
                author=owner,
                url=f"https://clawhub.ai/{owner}/{slug}" if owner and slug else "",
                raw={**it, "ref": ref},
            ))
        return out


class GitHubSkillsClient:
    """仓库级发现；有 GITHUB_TOKEN 时额外启用 code search（filename:SKILL.md）。"""

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        token = os.environ.get("GITHUB_TOKEN", "").strip()
        headers = {
            **HEADERS,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        out: List[Dict[str, Any]] = []
        seen = set()

        # 1) code search（需 token）
        if token:
            try:
                resp = requests.get(
                    GITHUB_CODE_API,
                    params={
                        "q": f"{query} filename:SKILL.md",
                        "per_page": min(limit, 30),
                    },
                    timeout=HTTP_TIMEOUT,
                    headers=headers,
                )
                if resp.status_code == 200:
                    for it in (resp.json().get("items") or [])[:limit]:
                        repo = (it.get("repository") or {})
                        full = repo.get("full_name") or ""
                        path = it.get("path") or ""
                        # skills/foo/SKILL.md -> foo
                        parts = path.replace("\\", "/").split("/")
                        skill = ""
                        if len(parts) >= 2 and parts[-1].lower() == "skill.md":
                            skill = parts[-2]
                        name = skill or full.split("/")[-1]
                        spec = f"{full}@{skill}" if full and skill else full
                        key = spec.lower()
                        if not full or key in seen:
                            continue
                        seen.add(key)
                        out.append(_item(
                            source="github",
                            name=name,
                            description=repo.get("description") or path,
                            install_command=_skills_add_cmd(spec),
                            install_count=int(repo.get("stargazers_count") or 0),
                            author=full.split("/")[0] if "/" in full else "",
                            url=it.get("html_url") or repo.get("html_url") or "",
                            raw=it,
                        ))
            except Exception:
                pass

        # 2) 仓库搜索（无需 token，公开限流）
        if len(out) < limit:
            q = (
                f'({query}) (agent-skills OR "claude skills" OR SKILL.md) '
                f'in:name,description,readme'
            )
            resp = requests.get(
                GITHUB_REPO_API,
                params={"q": q, "per_page": min(limit, 20), "sort": "stars"},
                timeout=HTTP_TIMEOUT,
                headers=headers,
            )
            resp.raise_for_status()
            for it in (resp.json().get("items") or []):
                if len(out) >= limit:
                    break
                full = it.get("full_name") or ""
                name = (it.get("name") or "").lower()
                desc = (it.get("description") or "").lower()
                # 过滤明显无关的 awesome 目录站
                blob = f"{name} {desc}"
                if "awesome-" in name and "skill" not in blob:
                    continue
                key = full.lower()
                if not full or key in seen:
                    continue
                seen.add(key)
                out.append(_item(
                    source="github",
                    name=it.get("name") or full.split("/")[-1],
                    description=it.get("description") or "",
                    install_command=_skills_add_cmd(full),
                    install_count=int(it.get("stargazers_count") or 0),
                    author=full.split("/")[0],
                    url=it.get("html_url") or "",
                    raw=it,
                ))
        return out[:limit]


class AnthropicSkillsClient:
    def _list_all(self) -> List[Dict[str, Any]]:
        global _ANTHROPICS_CACHE
        if _ANTHROPICS_CACHE is not None:
            return _ANTHROPICS_CACHE
        headers = {
            **HEADERS,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        token = os.environ.get("GITHUB_TOKEN", "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        resp = requests.get(ANTHROPICS_CONTENTS, timeout=HTTP_TIMEOUT, headers=headers)
        resp.raise_for_status()
        items = [x for x in resp.json() if isinstance(x, dict) and x.get("type") == "dir"]
        _ANTHROPICS_CACHE = items
        return items

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        q = (query or "").strip().lower()
        items = self._list_all()
        matched = []
        for it in items:
            name = it.get("name") or ""
            if not q or q in name.lower() or any(p in name.lower() for p in q.split()):
                matched.append(it)
        # 无命中时返回前若干官方技能，避免空结果
        if not matched and q:
            matched = [it for it in items if any(tok in (it.get("name") or "").lower() for tok in q.replace("-", " ").split() if len(tok) > 2)]
        out: List[Dict[str, Any]] = []
        for it in matched[:limit]:
            name = it.get("name") or ""
            out.append(_item(
                source="anthropics",
                name=name,
                description=f"Anthropic 官方技能 · anthropics/skills/{name}",
                install_command=_skills_add_cmd(f"anthropics/skills@{name}"),
                install_count=0,
                author="anthropics",
                url=it.get("html_url") or f"https://github.com/anthropics/skills/tree/main/skills/{name}",
                raw=it,
            ))
        return out


CLIENTS: Dict[str, Any] = {
    "modelscope": ModelScopeSkillsClient(),
    "skillssh": SkillsShClient(),
    "skillsmp": SkillsMpClient(),
    "smithery": SmitherySkillsClient(),
    "clawhub": ClawHubClient(),
    "github": GitHubSkillsClient(),
    "anthropics": AnthropicSkillsClient(),
}


def search_skill_market(
    query: str,
    sources: Optional[List[str]] = None,
    limit_per_source: int = 12,
) -> Dict[str, Any]:
    q = (query or "").strip()
    if not q:
        raise ValueError("缺少搜索关键词")

    if sources:
        wanted = [s.lower().strip() for s in sources if s and s.lower().strip() in CLIENTS]
    else:
        wanted = list(SOURCE_PRIORITY)

    if not wanted:
        raise ValueError("无有效搜索源")

    per_source: Dict[str, List[Dict[str, Any]]] = {}
    errors: Dict[str, str] = {}

    def _run(name: str) -> Tuple[str, List[Dict[str, Any]], Optional[str]]:
        try:
            items = CLIENTS[name].search(q, limit=limit_per_source)
            return name, items, None
        except Exception as e:
            return name, [], str(e)

    with ThreadPoolExecutor(max_workers=min(8, len(wanted))) as ex:
        futs = [ex.submit(_run, name) for name in wanted]
        for fut in as_completed(futs):
            name, items, err = fut.result()
            per_source[name] = items
            if err:
                errors[name] = err

    # 按优先级交错合并 + 去重
    merged: List[Dict[str, Any]] = []
    seen = set()
    source_meta: Dict[str, Any] = {}
    for name in SOURCE_PRIORITY:
        if name not in per_source:
            continue
        items = per_source[name]
        source_meta[name] = {
            "label": SOURCE_LABELS.get(name, name),
            "count": len(items),
            "error": errors.get(name, ""),
        }
        for it in items:
            key = _dedupe_key(it)
            if key in seen:
                continue
            seen.add(key)
            merged.append(it)

    for name, err in errors.items():
        if name not in source_meta:
            source_meta[name] = {
                "label": SOURCE_LABELS.get(name, name),
                "count": 0,
                "error": err,
            }

    return {
        "ok": True,
        "data": merged,
        "errors": [f"{SOURCE_LABELS.get(k, k)}: {v}" for k, v in errors.items()],
        "meta": {
            "query": q,
            "sources": source_meta,
            "total": len(merged),
            "github_code_search": bool(os.environ.get("GITHUB_TOKEN", "").strip()),
            "skillsmp_auth": bool(os.environ.get("SKILLSMP_API_KEY", "").strip()),
            "smithery_auth": bool(os.environ.get("SMITHERY_API_KEY", "").strip()),
        },
    }
