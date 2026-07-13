"""MCP 市场多源聚合搜索。

数据源：
  - modelscope  ModelScope OpenAPI（国内，含 hosted/安装配置）
  - registry    官方 MCP Registry
  - smithery    Smithery
  - pulsemcp    PulseMCP
  - glama       Glama（覆盖 mcp.so/Glama 目录类发现；mcp.so 无公开 JSON API）

search 并行 fan-out；按 SOURCE_PRIORITY 合并；按 repo_url / 包名 / 规范化 id 跨源去重。
"""
from __future__ import annotations

import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

HTTP_TIMEOUT = 12
# PulseMCP 对自定义 UA 返回 410，沿用常见客户端标识
USER_AGENT = "AdeBuddy/1.0"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}

MODELSCOPE_LIST_API = "https://www.modelscope.cn/openapi/v1/mcp/servers"
MODELSCOPE_DETAIL_API = "https://www.modelscope.cn/openapi/v1/mcp/servers/{owner}/{name}"
REGISTRY_BASE = "https://registry.modelcontextprotocol.io"
SMITHERY_BASE = "https://api.smithery.ai"
PULSEMCP_BASE = "https://api.pulsemcp.com/v0beta"
GLAMA_BASE = "https://glama.ai/api/mcp/v1"

# 搜索优先级：官方 > 主流市场 > 社区
SOURCE_PRIORITY = ("registry", "smithery", "modelscope", "pulsemcp", "glama")
SOURCE_LABELS = {
    "registry": "Official Registry",
    "smithery": "Smithery",
    "modelscope": "ModelScope",
    "pulsemcp": "PulseMCP",
    "glama": "Glama",
}


def _safe(fn: Callable[[], Any], default: Any) -> Any:
    try:
        return fn()
    except Exception:
        return default


def _norm_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    if u.startswith("git@"):
        u = u.replace(":", "/").replace("git@", "https://", 1)
    if u.endswith(".git"):
        u = u[:-4]
    parsed = urllib.parse.urlparse(u if "://" in u else f"https://{u}")
    host = (parsed.netloc or "").lower()
    path = re.sub(r"/+$", "", (parsed.path or "").lower())
    return f"{host}{path}"


def _norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def _local_name(name: str) -> str:
    """生成适合写入 mcpServers 的本地 key。"""
    n = (name or "mcp").strip()
    n = n.split("/")[-1]
    n = re.sub(r"[^A-Za-z0-9._-]+", "-", n).strip("-")
    return n or "mcp"


def _result(
    *,
    source: str,
    id: str,
    name: str,
    description: str = "",
    owner: str = "",
    author: str = "",
    homepage: str = "",
    repo_url: str = "",
    package_name: str = "",
    is_hosted: bool = False,
    categories: Optional[List[Any]] = None,
    install_hint: Optional[Dict[str, Any]] = None,
    raw: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "id": id,
        "name": name,
        "owner": owner,
        "author": author or owner,
        "description": description or "",
        "homepage": homepage or "",
        "repo_url": repo_url or "",
        "package_name": package_name or "",
        "is_hosted": bool(is_hosted),
        "categories": categories or [],
        "source": source,
        "source_label": SOURCE_LABELS.get(source, source),
        "install_hint": install_hint,
        "raw": raw or {},
    }


def _dedupe_key(item: Dict[str, Any]) -> str:
    repo = _norm_url(item.get("repo_url") or "")
    if repo:
        return f"repo:{repo}"
    pkg = (item.get("package_name") or "").strip().lower()
    if pkg:
        return f"pkg:{pkg}"
    return f"id:{item.get('source')}:{_norm_name(item.get('id') or item.get('name') or '')}"


def _dedupe(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for it in items:
        key = _dedupe_key(it)
        if key in seen:
            # 保留更高优先级源；列表已按优先级展开，后出现的丢弃
            continue
        seen.add(key)
        out.append(it)
    return out


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------

class ModelScopeClient:
    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        resp = requests.put(
            MODELSCOPE_LIST_API,
            json={"page_number": 1, "page_size": min(limit, 20), "search": query},
            headers={**HEADERS, "Content-Type": "application/json"},
            timeout=HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
        data = payload.get("data") or payload
        servers = data.get("servers") or data.get("list") or []
        out = []
        for s in servers[:limit]:
            sid = s.get("id") or s.get("mcp_server_id") or ""
            owner = ""
            name = s.get("name") or s.get("en_name") or ""
            if isinstance(sid, str) and sid.startswith("@") and "/" in sid:
                owner = sid[1:].split("/", 1)[0]
                if not name:
                    name = sid.split("/", 1)[-1]
            out.append(_result(
                source="modelscope",
                id=sid or f"@{owner}/{name}",
                name=name or sid,
                owner=owner,
                author=s.get("author") or owner,
                description=s.get("description") or s.get("chinese_description") or "",
                is_hosted=bool(s.get("is_hosted", False)),
                categories=s.get("categories") or [],
                raw=s,
            ))
        return out

    def detail(self, owner: str, name: str) -> Dict[str, Any]:
        url = MODELSCOPE_DETAIL_API.format(owner=owner, name=name)
        resp = requests.get(
            url,
            params={"get_operational_url": "true"},
            headers={**HEADERS, "Content-Type": "application/json"},
            timeout=HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
        return payload.get("data") or payload


class RegistryClient:
    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        resp = requests.get(
            f"{REGISTRY_BASE}/v0/servers",
            params={"search": query, "limit": str(min(limit, 50))},
            headers=HEADERS,
            timeout=HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        servers = resp.json().get("servers") or []
        out = []
        for entry in servers[:limit]:
            server = entry.get("server") or entry
            name = server.get("name") or ""
            repo = ((server.get("repository") or {}).get("url") or "")
            packages = server.get("packages") or []
            pkg_name = ""
            if packages:
                pkg_name = packages[0].get("identifier") or ""
            remotes = server.get("remotes") or []
            out.append(_result(
                source="registry",
                id=name,
                name=name.split("/")[-1] if "/" in name else name,
                owner=name.split("/")[0] if "/" in name else "",
                description=server.get("description") or "",
                repo_url=repo,
                package_name=pkg_name,
                is_hosted=bool(remotes),
                install_hint=_registry_install_hint(server),
                raw=entry,
            ))
        return out

    def detail(self, server_name: str) -> Dict[str, Any]:
        encoded = urllib.parse.quote(server_name, safe="")
        resp = requests.get(
            f"{REGISTRY_BASE}/v0/servers/{encoded}/versions/latest",
            headers=HEADERS,
            timeout=HTTP_TIMEOUT,
        )
        if resp.status_code == 404:
            # fallback search
            hits = self.search(server_name, limit=1)
            if not hits:
                raise LookupError(f"registry 未找到: {server_name}")
            return hits[0].get("raw") or {}
        resp.raise_for_status()
        return resp.json()


def _registry_install_hint(server: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    remotes = server.get("remotes") or []
    if remotes:
        r0 = remotes[0]
        rtype = (r0.get("type") or "http").replace("streamable-http", "streamableHttp")
        return {"type": rtype, "url": r0.get("url")}
    packages = server.get("packages") or []
    if not packages:
        return None
    p0 = packages[0]
    transport = p0.get("transport") or {}
    if (transport.get("type") or "stdio") != "stdio" and transport.get("url"):
        return {"type": transport.get("type"), "url": transport.get("url")}
    ident = p0.get("identifier") or ""
    runtime = p0.get("runtimeHint") or "npx"
    args = []
    for a in p0.get("runtimeArguments") or []:
        if isinstance(a, dict) and a.get("value"):
            args.append(str(a["value"]))
        elif isinstance(a, str):
            args.append(a)
    if runtime == "npx" and ident:
        if "-y" not in args:
            args = ["-y", *args]
        if ident not in args:
            args.append(ident)
        for a in p0.get("packageArguments") or []:
            if isinstance(a, dict) and a.get("value"):
                args.append(str(a["value"]))
        env = {}
        for ev in p0.get("environmentVariables") or []:
            if isinstance(ev, dict) and ev.get("name"):
                env[ev["name"]] = f"${{{ev['name']}}}"
        cfg: Dict[str, Any] = {"command": runtime, "args": args}
        if env:
            cfg["env"] = env
        return cfg
    if runtime in ("uvx", "uv") and ident:
        cfg = {"command": runtime, "args": [ident]}
        return cfg
    return None


class SmitheryClient:
    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        resp = requests.get(
            f"{SMITHERY_BASE}/servers",
            params={"q": query},
            headers=HEADERS,
            timeout=HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        servers = resp.json().get("servers") or []
        out = []
        for s in servers[:limit]:
            qname = s.get("qualifiedName") or s.get("id") or ""
            out.append(_result(
                source="smithery",
                id=qname,
                name=s.get("displayName") or qname,
                owner=s.get("namespace") or "",
                author=s.get("namespace") or "",
                description=s.get("description") or "",
                homepage=s.get("homepage") or "",
                is_hosted=bool(s.get("remote") or s.get("isDeployed")),
                install_hint=None,
                raw=s,
            ))
        return out

    def detail(self, qualified_name: str) -> Dict[str, Any]:
        resp = requests.get(
            f"{SMITHERY_BASE}/servers/{urllib.parse.quote(qualified_name, safe='/')}",
            headers=HEADERS,
            timeout=HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()


def _smithery_install_hint(detail: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for c in detail.get("connections") or []:
        url = c.get("deploymentUrl") or c.get("url")
        if url:
            ctype = c.get("type") or "http"
            if ctype == "sse":
                return {"type": "sse", "url": url}
            return {"type": "http" if ctype == "http" else ctype, "url": url}
    if detail.get("deploymentUrl"):
        return {"type": "http", "url": detail["deploymentUrl"]}
    return None


class PulseMCPClient:
    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        resp = None
        for attempt in range(2):
            resp = requests.get(
                f"{PULSEMCP_BASE}/servers",
                params={"query": query, "count_per_page": str(max(1, min(limit, 50)))},
                headers=HEADERS,
                timeout=HTTP_TIMEOUT,
            )
            # 并行聚合时偶发 410，重试一次
            if resp.status_code == 410 and attempt == 0:
                continue
            break
        assert resp is not None
        resp.raise_for_status()
        servers = resp.json().get("servers") or []
        out = []
        for s in servers[:limit]:
            name = s.get("name") or ""
            remotes = s.get("remotes") or []
            hint = None
            if remotes:
                r0 = remotes[0] if isinstance(remotes[0], dict) else {}
                if r0.get("url"):
                    hint = {"type": r0.get("type") or "http", "url": r0["url"]}
            elif s.get("package_name") and (s.get("package_registry") or "") == "npm":
                hint = {"command": "npx", "args": ["-y", s["package_name"]]}
            out.append(_result(
                source="pulsemcp",
                id=s.get("url") or name,
                name=name,
                description=s.get("short_description") or s.get("EXPERIMENTAL_ai_generated_description") or "",
                homepage=s.get("url") or "",
                repo_url=s.get("source_code_url") or s.get("external_url") or "",
                package_name=s.get("package_name") or "",
                is_hosted=bool(remotes),
                install_hint=hint,
                raw=s,
            ))
        return out


class GlamaClient:
    """Glama 目录 API。mcp.so 无稳定公开 JSON 搜索接口，目录类发现统一走 Glama。"""

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        resp = requests.get(
            f"{GLAMA_BASE}/servers",
            params={"query": query, "first": str(min(limit, 50))},
            headers=HEADERS,
            timeout=HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        servers = resp.json().get("servers") or []
        out = []
        for s in servers[:limit]:
            ns = s.get("namespace") or ""
            slug = s.get("slug") or ""
            sid = f"{ns}/{slug}" if ns and slug else (s.get("id") or s.get("name") or "")
            repo = ((s.get("repository") or {}).get("url") or "")
            attrs = s.get("attributes") or []
            hint = None
            env_schema = s.get("environmentVariablesJsonSchema") or {}
            props = (env_schema.get("properties") or {}) if isinstance(env_schema, dict) else {}
            if props and repo:
                # 无权威 install 命令时，仅提供 env 占位提示，由详情页补全
                env = {k: f"${{{k}}}" for k in props.keys()}
                hint = {"_needs_manual": True, "env": env, "repo_url": repo}
            out.append(_result(
                source="glama",
                id=sid,
                name=s.get("name") or slug or sid,
                owner=ns,
                author=ns,
                description=s.get("description") or "",
                homepage=s.get("url") or "",
                repo_url=repo,
                is_hosted="hosting:remote-capable" in attrs or "hosting:hosted" in attrs,
                install_hint=hint,
                raw=s,
            ))
        return out

    def detail(self, namespace: str, slug: str) -> Dict[str, Any]:
        resp = requests.get(
            f"{GLAMA_BASE}/servers/{urllib.parse.quote(namespace)}/{urllib.parse.quote(slug)}",
            headers=HEADERS,
            timeout=HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()


CLIENTS = {
    "modelscope": ModelScopeClient(),
    "registry": RegistryClient(),
    "smithery": SmitheryClient(),
    "pulsemcp": PulseMCPClient(),
    "glama": GlamaClient(),
}


class McpMarketAggregator:
    def __init__(self, sources: Optional[List[str]] = None):
        if sources:
            self.sources = [s for s in sources if s in CLIENTS]
        else:
            self.sources = list(SOURCE_PRIORITY)

    def search(self, query: str, limit_per_source: int = 12) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        results_by_source: Dict[str, List[Dict[str, Any]]] = {}
        errors: Dict[str, str] = {}

        def _run(name: str) -> Tuple[str, List[Dict[str, Any]], Optional[str]]:
            try:
                return name, CLIENTS[name].search(query, limit=limit_per_source), None
            except Exception as e:
                return name, [], str(e)

        with ThreadPoolExecutor(max_workers=max(1, len(self.sources))) as ex:
            futs = [ex.submit(_run, name) for name in self.sources]
            for fut in as_completed(futs):
                name, items, err = fut.result()
                results_by_source[name] = items
                if err:
                    errors[name] = err

        ordered: List[Dict[str, Any]] = []
        for name in SOURCE_PRIORITY:
            if name in results_by_source:
                ordered.extend(results_by_source[name])
        merged = _dedupe(ordered)
        meta = {
            "sources": {
                name: {
                    "count": len(results_by_source.get(name, [])),
                    "error": errors.get(name),
                    "label": SOURCE_LABELS.get(name, name),
                }
                for name in self.sources
            },
            "note": "mcp.so 无公开 JSON 搜索 API，目录类发现由 Glama 覆盖",
        }
        return merged, meta

    def resolve_install(
        self,
        source: str,
        id: str = "",
        owner: str = "",
        name: str = "",
    ) -> Dict[str, Any]:
        """解析可写入 mcpServers 的 server_config。"""
        source = (source or "modelscope").lower()
        local = _local_name(name or id)

        if source == "modelscope":
            if not owner or not name:
                # id 形如 @owner/name
                if id.startswith("@") and "/" in id:
                    owner, name = id[1:].split("/", 1)
                else:
                    raise ValueError("modelscope 需要 owner/name")
            data = ModelScopeClient().detail(owner, name)
            servers = data.get("servers") or data.get("mcp_servers") or []
            cfg = None
            if servers:
                s0 = servers[0]
                cfg = {"type": s0.get("type"), "url": s0.get("url")}
                if data.get("auth_required"):
                    cfg["headers"] = {"Authorization": "Bearer ${MODELSCOPE_TOKEN}"}
            elif data.get("server_config"):
                cfg = data["server_config"]
            if not cfg:
                raise ValueError("未找到 server_config")
            return {
                "local_name": _local_name(name),
                "server_config": cfg,
                "source": source,
                "detail": data,
            }

        if source == "registry":
            sid = id or name
            raw = RegistryClient().detail(sid)
            server = raw.get("server") or raw
            hint = _registry_install_hint(server)
            if not hint:
                raise ValueError("官方 Registry 条目缺少 packages/remotes，无法自动生成配置")
            return {
                "local_name": _local_name(server.get("name") or sid),
                "server_config": hint,
                "source": source,
                "detail": raw,
            }

        if source == "smithery":
            qname = id or name
            detail = SmitheryClient().detail(qname)
            hint = _smithery_install_hint(detail)
            if not hint:
                raise ValueError("Smithery 条目无可用 connection/deploymentUrl")
            return {
                "local_name": _local_name(detail.get("displayName") or qname),
                "server_config": hint,
                "source": source,
                "detail": detail,
            }

        if source == "pulsemcp":
            # PulseMCP 无稳定 detail API，依赖 search 首条 + install_hint
            hits = PulseMCPClient().search(id or name, limit=5)
            hit = None
            target = (id or name or "").lower()
            for h in hits:
                if (h.get("id") or "").lower() == target or (h.get("name") or "").lower() == target:
                    hit = h
                    break
            hit = hit or (hits[0] if hits else None)
            if not hit or not hit.get("install_hint"):
                raise ValueError("PulseMCP 无法解析安装配置（可改用手动添加）")
            return {
                "local_name": _local_name(hit.get("name") or local),
                "server_config": hit["install_hint"],
                "source": source,
                "detail": hit.get("raw") or hit,
            }

        if source == "glama":
            ns, slug = owner, name
            if (not ns or not slug) and "/" in (id or ""):
                ns, slug = id.split("/", 1)
            if not ns or not slug:
                raise ValueError("glama 需要 namespace/slug")
            detail = GlamaClient().detail(ns, slug)
            repo = ((detail.get("repository") or {}).get("url") or "")
            raise ValueError(
                f"Glama 条目通常需手动配置。仓库: {repo or '未知'}。"
                "请到「手动添加」粘贴官方安装 JSON。"
            )

        raise ValueError(f"未知 source: {source}")


def search_mcp_market(
    query: str,
    sources: Optional[List[str]] = None,
    limit_per_source: int = 12,
) -> Dict[str, Any]:
    agg = McpMarketAggregator(sources=sources)
    items, meta = agg.search(query, limit_per_source=limit_per_source)
    return {"ok": True, "data": items, "total": len(items), "meta": meta}


def resolve_mcp_install(
    source: str,
    id: str = "",
    owner: str = "",
    name: str = "",
) -> Dict[str, Any]:
    return McpMarketAggregator().resolve_install(source=source, id=id, owner=owner, name=name)
