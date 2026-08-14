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

import json
import os
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

HTTP_TIMEOUT = 12
# Glama 跨境偶发慢/超时：分开 connect/read，避免卡死；失败时走软降级
GLAMA_TIMEOUT = (5, 18)
REPO_FETCH_TIMEOUT = (5, 12)
# PulseMCP 对部分 UA / 并行请求不稳定，使用浏览器式 UA
USER_AGENT = "AgentBuddy/1.0"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}

MODELSCOPE_LIST_API = "https://www.modelscope.cn/openapi/v1/mcp/servers"
# 详情路径必须带完整 mcp_id：@owner/name 或 owner/name（不能拆成 owner/name 丢掉 @）
MODELSCOPE_DETAIL_API = "https://www.modelscope.cn/openapi/v1/mcp/servers/{mcp_id}"
REGISTRY_BASE = "https://registry.modelcontextprotocol.io"
SMITHERY_BASE = "https://api.smithery.ai"
# PulseMCP：v0beta 正在日落（随机 410 API_SUNSET）；正式接口为 v0.1（需 API Key）
PULSEMCP_V01_BASE = "https://api.pulsemcp.com/v0.1"
PULSEMCP_V0BETA_BASE = "https://api.pulsemcp.com/v0beta"
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
        # ModelScope 实际字段为 mcp_server_list（兼容旧 servers/list）
        servers = (
            data.get("mcp_server_list")
            or data.get("servers")
            or data.get("list")
            or []
        )
        out = []
        for s in servers[:limit]:
            sid = str(s.get("id") or s.get("mcp_server_id") or "")
            owner, server_name = _modelscope_owner_name(sid)
            locales = s.get("locales") or {}
            en = locales.get("en") or {}
            zh = locales.get("zh") or {}
            name = (
                s.get("name")
                or s.get("chinese_name")
                or zh.get("name")
                or en.get("name")
                or server_name
                or sid
            )
            description = (
                s.get("description")
                or s.get("chinese_description")
                or zh.get("description")
                or en.get("description")
                or ""
            )
            out.append(_result(
                source="modelscope",
                id=sid or f"@{owner}/{server_name}",
                name=name,
                owner=owner,
                author=s.get("author") or s.get("publisher") or owner,
                description=description,
                is_hosted=bool(s.get("is_hosted", False)),
                categories=s.get("categories") or s.get("tags") or [],
                raw=s,
            ))
        return out

    def detail(
        self,
        owner: str = "",
        name: str = "",
        server_id: str = "",
    ) -> Dict[str, Any]:
        candidates = _modelscope_id_candidates(server_id=server_id, owner=owner, name=name)
        headers = {**HEADERS, "Content-Type": "application/json"}
        token = _modelscope_api_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        # get_operational_url=true 需要登录态；无 Token 时拉公开详情（含 server_config）
        want_ops = bool(token)
        last_err: Optional[Exception] = None
        for mcp_id in candidates:
            url = MODELSCOPE_DETAIL_API.format(mcp_id=mcp_id)
            try:
                params: Optional[Dict[str, str]] = {"get_operational_url": "true"} if want_ops else None
                resp = requests.get(url, params=params, headers=headers, timeout=HTTP_TIMEOUT)
                if resp.status_code == 401 and params:
                    resp = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT)
                if resp.status_code == 404:
                    last_err = LookupError(f"ModelScope 未找到: {mcp_id}")
                    continue
                resp.raise_for_status()
                payload = resp.json()
                return payload.get("data") or payload
            except Exception as e:
                last_err = e
                continue
        if last_err:
            raise last_err
        raise ValueError("modelscope 需要 id 或 owner/name")


def _modelscope_api_token() -> str:
    return (
        os.environ.get("MODELSCOPE_API_TOKEN", "").strip()
        or os.environ.get("MODELSCOPE_TOKEN", "").strip()
    )


def _modelscope_id_candidates(server_id: str = "", owner: str = "", name: str = "") -> List[str]:
    """生成 ModelScope 详情 mcp_id 候选（保留 @，并兼容无 @ 的社区 id）。"""
    out: List[str] = []
    sid = (server_id or "").strip()
    if sid:
        out.append(sid)
        return out
    o = (owner or "").strip()
    n = (name or "").strip()
    if o and n:
        # 社区 id 多为 owner/name；官方 scoped 包需要 @owner/name
        out.append(f"{o}/{n}")
        out.append(f"@{o}/{n}")
    elif n:
        out.append(n)
    return out


def _modelscope_mcp_id(server_id: str = "", owner: str = "", name: str = "") -> str:
    cands = _modelscope_id_candidates(server_id=server_id, owner=owner, name=name)
    if not cands:
        raise ValueError("modelscope 需要 id 或 owner/name")
    return cands[0]


def _modelscope_owner_name(sid: str) -> Tuple[str, str]:
    """从 ModelScope id 解析 owner/name。

    支持：
      @modelcontextprotocol/github
      YTGX123/search
    """
    s = (sid or "").strip()
    if s.startswith("@"):
        s = s[1:]
    if "/" in s:
        owner, name = s.split("/", 1)
        return owner, name
    return "", s


_PLACEHOLDER_VAL = re.compile(
    r"^(?:<[^>]+>|your[_-]?token(?:[_-]?here)?|changeme|xxx+|TODO)$",
    re.IGNORECASE,
)


def _looks_like_secret_placeholder(value: str) -> bool:
    s = (value or "").strip()
    if not s:
        return True
    if _PLACEHOLDER_VAL.match(s) or "YOUR_" in s.upper() or "你的" in s:
        return True
    if re.search(r"_optional$", s, re.I):
        return True
    if re.match(r"^(?:ghp|gho|github_pat)_[x0-9a-z]*$", s, re.I) and "x" in s.lower():
        return True
    if re.match(r"^(?:sk|tok)[-_]?[x0-9]*$", s, re.I) and "x" in s.lower():
        return True
    if "xxx" in s.lower() and len(s) < 48:
        return True
    return False


def _normalize_ms_env(env: Any) -> Dict[str, str]:
    if not isinstance(env, dict):
        return {}
    out: Dict[str, str] = {}
    for k, v in env.items():
        key = str(k)
        if not isinstance(v, str):
            out[key] = str(v) if v is not None else f"${{{key}}}"
            continue
        if _looks_like_secret_placeholder(v):
            out[key] = f"${{{key}}}"
        else:
            out[key] = v
    return out


def _normalize_ms_server_cfg(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """把 ModelScope server_config 条目规范成可写入 mcpServers 的 dict。"""
    out = dict(cfg)
    if isinstance(out.get("env"), dict):
        out["env"] = _normalize_ms_env(out["env"])
    transport = str(out.pop("transport", "") or "").lower()
    if transport and "type" not in out:
        if transport in ("sse", "http", "streamable-http", "streamablehttp"):
            out["type"] = "sse" if transport == "sse" else "streamableHttp"
    # AgentBuddy 模板不需要该浏览器专用字段
    out.pop("useNodeEventSource", None)
    return out


def _extract_modelscope_install(data: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """从 ModelScope 详情中提取 (local_name, server_config)。"""
    # 1) get_operational_url 返回的 hosted servers
    servers = data.get("servers") or data.get("mcp_servers") or []
    if isinstance(servers, list) and servers:
        s0 = servers[0] if isinstance(servers[0], dict) else {}
        cfg: Dict[str, Any] = {}
        if s0.get("url"):
            cfg["url"] = s0["url"]
        if s0.get("type"):
            cfg["type"] = s0["type"]
        if data.get("auth_required"):
            cfg["headers"] = {"Authorization": "Bearer ${MODELSCOPE_TOKEN}"}
        if cfg.get("url"):
            return _local_name(str(data.get("name") or data.get("id") or "mcp")), cfg

    # 2) operational_urls（有时仅 URL 列表）
    ops = data.get("operational_urls") or []
    if isinstance(ops, list) and ops:
        first = ops[0]
        url = first if isinstance(first, str) else (first or {}).get("url")
        if url:
            cfg = {"type": "sse", "url": url}
            if data.get("auth_required"):
                cfg["headers"] = {"Authorization": "Bearer ${MODELSCOPE_TOKEN}"}
            return _local_name(str(data.get("name") or data.get("id") or "mcp")), cfg

    # 3) 公开详情里的 server_config：[{mcpServers:{name: cfg}}, ...]
    sc = data.get("server_config")
    blocks: List[Any]
    if isinstance(sc, list):
        blocks = sc
    elif isinstance(sc, dict):
        blocks = [sc]
    else:
        blocks = []

    for block in blocks:
        if not isinstance(block, dict):
            continue
        mcp_servers = block.get("mcpServers")
        if isinstance(mcp_servers, dict) and mcp_servers:
            key, raw_cfg = next(iter(mcp_servers.items()))
            if isinstance(raw_cfg, dict):
                return str(key), _normalize_ms_server_cfg(raw_cfg)
        # 少数条目可能直接是单服务字段
        if block.get("command") or block.get("url"):
            return _local_name(str(data.get("name") or data.get("id") or "mcp")), _normalize_ms_server_cfg(block)

    raise ValueError("未找到可用的 server_config（可配置 MODELSCOPE_API_TOKEN 后重试，或改用手动添加）")


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
    """PulseMCP 搜索客户端。

    - 优先：v0.1（需环境变量 PULSEMCP_API_KEY，可选 PULSEMCP_TENANT_ID）
    - 回退：v0beta（正在日落，会随机 410/API_SUNSET，加重试）
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ):
        import os
        self.api_key = (api_key if api_key is not None else os.environ.get("PULSEMCP_API_KEY", "")).strip()
        self.tenant_id = (
            tenant_id if tenant_id is not None else os.environ.get("PULSEMCP_TENANT_ID", "")
        ).strip()

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        if self.api_key:
            return self._search_v01(query, limit)
        return self._search_v0beta(query, limit)

    def _search_v01(self, query: str, limit: int) -> List[Dict[str, Any]]:
        headers = {
            **HEADERS,
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }
        if self.tenant_id:
            headers["X-Tenant-ID"] = self.tenant_id
        resp = requests.get(
            f"{PULSEMCP_V01_BASE}/servers",
            params={
                "search": query,
                "limit": str(max(1, min(limit, 100))),
                "version": "latest",
            },
            headers=headers,
            timeout=HTTP_TIMEOUT,
        )
        if resp.status_code in (401, 403):
            raise RuntimeError(
                "PulseMCP v0.1 需要有效 API Key（环境变量 PULSEMCP_API_KEY / PULSEMCP_TENANT_ID）。"
                "申请：hello@pulsemcp.com · 文档：https://www.pulsemcp.com/api/docs/v0.1"
            )
        resp.raise_for_status()
        servers = resp.json().get("servers") or []
        return [self._map_v01_entry(entry) for entry in servers[:limit]]

    def _map_v01_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        server = entry.get("server") or entry
        name = server.get("name") or ""
        title = server.get("title") or (name.split("/")[-1] if "/" in name else name)
        repo = ((server.get("repository") or {}).get("url") or "")
        packages = server.get("packages") or []
        pkg_name = (packages[0].get("identifier") if packages else "") or ""
        remotes = server.get("remotes") or []
        hint = _registry_install_hint(server)
        return _result(
            source="pulsemcp",
            id=name or title,
            name=title or name,
            owner=name.split("/")[0] if "/" in name else "",
            description=server.get("description") or "",
            homepage=server.get("websiteUrl") or "",
            repo_url=repo,
            package_name=pkg_name,
            is_hosted=bool(remotes),
            install_hint=hint,
            raw=entry,
        )

    def _search_v0beta(self, query: str, limit: int) -> List[Dict[str, Any]]:
        import time

        last_err: Optional[str] = None
        resp = None
        # v0beta 日落期按比例随机 410；多试几次通常能过（2026-09 将 100% 失败）
        for attempt in range(6):
            resp = requests.get(
                f"{PULSEMCP_V0BETA_BASE}/servers",
                params={"query": query, "count_per_page": str(max(1, min(limit, 50)))},
                headers=HEADERS,
                timeout=HTTP_TIMEOUT,
            )
            if resp.status_code == 410:
                last_err = (resp.text or "")[:240]
                time.sleep(0.15 * (attempt + 1))
                continue
            break

        assert resp is not None
        if resp.status_code == 410:
            raise RuntimeError(
                "PulseMCP v0beta 正在日落（API_SUNSET，随机失败）。"
                "请设置环境变量 PULSEMCP_API_KEY（及可选 PULSEMCP_TENANT_ID）改用 v0.1；"
                "申请：hello@pulsemcp.com"
                + (f" | raw={last_err}" if last_err else "")
            )
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


def _glama_ns_slug(
    server_id: str = "",
    owner: str = "",
    name: str = "",
) -> Tuple[str, str]:
    """解析 Glama namespace/slug。

    必须优先用 id（如 LauraMattz/mcp_ai_news）；
    item.name 常为展示名「AI News Aggregator」，不能当 slug。
    """
    sid = (server_id or "").strip()
    if "/" in sid:
        ns, slug = sid.split("/", 1)
        if ns and slug:
            return ns, slug
    o = (owner or "").strip()
    n = (name or "").strip()
    # name 含空格/中文时几乎一定是展示名，不能拼进详情路径
    if o and n and (" " not in n) and not re.search(r"[\u4e00-\u9fff]", n):
        return o, n
    if o and sid and "/" not in sid:
        return o, sid
    return o, ""


def _glama_repo_fallback(ns: str, slug: str, repo_url: str = "") -> str:
    repo = (repo_url or "").strip()
    if repo:
        return repo
    if ns and slug:
        return f"https://github.com/{ns}/{slug}"
    return ""


def _glama_manual_message(repo: str = "", reason: str = "") -> str:
    base = "Glama 条目通常需手动配置"
    if reason:
        base = f"{reason}。{base}"
    if repo:
        return f"{base}。仓库: {repo}。请到「手动添加」粘贴官方安装 JSON。"
    return f"{base}。请到「手动添加」粘贴官方安装 JSON。"


def _parse_github_repo(repo_url: str) -> Optional[Tuple[str, str]]:
    """从仓库 URL 解析 (owner, repo)。"""
    u = (repo_url or "").strip()
    if not u:
        return None
    if u.startswith("git@"):
        u = u.replace(":", "/").replace("git@", "https://", 1)
    if u.endswith(".git"):
        u = u[:-4]
    m = re.search(r"github\.com[/:]([^/\s]+)/([^/\s?#]+)", u, re.I)
    if not m:
        return None
    return m.group(1), m.group(2)


def _strip_jsonc(text: str) -> str:
    """粗略去掉 JSONC 行注释，便于 README 代码块解析。"""
    out_lines = []
    for line in (text or "").splitlines():
        if re.match(r"^\s*//", line):
            continue
        out_lines.append(re.sub(r"\s+//.*$", "", line))
    return "\n".join(out_lines)


def _env_from_schema(schema: Any) -> Dict[str, str]:
    if not isinstance(schema, dict):
        return {}
    props = schema.get("properties") or {}
    if not isinstance(props, dict):
        return {}
    env: Dict[str, str] = {}
    for key, meta in props.items():
        k = str(key)
        if isinstance(meta, dict) and meta.get("default") is not None and not isinstance(meta.get("default"), (dict, list)):
            env[k] = str(meta["default"])
        else:
            env[k] = f"${{{k}}}"
    return env


def _merge_env(base: Optional[Dict[str, Any]], extra: Optional[Dict[str, str]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if isinstance(base, dict):
        out.update(_normalize_ms_env(base))
    if isinstance(extra, dict):
        for k, v in extra.items():
            if k not in out or not str(out.get(k) or "").strip():
                out[k] = v
    return out


def _pick_mcp_server_entry(
    servers: Dict[str, Any],
    preferred_name: str = "",
) -> Optional[Tuple[str, Dict[str, Any]]]:
    if not isinstance(servers, dict) or not servers:
        return None
    pref = _local_name(preferred_name) if preferred_name else ""
    if pref and pref in servers and isinstance(servers[pref], dict):
        return pref, dict(servers[pref])
    # 忽略大小写 / 破折号差异
    pref_norm = _norm_name(pref)
    if pref_norm:
        for k, v in servers.items():
            if _norm_name(str(k)) == pref_norm and isinstance(v, dict):
                return str(k), dict(v)
    for k, v in servers.items():
        if isinstance(v, dict) and (v.get("command") or v.get("url")):
            return str(k), dict(v)
    return None


def _extract_mcp_from_readme(text: str, preferred_name: str = "") -> Optional[Tuple[str, Dict[str, Any]]]:
    """从 README 代码块提取 mcpServers 配置。"""
    if not text:
        return None
    fence = re.compile(r"```(?:json|jsonc)?\s*\n(.*?)```", re.S | re.I)
    for m in fence.finditer(text):
        block = _strip_jsonc(m.group(1)).strip()
        if "mcpServers" not in block:
            continue
        # 允许代码块不是纯 JSON：截取最外层 {}
        start = block.find("{")
        end = block.rfind("}")
        if start < 0 or end <= start:
            continue
        raw = block[start : end + 1]
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        servers = data.get("mcpServers")
        picked = _pick_mcp_server_entry(servers if isinstance(servers, dict) else {}, preferred_name)
        if picked:
            key, cfg = picked
            return key, _normalize_ms_server_cfg(cfg)
    return None


def _github_raw_get(owner: str, repo: str, path: str) -> Optional[str]:
    headers = {**HEADERS, "Accept": "text/plain"}
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    for branch in ("main", "master"):
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
        try:
            resp = requests.get(url, headers=headers, timeout=REPO_FETCH_TIMEOUT)
        except requests.RequestException:
            continue
        if resp.status_code == 200 and (resp.text or "").strip():
            return resp.text
    return None


def _cfg_from_package_json(text: str, preferred_name: str = "") -> Optional[Tuple[str, Dict[str, Any]]]:
    try:
        pkg = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(pkg, dict):
        return None
    pkg_name = str(pkg.get("name") or "").strip()
    if not pkg_name:
        return None
    local = _local_name(preferred_name or pkg_name)
    return local, {"command": "npx", "args": ["-y", pkg_name]}


def _cfg_from_pyproject(text: str, preferred_name: str = "") -> Optional[Tuple[str, Dict[str, Any]]]:
    # 轻量解析，避免强依赖 tomllib
    m = re.search(r'(?m)^name\s*=\s*["\']([^"\']+)["\']', text or "")
    if not m:
        return None
    pkg_name = m.group(1).strip()
    if not pkg_name:
        return None
    local = _local_name(preferred_name or pkg_name)
    return local, {"command": "uvx", "args": [pkg_name]}


def _resolve_install_from_repo(
    repo_url: str,
    *,
    preferred_name: str = "",
    env_schema: Any = None,
) -> Tuple[str, Dict[str, Any]]:
    """替用户完成「打开仓库 → 复制安装 JSON」：从 README / package.json / pyproject 推断配置。"""
    parsed = _parse_github_repo(repo_url)
    if not parsed:
        raise ValueError("仅支持从 GitHub 仓库自动解析安装配置")
    owner, repo = parsed
    schema_env = _env_from_schema(env_schema)

    readme = _github_raw_get(owner, repo, "README.md") or _github_raw_get(owner, repo, "readme.md")
    if readme:
        picked = _extract_mcp_from_readme(readme, preferred_name=preferred_name or repo)
        if picked:
            key, cfg = picked
            merged_env = _merge_env(cfg.get("env") if isinstance(cfg.get("env"), dict) else {}, schema_env)
            if merged_env:
                cfg = {**cfg, "env": merged_env}
            return key, cfg

    pkg_text = _github_raw_get(owner, repo, "package.json")
    if pkg_text:
        picked = _cfg_from_package_json(pkg_text, preferred_name=preferred_name or repo)
        if picked:
            key, cfg = picked
            if schema_env:
                cfg = {**cfg, "env": schema_env}
            return key, cfg

    py_text = _github_raw_get(owner, repo, "pyproject.toml")
    if py_text:
        picked = _cfg_from_pyproject(py_text, preferred_name=preferred_name or repo)
        if picked:
            key, cfg = picked
            if schema_env:
                cfg = {**cfg, "env": schema_env}
            return key, cfg

    raise ValueError("仓库中未找到可识别的 MCP 安装配置（README mcpServers / package.json / pyproject.toml）")


class GlamaClient:
    """Glama 目录 API。mcp.so 无稳定公开 JSON 搜索接口，目录类发现统一走 Glama。"""

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        resp = requests.get(
            f"{GLAMA_BASE}/servers",
            params={"query": query, "first": str(min(limit, 50))},
            headers=HEADERS,
            timeout=GLAMA_TIMEOUT,
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

    def detail(self, namespace: str = "", slug: str = "", server_id: str = "") -> Dict[str, Any]:
        ns, sl = _glama_ns_slug(server_id=server_id, owner=namespace, name=slug)
        if not ns or not sl:
            raise ValueError("glama 需要 namespace/slug（完整 id）")
        resp = requests.get(
            f"{GLAMA_BASE}/servers/{urllib.parse.quote(ns)}/{urllib.parse.quote(sl)}",
            headers=HEADERS,
            timeout=GLAMA_TIMEOUT,
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
                client = PulseMCPClient() if name == "pulsemcp" else CLIENTS[name]
                return name, client.search(query, limit=limit_per_source), None
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
        import os
        has_pulse_key = bool(os.environ.get("PULSEMCP_API_KEY", "").strip())
        meta = {
            "sources": {
                name: {
                    "count": len(results_by_source.get(name, [])),
                    "error": errors.get(name),
                    "label": SOURCE_LABELS.get(name, name),
                }
                for name in self.sources
            },
            "note": (
                "mcp.so 无公开 JSON API，由 Glama 覆盖；"
                + (
                    "PulseMCP 使用 v0.1（已配置 API Key）"
                    if has_pulse_key
                    else "PulseMCP v0beta 日落中，稳定使用请配置 PULSEMCP_API_KEY"
                )
            ),
            "pulsemcp_mode": "v0.1" if has_pulse_key else "v0beta",
        }
        return merged, meta

    def resolve_install(
        self,
        source: str,
        id: str = "",
        owner: str = "",
        name: str = "",
        detail: Optional[Dict[str, Any]] = None,
        repo_url: str = "",
    ) -> Dict[str, Any]:
        """解析可写入 mcpServers 的 server_config。

        detail / repo_url：可选预取数据，避免 Glama 等源重复打详情接口。
        """
        source = (source or "modelscope").lower()
        local = _local_name(name or id)

        if source == "modelscope":
            sid = (id or "").strip()
            if not sid and not (owner and name):
                raise ValueError("modelscope 需要 id 或 owner/name")
            # 详情 API 必须以完整 mcp_id 请求；有 id 时绝不用展示名拼路径
            data = ModelScopeClient().detail(
                server_id=sid,
                owner=owner if not sid else "",
                name=name if not sid else "",
            )
            local, cfg = _extract_modelscope_install(data)
            return {
                "local_name": local,
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
            ns, slug = _glama_ns_slug(server_id=id, owner=owner, name=name)
            if not ns or not slug:
                raise ValueError("glama 需要完整 id（namespace/slug）")
            data = detail
            if data is None:
                try:
                    data = GlamaClient().detail(namespace=ns, slug=slug)
                except Exception:
                    data = {}
            repo = (
                ((data or {}).get("repository") or {}).get("url")
                or _glama_repo_fallback(ns, slug, repo_url)
            )
            if not repo:
                raise ValueError(_glama_manual_message(reason="缺少仓库地址"))
            try:
                local, cfg = _resolve_install_from_repo(
                    repo,
                    preferred_name=slug or name or id,
                    env_schema=(data or {}).get("environmentVariablesJsonSchema"),
                )
            except Exception as e:
                raise ValueError(
                    _glama_manual_message(repo, reason=f"自动解析失败: {e}")
                ) from e
            return {
                "local_name": local,
                "server_config": cfg,
                "source": source,
                "detail": data or {"repository": {"url": repo}, "namespace": ns, "slug": slug},
                "resolved_from": "repo",
            }

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
    detail: Optional[Dict[str, Any]] = None,
    repo_url: str = "",
) -> Dict[str, Any]:
    return McpMarketAggregator().resolve_install(
        source=source,
        id=id,
        owner=owner,
        name=name,
        detail=detail,
        repo_url=repo_url,
    )
